"""
Phase 2 Slice 1 Tests:
1. get_dropdown_options service & error handling
2. resolve_reference_data tool & schema validation
3. lookup_eligible_owners tool & department RBAC scoping
4. Confirmation fingerprint integrity & anti-tampering protection
"""
import time
import unittest
from unittest.mock import MagicMock, patch

from ERM_Copilot.agents.risk_creation.agent import RiskCreationAgent
from ERM_Copilot.agents.risk_creation.state import RiskCreationSession, RiskCreationState
from ERM_Copilot.agents.risk_creation.scoring import RiskMatrixCalculator
from ERM_Copilot.ai_harness.confirmation import confirmation_manager
from ERM_Copilot.ai_harness.context import HarnessContext
from ERM_Copilot.ai_harness.exceptions import (
    ConfirmationMismatchError,
    ToolValidationError,
)
from ERM_Copilot.ai_harness.execution import ExecutionCoordinator
from ERM_Copilot.ai_harness.tool_registry import tool_registry
from ERM_Copilot.models.contracts import AgentRequest
from ERM_Copilot.services.db_service import ERMDatabaseService, erm_db


class TestDropdownOptionsService(unittest.TestCase):
    """Tests for ERMDatabaseService.get_dropdown_options."""

    def test_dropdown_options_returns_expected_structure(self):
        result = erm_db.get_dropdown_options(dept_id=1)
        self.assertEqual(result.get("status"), "success")
        self.assertIn("departments", result)
        self.assertIn("statuses", result)
        self.assertIn("likelihood_scales", result)
        self.assertIn("impact_scales", result)
        self.assertIn("action_owners", result)

        # Verify likelihood scales match 5x5 matrix
        self.assertEqual(len(result["likelihood_scales"]), 5)
        self.assertEqual(result["likelihood_scales"][0]["name"], "Remote")
        self.assertEqual(result["likelihood_scales"][4]["name"], "Expected")

        # Verify impact scales match 5x5 matrix
        self.assertEqual(len(result["impact_scales"]), 5)
        self.assertEqual(result["impact_scales"][0]["name"], "Negligible")
        self.assertEqual(result["impact_scales"][4]["name"], "Extreme")

    def test_dropdown_options_department_scoping(self):
        with patch.object(
            erm_db,
            "get_department_action_owners",
            return_value=[
                {"user_id": 10, "log_id": "ao_gas", "full_name": "Gas AO", "dept_id": 2, "role_name": "Action Owner", "email": "ao@gas.com"}
            ]
        ) as mock_get_owners:
            res = erm_db.get_dropdown_options(dept_id=2)
            mock_get_owners.assert_called_once_with(dept_id=2)
            self.assertEqual(len(res["action_owners"]), 1)
            self.assertEqual(res["action_owners"][0]["user_id"], 10)
            # Ensure email is not exposed in sanitized action owners
            self.assertNotIn("email", res["action_owners"][0])

    def test_dropdown_options_handles_db_connection_error_gracefully(self):
        service = ERMDatabaseService()
        with patch.object(service, "_get_connection", side_effect=Exception("Database unreachable")):
            res = service.get_dropdown_options(dept_id=1)
            self.assertEqual(res["status"], "success")
            self.assertIsInstance(res["departments"], list)
            # Static scales still available from RiskMatrixCalculator
            self.assertEqual(len(res["likelihood_scales"]), 5)
            self.assertEqual(len(res["impact_scales"]), 5)


