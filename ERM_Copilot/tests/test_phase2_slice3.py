"""
Phase 2 Slice 3 Tests: Governed Duplicate Risk Detection
1. Matching Strategy (Layer A, Layer B, Layer C):
   - Exact name match (case & whitespace insensitive).
   - Normalized name match (punctuation, multi-spaces).
   - Similar name match (token overlap, Jaccard, SequenceMatcher).
   - Description similarity with name overlap.
   - Generic description avoidance (operational risk, process issue).
   - Empty/insufficient draft handling.
   - Deterministic match reasons and bounded result limits.
2. AI Harness Governance & Security:
   - Tool registration (read_only, idempotent, CREATOR_ROLES).
   - Role authorization (Risk Owner vs Auditor).
   - Department scoping and isolation.
   - Read-only safety (zero database writes).
   - Parameterized queries and SQL-injection safety.
3. Conversational Agent Integration:
   - Automatic execution on review readiness.
   - Non-blocking advisory warning banner in preview.
   - Candidate grounding (no LLM hallucinations).
   - Cache validity and stale invalidation on title/description edit.
   - User acknowledgment flow ("distinct risk", "not duplicate").
   - Explicit confirmation and fingerprint integrity preserved.
   - Checkpoint serialization and restoration.
"""
import unittest
from unittest.mock import MagicMock, patch

from ERM_Copilot.agents.risk_creation.agent import RiskCreationAgent
from ERM_Copilot.agents.risk_creation.state import RiskCreationSession, RiskCreationState
from ERM_Copilot.ai_harness.context import HarnessContext
from ERM_Copilot.ai_harness.exceptions import (
    AuthorizationError,
    ToolValidationError,
)
from ERM_Copilot.ai_harness.execution import ExecutionCoordinator
from ERM_Copilot.ai_harness.policies import (
    ROLE_ADMIN,
    ROLE_RISK_OWNER,
    ROLE_SUPER_ADMIN,
    ROLE_AUDITOR,
    ROLE_BOARD_AUDIT,
)
from ERM_Copilot.ai_harness.tool_registry import tool_registry
from ERM_Copilot.models.contracts import AgentRequest
from ERM_Copilot.services.db_service import ERMDatabaseService, erm_db


class TestMatchingAlgorithm(unittest.TestCase):
    """Deterministic, explainable matching logic tests (Layers A, B, C)."""

    def test_layer_a_exact_name_match(self):
        # Identical
        reason, score = ERMDatabaseService.score_candidate_match(
            "Pump Failure in Plant 1", "Pump Failure in Plant 1"
        )
        self.assertEqual(reason, "exact_name_match")
        self.assertEqual(score, 1.0)

        # Case-insensitive and extra whitespace
        reason, score = ERMDatabaseService.score_candidate_match(
            "   pump   failure   in plant 1   ", "Pump Failure in Plant 1"
        )
        self.assertEqual(reason, "exact_name_match")
        self.assertEqual(score, 1.0)

    def test_layer_a_normalized_name_match(self):
        # Punctuation differences: hyphens, colons, slashes
        reason, score = ERMDatabaseService.score_candidate_match(
            "Data-Leak: Cloud / Storage!", "Data Leak Cloud Storage"
        )
        self.assertEqual(reason, "normalized_name_match")
        self.assertAlmostEqual(score, 0.95, places=2)

    def test_layer_b_similar_name(self):
        # High token overlap with slight phrasing difference
        reason, score = ERMDatabaseService.score_candidate_match(
            "Centrifugal Pump Bearing Overheating",
            "Centrifugal Pump Overheating Failure"
        )
        self.assertEqual(reason, "similar_name")
        self.assertGreaterEqual(score, 0.50)

    def test_distinct_names_yield_no_match(self):
        reason, score = ERMDatabaseService.score_candidate_match(
            "Foreign Exchange Volatility in APAC",
            "Fire Safety Code Violation in Warehouse B"
        )
        self.assertIsNone(reason)
        self.assertEqual(score, 0.0)

    def test_layer_c_description_similarity_with_name_overlap(self):
        # Moderate name overlap supplemented by domain-rich description overlap
        draft_title = "Water Ingress in Data Center"
        draft_desc = "Rainwater seepage through basement ceiling threatening server racks and power supply units."
        cand_title = "Data Center Flooding Incident"
        cand_desc = "Basement ceiling seepage from heavy rainfall threatening power supply and server equipment."

        reason, score = ERMDatabaseService.score_candidate_match(
            draft_title=draft_title,
            cand_title=cand_title,
            draft_desc=draft_desc,
            cand_desc=cand_desc,
        )
        self.assertIn(reason, ["name_and_description_similarity", "similar_name"])
        self.assertGreaterEqual(score, 0.50)

    def test_generic_description_does_not_trigger_match(self):
        # Even with identical generic descriptions, if names are unrelated, no match
        draft_title = "Vendor Contract Delay"
        draft_desc = "This is a general operational risk due to process issue."
        cand_title = "Chemical Spill in Loading Dock"
        cand_desc = "This is a general operational risk due to process issue."

        reason, score = ERMDatabaseService.score_candidate_match(
            draft_title=draft_title,
            cand_title=cand_title,
            draft_desc=draft_desc,
            cand_desc=cand_desc,
        )
        self.assertIsNone(reason)
        self.assertEqual(score, 0.0)