class TestResolveReferenceDataTool(unittest.TestCase):
    """Tests for resolve_reference_data tool registered in AI Harness."""

    def setUp(self):
        self.context = HarnessContext.build_from_auth(
            user_id="101",
            user_role="Risk Owner",
            dept_id=1,
            dept_name="HSE",
        )

    def test_tool_registered_with_read_only_governance(self):
        tool = tool_registry.get("resolve_reference_data")
        self.assertEqual(tool.category.value, "read_only")
        self.assertFalse(tool.requires_confirmation)
        self.assertFalse(tool.is_state_changing)
        self.assertTrue(tool.is_idempotent)
        self.assertIsNotNone(tool.schema_model)

    @patch.object(erm_db, "get_status_options", return_value=[{"id": 1, "status_name": "Draft"}, {"id": 2, "status_name": "Submitted to Functional Head"}])
    def test_resolve_status_dataset(self, mock_status):
        res = ExecutionCoordinator.execute_tool(
            tool_name="resolve_reference_data",
            arguments={"dataset": "status"},
            context=self.context,
        )
        self.assertTrue(res["success"])
        data = res["result"]
        self.assertEqual(data["dataset"], "status")
        self.assertIn("data", data)
        self.assertTrue(len(data["data"]) > 0)

    def test_resolve_departments_dataset(self):
        res = ExecutionCoordinator.execute_tool(
            tool_name="resolve_reference_data",
            arguments={"dataset": "departments"},
            context=self.context,
        )
        self.assertTrue(res["success"])
        data = res["result"]
        self.assertEqual(data["dataset"], "departments")
        self.assertIn("data", data)

    def test_resolve_assessment_criteria_dataset(self):
        res = ExecutionCoordinator.execute_tool(
            tool_name="resolve_reference_data",
            arguments={"dataset": "assessment_criteria"},
            context=self.context,
        )
        self.assertTrue(res["success"])
        data = res["result"]
        self.assertEqual(data["dataset"], "assessment_criteria")
        self.assertIn("likelihood_scales", data)
        self.assertIn("impact_scales", data)
        self.assertIn("matrix_bands", data)

    def test_resolve_all_datasets(self):
        res = ExecutionCoordinator.execute_tool(
            tool_name="resolve_reference_data",
            arguments={"dataset": "all"},
            context=self.context,
        )
        self.assertTrue(res["success"])
        data = res["result"]
        self.assertEqual(data["dataset"], "all")
        self.assertIn("departments", data)
        self.assertIn("statuses", data)
        self.assertIn("likelihood_scales", data)
        self.assertIn("impact_scales", data)

    def test_invalid_dataset_raises_validation_error(self):
        with self.assertRaises(ToolValidationError):
            ExecutionCoordinator.execute_tool(
                tool_name="resolve_reference_data",
                arguments={"dataset": "invented_table"},
                context=self.context,
            )


class TestLookupEligibleOwnersTool(unittest.TestCase):
    """Tests for lookup_eligible_owners tool registered in AI Harness."""

    def test_tool_registered_with_governance(self):
        tool = tool_registry.get("lookup_eligible_owners")
        self.assertEqual(tool.category.value, "read_only")
        self.assertFalse(tool.requires_confirmation)
        self.assertFalse(tool.is_state_changing)
        self.assertTrue(tool.is_idempotent)
        self.assertIsNotNone(tool.schema_model)

    def test_action_owner_restricted_to_authenticated_department(self):
        """Standard user cannot query action owners from another department."""
        context = HarnessContext.build_from_auth(
            user_id="101",
            user_role="Risk Owner",
            dept_id=2,
            dept_name="Gas Processing",
        )
        with patch.object(
            erm_db,
            "get_department_action_owners",
            return_value=[
                {"user_id": 20, "log_id": "ao_gas", "full_name": "Gas AO", "dept_id": 2, "role_name": "Action Owner"}
            ]
        ) as mock_ao:
            # Caller attempts to supply dept_id=5 (trying to bypass department isolation)
            res = ExecutionCoordinator.execute_tool(
                tool_name="lookup_eligible_owners",
                arguments={"owner_type": "action_owner", "dept_id": 5},
                context=context,
            )
            self.assertTrue(res["success"])
            # Enforced to caller's dept_id=2, NOT the manipulated dept_id=5
            mock_ao.assert_called_once_with(dept_id=2)
            self.assertEqual(res["result"]["dept_id"], 2)

    def test_admin_permitted_cross_department_action_owner_lookup(self):
        """Admin is authorized to specify a target department."""
        context = HarnessContext.build_from_auth(
            user_id="1",
            user_role="Admin",
            dept_id=1,
            dept_name="Corporate",
        )
        with patch.object(
            erm_db,
            "get_department_action_owners",
            return_value=[
                {"user_id": 50, "log_id": "ao_drilling", "full_name": "Drilling AO", "dept_id": 4, "role_name": "Action Owner"}
            ]
        ) as mock_ao:
            res = ExecutionCoordinator.execute_tool(
                tool_name="lookup_eligible_owners",
                arguments={"owner_type": "action_owner", "dept_id": 4},
                context=context,
            )
            self.assertTrue(res["success"])
            mock_ao.assert_called_once_with(dept_id=4)
            self.assertEqual(res["result"]["dept_id"], 4)

    def test_co_owner_enterprise_wide_lookup(self):
        """Co-owner lookup queries enterprise personnel across departments."""
        context = HarnessContext.build_from_auth(
            user_id="101",
            user_role="Risk Owner",
            dept_id=2,
            dept_name="Gas Processing",
        )
        with patch.object(
            erm_db,
            "get_all_users_for_co_owner",
            return_value=[
                {"user_id": 30, "log_id": "co_refinery", "full_name": "Refinery Manager", "dept_id": 3, "role_name": "Risk Owner"}
            ]
        ) as mock_co:
            res = ExecutionCoordinator.execute_tool(
                tool_name="lookup_eligible_owners",
                arguments={"owner_type": "co_owner"},
                context=context,
            )
            self.assertTrue(res["success"])
            mock_co.assert_called_once_with(limit=50)
            self.assertEqual(res["result"]["count"], 1)

    def test_search_term_filters_candidates(self):
        context = HarnessContext.build_from_auth(
            user_id="101",
            user_role="Risk Owner",
            dept_id=1,
        )
        with patch.object(
            erm_db,
            "get_department_action_owners",
            return_value=[
                {"user_id": 1, "log_id": "sunil_ao", "full_name": "Sunil Yadav", "dept_id": 1, "role_name": "Action Owner"},
                {"user_id": 2, "log_id": "vikram_ao", "full_name": "Vikram Singh", "dept_id": 1, "role_name": "Action Owner"},
            ]
        ):
            res = ExecutionCoordinator.execute_tool(
                tool_name="lookup_eligible_owners",
                arguments={"owner_type": "action_owner", "search_term": "Sunil"},
                context=context,
            )
            self.assertTrue(res["success"])
            owners = res["result"]["owners"]
            self.assertEqual(len(owners), 1)
            self.assertEqual(owners[0]["full_name"], "Sunil Yadav")

    def test_pii_sanitization_excludes_email(self):
        context = HarnessContext.build_from_auth(
            user_id="101",
            user_role="Risk Owner",
            dept_id=1,
        )
        with patch.object(
            erm_db,
            "get_department_action_owners",
            return_value=[
                {"user_id": 1, "log_id": "user1", "full_name": "Test User", "dept_id": 1, "role_name": "Action Owner", "email": "secret@corp.com"}
            ]
        ):
            res = ExecutionCoordinator.execute_tool(
                tool_name="lookup_eligible_owners",
                arguments={"owner_type": "action_owner"},
                context=context,
            )
            self.assertTrue(res["success"])
            owner = res["result"]["owners"][0]
            self.assertNotIn("email", owner)

    def test_invalid_owner_type_raises_validation_error(self):
        context = HarnessContext.build_from_auth(
            user_id="101",
            user_role="Risk Owner",
            dept_id=1,
        )
        with self.assertRaises(ToolValidationError):
            ExecutionCoordinator.execute_tool(
                tool_name="lookup_eligible_owners",
                arguments={"owner_type": "unauthorized_owner_type"},
                context=context,
            )


class TestConfirmationFingerprintIntegrity(unittest.TestCase):
    """
    Tests ensuring risk creation confirmation is strictly cryptographically bound
    to the exact previewed payload using ConfirmationManager.
    """

    def setUp(self):
        self.agent = RiskCreationAgent()
        self.user_id = "test_user_777"
        self.session_key = self.user_id
        self.agent.clear_session(self.session_key)
        self.meta = {
            "role": "Risk Owner",
            "user_id": self.user_id,
            "dept_id": 2,
            "dept_name": "Gas Processing",
        }

    def _setup_preview_session(self) -> RiskCreationSession:
        """Helper to create a complete session ready for confirmation."""
        sess = RiskCreationSession(
            session_id="sess-conf-test-01",
            user_id=self.user_id,
            user_role="Risk Owner",
            dept_id=2,
            dept_name="Gas Processing",
            risk_name="Gas Pipeline Flange Leak",
            risk_description="Minor hydrocarbon vapor release at flange joint F-102.",
            inherent_likelihood=3,
            inherent_impact=4,
            inherent_score=12,
            inherent_level="HIGH",
            inherent_badge="[HIGH]",
            mitigation="Periodic ultrasonic thickness testing and torque check.",
            current_likelihood=2,
            current_impact=2,
            current_score=4,
            current_level="LOW",
            current_badge="[LOW]",
            action_plan="Replace spiral-wound gasket with graphite packing.",
            action_owner_id=5,
            action_owner_name="Sunil Yadav",
            target_date="2026-12-31",
            status_id=1,
            status_name="Draft",
            progress=0,
            state=RiskCreationState.AWAITING_CONFIRMATION,
        )
        self.session_key = f"{self.user_id}::{sess.session_id}"
        self.agent.sessions[self.session_key] = sess
        # Bind pending confirmation exactly as preview generation does
        self.agent._bind_pending_confirmation(sess)
        return sess

    def test_valid_confirmation_creates_risk_and_marks_executed(self):
        sess = self._setup_preview_session()

        with patch("ERM_Copilot.agents.risk_creation.agent.erm_db.create_risk") as mock_create:
            mock_create.return_value = {
                "status": "success",
                "risk_id": "RSK-GAS-2026-099",
                "risk_register_id": 42,
            }
            req = AgentRequest(
                message="confirm",
                user_id=self.user_id,
                user_role="Risk Owner",
                session_id=sess.session_id,
                metadata=self.meta,
            )
            resp = self.agent.process(req)

            self.assertIn("Risk Created Successfully", resp.response)
            self.assertIn("RSK-GAS-2026-099", resp.response)
            mock_create.assert_called_once()
            # Session must be cleared upon successful creation
            self.assertFalse(self.agent.is_session_active(self.session_key))

    def test_tampered_payload_blocks_database_write(self):
        """If risk rating is tampered between preview and confirmation, DB write is blocked."""
        sess = self._setup_preview_session()
        # Malicious modification: change inherent rating from 3x4 to 1x1 without triggering preview
        sess.inherent_likelihood = 1
        sess.inherent_impact = 1
        sess.inherent_score = 1

        with patch("ERM_Copilot.agents.risk_creation.agent.erm_db.create_risk") as mock_create:
            req = AgentRequest(
                message="confirm",
                user_id=self.user_id,
                user_role="Risk Owner",
                session_id=sess.session_id,
                metadata=self.meta,
            )
            resp = self.agent.process(req)

            # Assert database write was NOT invoked
            mock_create.assert_not_called()
            # Assert confirmation was rejected with verification notice
            self.assertIn("Confirmation Verification Notice", resp.response)
            self.assertIn("tampered or mismatched", resp.response)
            # Session is still active in AWAITING_CONFIRMATION with a newly bound fingerprint
            self.assertTrue(self.agent.is_session_active(self.session_key))

    def test_tampered_action_owner_blocks_database_write(self):
        sess = self._setup_preview_session()
        # Tamper action owner ID
        sess.action_owner_id = 9999

        with patch("ERM_Copilot.agents.risk_creation.agent.erm_db.create_risk") as mock_create:
            req = AgentRequest(
                message="confirm",
                user_id=self.user_id,
                user_role="Risk Owner",
                session_id=sess.session_id,
                metadata=self.meta,
            )
            resp = self.agent.process(req)

            mock_create.assert_not_called()
            self.assertIn("Confirmation Verification Notice", resp.response)

    def test_tampered_department_blocks_database_write(self):
        sess = self._setup_preview_session()
        # Tamper department ID
        sess.dept_id = 99

        with patch("ERM_Copilot.agents.risk_creation.agent.erm_db.create_risk") as mock_create:
            req = AgentRequest(
                message="confirm",
                user_id=self.user_id,
                user_role="Risk Owner",
                session_id=sess.session_id,
                metadata=self.meta,
            )
            resp = self.agent.process(req)

            mock_create.assert_not_called()
            self.assertIn("Confirmation Verification Notice", resp.response)

    def test_expired_confirmation_blocks_database_write(self):
        sess = self._setup_preview_session()
        # Backdate expiration by 20 minutes
        sess.pending_confirmation["expires_at"] = time.time() - 1200

        with patch("ERM_Copilot.agents.risk_creation.agent.erm_db.create_risk") as mock_create:
            req = AgentRequest(
                message="confirm",
                user_id=self.user_id,
                user_role="Risk Owner",
                session_id=sess.session_id,
                metadata=self.meta,
            )
            resp = self.agent.process(req)

            mock_create.assert_not_called()
            self.assertIn("Confirmation Verification Notice", resp.response)
            self.assertIn("expired", resp.response)

    def test_missing_confirmation_state_blocks_database_write(self):
        sess = self._setup_preview_session()
        # Strip pending confirmation state
        sess.pending_confirmation = None

        with patch("ERM_Copilot.agents.risk_creation.agent.erm_db.create_risk") as mock_create:
            req = AgentRequest(
                message="confirm",
                user_id=self.user_id,
                user_role="Risk Owner",
                session_id=sess.session_id,
                metadata=self.meta,
            )
            resp = self.agent.process(req)

            mock_create.assert_not_called()
            self.assertIn("Confirmation Verification Notice", resp.response)
            self.assertIn("No pending confirmation state found", resp.response)

    def test_checkpoint_restoration_preserves_valid_confirmation(self):
        """Simulate saving session to checkpoint store and resuming."""
        sess = self._setup_preview_session()
        serialized = sess.to_dict()

        # Re-create session from serialized dictionary
        restored = RiskCreationSession.from_dict(serialized)
        self.agent.sessions[self.session_key] = restored

        with patch("ERM_Copilot.agents.risk_creation.agent.erm_db.create_risk") as mock_create:
            mock_create.return_value = {
                "status": "success",
                "risk_id": "RSK-GAS-2026-RESTORED",
                "risk_register_id": 99,
            }
            req = AgentRequest(
                message="confirm",
                user_id=self.user_id,
                user_role="Risk Owner",
                session_id=restored.session_id,
                metadata=self.meta,
            )
            resp = self.agent.process(req)

            self.assertIn("Risk Created Successfully", resp.response)
            mock_create.assert_called_once()


if __name__ == "__main__":
    unittest.main()