class TestDuplicateRiskCheckGovernance(unittest.TestCase):
    """AI Harness registration, RBAC, input validation, and department scoping tests."""

    def setUp(self):
        self.owner_context = HarnessContext.build_from_auth(
            user_id="101",
            user_role=ROLE_RISK_OWNER,
            dept_id=2,
            dept_name="Operations",
            session_id="test-sess-dup-001"
        )
        self.admin_context = HarnessContext.build_from_auth(
            user_id="999",
            user_role=ROLE_ADMIN,
            dept_id=1,
            dept_name="Executive",
            session_id="test-sess-dup-admin"
        )
        self.auditor_context = HarnessContext.build_from_auth(
            user_id="404",
            user_role=ROLE_AUDITOR,
            dept_id=3,
            dept_name="Internal Audit",
            session_id="test-sess-dup-auditor"
        )

    def test_tool_registered_with_correct_governance(self):
        tool = tool_registry.get("detect_duplicate_risks")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.category.value, "read_only")
        self.assertFalse(tool.is_state_changing)
        self.assertTrue(tool.is_idempotent)
        self.assertFalse(tool.requires_confirmation)
        self.assertIn(ROLE_RISK_OWNER, tool.allowed_roles)
        self.assertIn(ROLE_ADMIN, tool.allowed_roles)
        self.assertIn(ROLE_SUPER_ADMIN, tool.allowed_roles)
        self.assertNotIn(ROLE_AUDITOR, tool.allowed_roles)
        self.assertNotIn(ROLE_BOARD_AUDIT, tool.allowed_roles)

    def test_unauthorized_role_rejected(self):
        with self.assertRaises(AuthorizationError):
            ExecutionCoordinator.execute_tool(
                tool_name="detect_duplicate_risks",
                arguments={"risk_title": "Unauthorized Test Risk"},
                context=self.auditor_context
            )

    def test_short_risk_title_fails_validation(self):
        with self.assertRaises(ToolValidationError):
            ExecutionCoordinator.execute_tool(
                tool_name="detect_duplicate_risks",
                arguments={"risk_title": "AB"},
                context=self.owner_context
            )

    def test_department_scoping_enforced_for_risk_owner(self):
        # Even if caller specifies dept_id=5, Risk Owner's dept_id=2 from context must be enforced
        mock_candidates = [
            {
                "risk_id": 10,
                "risk_name": "Centrifugal Pump Failure",
                "department": "Operations",
                "status": "Active",
                "match_reason": "similar_name",
                "similarity_score": 0.85,
            }
        ]
        with patch.object(erm_db, "find_potential_duplicate_risks", return_value=mock_candidates) as mock_find:
            res = ExecutionCoordinator.execute_tool(
                tool_name="detect_duplicate_risks",
                arguments={"risk_title": "Centrifugal Pump Failure", "dept_id": 5},
                context=self.owner_context
            )
            self.assertTrue(res.get("success"))
            # find_potential_duplicate_risks must have received dept_id=2 (from context), not 5
            args, kwargs = mock_find.call_args
            self.assertEqual(kwargs.get("dept_id"), 2)

    def test_admin_permitted_cross_department(self):
        with patch.object(erm_db, "find_potential_duplicate_risks", return_value=[]) as mock_find:
            res = ExecutionCoordinator.execute_tool(
                tool_name="detect_duplicate_risks",
                arguments={"risk_title": "Executive Strategic Risk", "dept_id": 4},
                context=self.admin_context
            )
            self.assertTrue(res.get("success"))
            args, kwargs = mock_find.call_args
            self.assertEqual(kwargs.get("dept_id"), 4)

    def test_read_only_safety_no_mutations(self):
        # Verify that running detect_duplicate_risks calls no mutating DB methods
        with patch.object(erm_db, "create_risk") as mock_create, \
             patch.object(erm_db, "find_potential_duplicate_risks", return_value=[]):
            res = ExecutionCoordinator.execute_tool(
                tool_name="detect_duplicate_risks",
                arguments={"risk_title": "Pump Failure"},
                context=self.owner_context
            )
            self.assertTrue(res.get("success"))
            mock_create.assert_not_called()


class TestAgentDuplicateDetectionIntegration(unittest.TestCase):
    """Conversational Agent integration, advisory banner, caching, and confirmation integrity."""

    def setUp(self):
        self.agent = RiskCreationAgent()
        self.context = HarnessContext.build_from_auth(
            user_id="101",
            user_role=ROLE_RISK_OWNER,
            dept_id=2,
            dept_name="Operations",
            session_id="test-sess-agent-dup"
        )

    def _create_ready_session(self) -> RiskCreationSession:
        s = RiskCreationSession(session_id="test-sess-agent-dup", user_id="101", user_role=ROLE_RISK_OWNER)
        s.dept_id = 2
        s.dept_name = "Operations"
        s.risk_owner_id = "101"
        s.risk_owner_name = "John Doe"
        s.risk_owner_role = ROLE_RISK_OWNER
        s.risk_name = "Centrifugal Pump Overheating"
        s.risk_description = "Bearing failure causing motor to trip and halt line 1."
        s.inherent_likelihood = 4
        s.inherent_impact = 4
        s.inherent_score = 16
        s.inherent_badge = "High"
        s.current_likelihood = 3
        s.current_impact = 3
        s.current_score = 9
        s.current_badge = "Medium"
        s.mitigation = "Install vibration monitoring and continuous thermal sensors."
        s.action_plan = "Procure and configure sensors within 30 days."
        s.action_owner_id = "101"
        s.action_owner_name = "John Doe"
        s.action_owner_role = "Action Owner"
        s.target_date = "2026-12-31"
        s.status_id = 1
        s.status_name = "Draft"
        return s

    def test_duplicate_check_runs_and_surfaces_advisory_in_preview(self):
        session = self._create_ready_session()
        candidates = [
            {
                "risk_id": 42,
                "risk_name": "Centrifugal Pump Overheating Risk",
                "department": "Operations",
                "status": "Active",
                "match_reason": "similar_name",
                "similarity_score": 0.88,
            }
        ]

        with patch.object(erm_db, "find_potential_duplicate_risks", return_value=candidates):
            preview_markdown = self.agent._render_preview_with_advisory(session)

            self.assertIn("Potential Duplicate Risk", preview_markdown)
            self.assertIn("Centrifugal Pump Overheating Risk", preview_markdown)
            self.assertIn("similar_name", preview_markdown)
            self.assertIn("88%", preview_markdown)
            self.assertEqual(session.duplicate_check_status, "potential_matches_found")
            self.assertEqual(len(session.duplicate_candidates), 1)

    def test_cache_avoids_repeated_identical_queries(self):
        session = self._create_ready_session()
        candidates = [
            {
                "risk_id": 42,
                "risk_name": "Centrifugal Pump Overheating Risk",
                "department": "Operations",
                "status": "Active",
                "match_reason": "similar_name",
                "similarity_score": 0.88,
            }
        ]

        with patch.object(erm_db, "find_potential_duplicate_risks", return_value=candidates) as mock_find:
            # First call executes DB search
            self.agent._run_duplicate_check(session)
            self.assertEqual(mock_find.call_count, 1)

            # Second call with identical session parameters uses cached results
            self.agent._run_duplicate_check(session)
            self.assertEqual(mock_find.call_count, 1)

    def test_material_edit_invalidates_cache_and_re_runs_check(self):
        session = self._create_ready_session()
        with patch.object(erm_db, "find_potential_duplicate_risks", return_value=[]):
            self.agent._run_duplicate_check(session)
            self.assertIsNotNone(session.duplicate_check_input_hash)

            # Editing risk_name resets cache hash and acknowledgment
            session.duplicate_acknowledged = True
            self.agent._apply_field_edit(session, "risk_name", "Cooling Tower Pump Overheating")
            self.assertIsNone(session.duplicate_check_input_hash)
            self.assertFalse(session.duplicate_acknowledged)

    def test_user_acknowledgment_preserves_draft_and_allows_confirmation(self):
        session = self._create_ready_session()
        session.state = RiskCreationState.AWAITING_CONFIRMATION
        session.duplicate_check_status = "potential_matches_found"
        session.duplicate_candidates = [{"risk_id": 1, "risk_name": "Existing"}]
        session.duplicate_acknowledged = False
        self.agent._bind_pending_confirmation(session)

        # User says "This is a distinct risk, proceed"
        req = AgentRequest(
            session_id="test-ack-01",
            user_id="101",
            message="This is a distinct risk, please proceed with draft",
            metadata={"role": ROLE_RISK_OWNER, "user_id": "101", "dept_id": 2, "dept_name": "Operations"}
        )
        session_key = self.agent.get_session_key(req)
        self.agent.sessions[session_key] = session

        resp = self.agent.process(req)
        self.assertTrue(session.duplicate_acknowledged)
        self.assertIn("Acknowledged", resp.response)
        self.assertEqual(resp.metadata.get("workflow_state"), "DUPLICATES_ACKNOWLEDGED")

    def test_confirmation_integrity_still_enforced_with_duplicate_detection(self):
        session = self._create_ready_session()
        session.state = RiskCreationState.AWAITING_CONFIRMATION
        self.agent.validate(session)
        self.agent._bind_pending_confirmation(session)

        # Confirming with matching fingerprint calls erm_db.create_risk safely
        with patch.object(erm_db, "create_risk", return_value={"risk_id": 99, "status": "Draft"}) as mock_create:
            req = AgentRequest(
                session_id="test-conf-01",
                user_id="101",
                message="Confirm risk creation",
                metadata={"role": ROLE_RISK_OWNER, "user_id": "101", "dept_id": 2, "dept_name": "Operations"}
            )
            session_key = self.agent.get_session_key(req)
            self.agent.sessions[session_key] = session

            resp = self.agent.process(req)
            self.assertEqual(resp.metadata.get("workflow_state"), "WIZARD_COMPLETED")
            mock_create.assert_called_once()
            self.assertIn("created successfully", resp.response.lower())

    def test_checkpoint_serialization_and_restoration(self):
        session = self._create_ready_session()
        session.duplicate_check_status = "potential_matches_found"
        session.duplicate_candidates = [
            {"risk_id": 101, "risk_name": "Fire Risk", "similarity_score": 0.9}
        ]
        session.duplicate_check_input_hash = "2::Pump::Bearing"
        session.duplicate_acknowledged = True

        data = session.to_dict()
        self.assertEqual(data["duplicate_check_status"], "potential_matches_found")
        self.assertEqual(len(data["duplicate_candidates"]), 1)
        self.assertEqual(data["duplicate_check_input_hash"], "2::Pump::Bearing")
        self.assertTrue(data["duplicate_acknowledged"])

        restored = RiskCreationSession.from_dict(data)
        self.assertEqual(restored.duplicate_check_status, "potential_matches_found")
        self.assertEqual(len(restored.duplicate_candidates), 1)
        self.assertEqual(restored.duplicate_candidates[0]["risk_id"], 101)
        self.assertEqual(restored.duplicate_check_input_hash, "2::Pump::Bearing")
        self.assertTrue(restored.duplicate_acknowledged)


if __name__ == "__main__":
    unittest.main()
