"""
Phase 3 Tests: Deterministic Risk Assessment, Validation, and Final Payload Preparation
1. Field Validation:
   - Missing required fields individually (distinguished from invalid).
   - Empty and whitespace-only text inputs.
   - Text length boundaries (min and max).
   - Out-of-bounds ratings (0, 6, 9, negative, booleans, floats).
   - Invalid target dates.
   - Optional defaults and normalization.
2. Authoritative Risk Scoring:
   - ERM 5x5 Matrix calculation across thresholds (LOW, MEDIUM, HIGH, CRITICAL).
   - Authoritative calculation overrides any LLM/user score.
   - Stale score invalidation upon rating modification.
3. Final Payload Construction:
   - Valid draft produces schema-compatible FinalRiskPayload.
   - Incomplete or invalid draft raises RiskPayloadError.
   - Server context (user_id, dept_id, dept_name) strictly overrides draft or model claims.
   - Treatments structure correctly mapped.
   - Zero database writes during payload construction.
4. Review & Confirmation Integrity:
   - Cryptographic fingerprinting over canonical payload.
   - Material changes (title, ratings, mitigation, owner, target date, status) invalidate confirmation.
   - Mismatch triggers fail-closed behavior, re-binds preview, prevents DB writes.
   - Verified payload is directly unpacked into erm_db.create_risk.
5. Checkpoint & State Consistency:
   - Session serialization and restoration preserve validation and calculated states.
"""
import unittest
from unittest.mock import MagicMock, patch

from ERM_Copilot.agents.risk_creation.agent import RiskCreationAgent
from ERM_Copilot.agents.risk_creation.payload import (
    FinalRiskPayload,
    RiskPayloadError,
    build_final_risk_payload,
)
from ERM_Copilot.agents.risk_creation.scoring import RiskMatrixCalculator
from ERM_Copilot.agents.risk_creation.state import RiskCreationSession, RiskCreationState
from ERM_Copilot.agents.risk_creation.validation import (
    RiskValidationResult,
    validate_risk_draft,
)
from ERM_Copilot.ai_harness.confirmation import confirmation_manager
from ERM_Copilot.ai_harness.exceptions import ConfirmationMismatchError
from ERM_Copilot.models.contracts import AgentRequest
from ERM_Copilot.services.db_service import erm_db


class TestDeterministicFieldValidation(unittest.TestCase):
    """Test deterministic validation boundaries across all risk fields."""

    def setUp(self):
        self.server_ctx = {
            "user_id": 101,
            "role": "Risk Owner",
            "user_role": "Risk Owner",
            "dept_id": 2,
            "dept_name": "Operations",
        }

    def _create_valid_draft(self) -> RiskCreationSession:
        s = RiskCreationSession(session_id="test-val-01", user_id=101, user_role="Risk Owner")
        s.dept_id = 2
        s.dept_name = "Operations"
        s.risk_name = "Centrifugal Pump Bearing Overheating"
        s.risk_description = "Excessive thermal degradation causing pump trip and line shutdown."
        s.inherent_likelihood = 4
        s.inherent_impact = 4
        s.mitigation = "Install infrared continuous thermal imaging and auto-trip interlocks."
        s.current_likelihood = 2
        s.current_impact = 2
        s.action_plan = "Procure and commission vibration and thermal sensors within 30 days."
        s.target_date = "2026-12-31"
        s.progress = 0
        s.status_id = 1
        s.status_name = "Draft"
        return s

    def test_valid_draft_passes_validation(self):
        draft = self._create_valid_draft()
        res = validate_risk_draft(draft, server_context=self.server_ctx)
        self.assertTrue(res.is_valid)
        self.assertTrue(res.is_ready_for_review)
        self.assertEqual(len(res.errors), 0)
        self.assertEqual(len(res.missing_required_fields), 0)
        self.assertEqual(res.normalized_values["risk_name"], "Centrifugal Pump Bearing Overheating")
        self.assertEqual(res.calculated_scores["inherent_score"], 16)
        self.assertEqual(res.calculated_scores["inherent_level"], "CRITICAL")
        self.assertEqual(res.calculated_scores["current_score"], 4)
        self.assertEqual(res.calculated_scores["current_level"], "LOW")

    def test_missing_required_fields_distinguished_individually(self):
        required_fields = [
            "risk_name", "risk_description", "inherent_likelihood", "inherent_impact",
            "mitigation", "current_likelihood", "current_impact", "action_plan"
        ]
        for field_name in required_fields:
            draft = self._create_valid_draft()
            setattr(draft, field_name, None)
            res = validate_risk_draft(draft, server_context=self.server_ctx)
            self.assertFalse(res.is_ready_for_review, f"Draft should not be ready when {field_name} is None")
            self.assertIn(field_name, res.missing_required_fields, f"{field_name} should be in missing_required_fields")
            self.assertNotIn(field_name, res.errors, f"Missing {field_name} should not be treated as invalid syntax")

    def test_empty_and_whitespace_only_strings_flagged_as_errors(self):
        string_fields = ["risk_name", "risk_description", "mitigation", "action_plan"]
        for field_name in string_fields:
            draft = self._create_valid_draft()
            setattr(draft, field_name, "    ")
            res = validate_risk_draft(draft, server_context=self.server_ctx)
            self.assertFalse(res.is_valid)
            self.assertIn(field_name, res.errors)
            self.assertIn("cannot be empty", res.errors[field_name].lower())

    def test_string_length_boundaries(self):
        draft = self._create_valid_draft()
        draft.risk_name = "AB"  # Min 3
        res = validate_risk_draft(draft, server_context=self.server_ctx)
        self.assertIn("risk_name", res.errors)
        self.assertIn("at least 3 characters", res.errors["risk_name"])

        draft = self._create_valid_draft()
        draft.risk_description = "Fail"  # Min 5
        res = validate_risk_draft(draft, server_context=self.server_ctx)
        self.assertIn("risk_description", res.errors)
        self.assertIn("at least 5 characters", res.errors["risk_description"])

    def test_out_of_bounds_ratings_flagged_without_clamping(self):
        invalid_ratings = [0, 6, 9, -1, 10, True, False, "invalid"]
        for inv in invalid_ratings:
            draft = self._create_valid_draft()
            draft.inherent_likelihood = inv
            res = validate_risk_draft(draft, server_context=self.server_ctx)
            self.assertFalse(res.is_valid, f"Rating {inv} should fail validation")
            self.assertIn("inherent_likelihood", res.errors)
            self.assertIsNone(res.calculated_scores.get("inherent_score"))

    def test_invalid_target_date_format_flagged(self):
        draft = self._create_valid_draft()
        draft.target_date = "31-12-2026"  # Not YYYY-MM-DD
        res = validate_risk_draft(draft, server_context=self.server_ctx)
        self.assertIn("target_date", res.errors)
        self.assertIn("YYYY-MM-DD", res.errors["target_date"])

    def test_optional_defaults_applied(self):
        draft = self._create_valid_draft()
        draft.action_owner_id = None
        draft.target_date = None
        draft.progress = None
        res = validate_risk_draft(draft, server_context=self.server_ctx)
        self.assertTrue(res.is_valid)
        self.assertEqual(res.normalized_values["action_owner_id"], 101)  # Defaulted to risk owner
        self.assertEqual(res.normalized_values["progress"], 0)
        self.assertTrue(len(res.warnings) >= 1)


class TestAuthoritativeRiskScoring(unittest.TestCase):
    """Test 5x5 ERM Matrix calculation, threshold classifications, and stale invalidation."""

    def test_matrix_threshold_classifications(self):
        # LOW: score < 5
        score, lvl, badge = RiskMatrixCalculator.calculate_score(1, 1)
        self.assertEqual(score, 1)
        self.assertEqual(lvl, "LOW")

        score, lvl, badge = RiskMatrixCalculator.calculate_score(2, 2)
        self.assertEqual(score, 4)
        self.assertEqual(lvl, "LOW")

        # MEDIUM: 5 <= score < 10
        score, lvl, badge = RiskMatrixCalculator.calculate_score(1, 5)
        self.assertEqual(score, 5)
        self.assertEqual(lvl, "MEDIUM")

        score, lvl, badge = RiskMatrixCalculator.calculate_score(3, 3)
        self.assertEqual(score, 9)
        self.assertEqual(lvl, "MEDIUM")

        # HIGH: 10 <= score < 15
        score, lvl, badge = RiskMatrixCalculator.calculate_score(2, 5)
        self.assertEqual(score, 10)
        self.assertEqual(lvl, "HIGH")

        score, lvl, badge = RiskMatrixCalculator.calculate_score(3, 4)
        self.assertEqual(score, 12)
        self.assertEqual(lvl, "HIGH")

        # CRITICAL: score >= 15
        score, lvl, badge = RiskMatrixCalculator.calculate_score(3, 5)
        self.assertEqual(score, 15)
        self.assertEqual(lvl, "CRITICAL")

        score, lvl, badge = RiskMatrixCalculator.calculate_score(4, 4)
        self.assertEqual(score, 16)
        self.assertEqual(lvl, "CRITICAL")

        score, lvl, badge = RiskMatrixCalculator.calculate_score(5, 5)
        self.assertEqual(score, 25)
        self.assertEqual(lvl, "CRITICAL")

    def test_strict_rating_validation_raises_error(self):
        with self.assertRaises(ValueError):
            RiskMatrixCalculator.calculate_score(0, 5, strict=True)
        with self.assertRaises(ValueError):
            RiskMatrixCalculator.calculate_score(6, 4, strict=True)
        with self.assertRaises(ValueError):
            RiskMatrixCalculator.calculate_score(-2, 3, strict=True)

    def test_stale_score_invalidation_in_session(self):
        s = RiskCreationSession(session_id="test-sc-01", user_id=101, user_role="Risk Owner")
        # Initially valid
        s.update_inherent_assessment(4, 4)
        self.assertEqual(s.inherent_score, 16)
        self.assertEqual(s.inherent_level, "CRITICAL")

        # Inherent rating changed to None or invalid -> stale scores cleared
        s.update_inherent_assessment(None, 4)
        self.assertIsNone(s.inherent_score)
        self.assertIsNone(s.inherent_level)
        self.assertIsNone(s.inherent_badge)

        s.update_current_assessment(3, 3)
        self.assertEqual(s.current_score, 9)
        s.update_current_assessment(7, 3)  # Out of range 7
        self.assertIsNone(s.current_score)
        self.assertIsNone(s.current_level)


class TestFinalPayloadConstruction(unittest.TestCase):
    """Test deterministic final payload builder, schema mapping, and server-context enforcement."""

    def setUp(self):
        self.server_ctx = {
            "user_id": 101,
            "role": "Risk Owner",
            "user_role": "Risk Owner",
            "dept_id": 2,
            "dept_name": "Operations",
        }

    def _create_valid_session(self) -> RiskCreationSession:
        s = RiskCreationSession(session_id="test-pld-01", user_id=101, user_role="Risk Owner")
        s.dept_id = 2
        s.dept_name = "Operations"
        s.risk_name = "Pipeline Wall Thinning Hazard"
        s.risk_description = "Internal H2S acidic corrosion causing wall thinning on crude transfer line."
        s.inherent_likelihood = 5
        s.inherent_impact = 3
        s.inherent_score = 15
        s.inherent_level = "CRITICAL"
        s.mitigation = "Chemical corrosion inhibitor injection and quarterly ultrasonic thickness scans."
        s.current_likelihood = 2
        s.current_impact = 2
        s.current_score = 4
        s.current_level = "LOW"
        s.action_plan = "Perform ultrasonic NDT testing on spool segments 10 through 18."
        s.action_owner_id = 101
        s.target_date = "2026-11-30"
        s.progress = 10
        s.status_id = 1
        s.status_name = "Draft"
        return s

    def test_build_final_risk_payload_success(self):
        s = self._create_valid_session()
        payload = build_final_risk_payload(s, self.server_ctx)
        self.assertIsInstance(payload, FinalRiskPayload)
        self.assertEqual(payload.risk_name, "Pipeline Wall Thinning Hazard")
        self.assertEqual(payload.risk_owner_id, 101)
        self.assertEqual(payload.dept_id, 2)
        self.assertEqual(payload.inherent_score, 15)
        self.assertEqual(payload.inherent_level, "CRITICAL")
        self.assertEqual(payload.current_score, 4)
        self.assertEqual(payload.current_level, "LOW")
        self.assertEqual(len(payload.treatments), 1)
        self.assertEqual(payload.treatments[0]["action_owner_id"], 101)

    def test_untrusted_identity_cannot_override_server_context(self):
        s = self._create_valid_session()
        # Malicious or confused conversational session claiming user_id 999 and dept 99
        s.user_id = 999
        s.dept_id = 99
        s.dept_name = "Invented Dept"

        payload = build_final_risk_payload(s, self.server_ctx)
        self.assertEqual(payload.risk_owner_id, 101, "Server context user_id must override draft user_id")
        self.assertEqual(payload.dept_id, 2, "Server context dept_id must override draft dept_id")
        self.assertEqual(payload.dept_name, "Operations")

    def test_incomplete_draft_raises_payload_error(self):
        s = self._create_valid_session()
        s.action_plan = None
        with self.assertRaises(RiskPayloadError) as ctx:
            build_final_risk_payload(s, self.server_ctx)
        self.assertIn("action plan", str(ctx.exception).lower())

    def test_db_kwargs_matches_db_service_signature(self):
        s = self._create_valid_session()
        payload = build_final_risk_payload(s, self.server_ctx)
        db_kwargs = payload.to_db_kwargs()

        expected_keys = {
            "risk_name", "risk_description", "dept_id", "dept_name",
            "risk_owner_id", "risk_co_owner_id", "inherent_likelihood",
            "inherent_impact", "current_likelihood", "current_impact",
            "mitigation", "status", "financial_year", "treatments"
        }
        self.assertEqual(set(db_kwargs.keys()), expected_keys)

    def test_payload_builder_performs_zero_database_writes(self):
        s = self._create_valid_session()
        with patch.object(erm_db, "create_risk") as mock_create:
            build_final_risk_payload(s, self.server_ctx)
            mock_create.assert_not_called()


class TestConfirmationIntegrityAndTamperProtection(unittest.TestCase):
    """Test cryptographic fingerprint binding, tamper detection, and fail-closed persistence."""

    def setUp(self):
        self.agent = RiskCreationAgent()
        self.server_ctx = {
            "user_id": 101,
            "role": "Risk Owner",
            "user_role": "Risk Owner",
            "dept_id": 2,
            "dept_name": "Operations",
        }

    def _create_ready_session(self) -> RiskCreationSession:
        s = RiskCreationSession(session_id="test-conf-integ", user_id=101, user_role="Risk Owner")
        s.dept_id = 2
        s.dept_name = "Operations"
        s.risk_name = "High Pressure Gas Pipeline Leak"
        s.risk_description = "Flange gasket rupture causing pressurized methane release."
        s.inherent_likelihood = 4
        s.inherent_impact = 5
        s.inherent_score = 20
        s.inherent_level = "CRITICAL"
        s.mitigation = "Dual isolation valves, automatic gas leak detectors, and acoustic monitors."
        s.current_likelihood = 2
        s.current_impact = 3
        s.current_score = 6
        s.current_level = "MEDIUM"
        s.action_plan = "Replace seal ring gaskets on manifold flange MF-04."
        s.action_owner_id = 101
        s.target_date = "2026-12-15"
        s.progress = 0
        s.status_id = 1
        s.status_name = "Draft"
        return s

    def test_confirmation_succeeds_for_exact_reviewed_payload(self):
        session = self._create_ready_session()
        session.state = RiskCreationState.AWAITING_CONFIRMATION
        self.agent._bind_pending_confirmation(session)

        with patch.object(erm_db, "create_risk", return_value={"status": "success", "risk_id": "RSK-OP-001"}) as mock_create:
            req = AgentRequest(
                session_id="test-conf-integ",
                user_id="101",
                message="Confirm risk creation",
                metadata={"role": "Risk Owner", "user_id": 101, "dept_id": 2, "dept_name": "Operations"}
            )
            session_key = self.agent.get_session_key(req)
            self.agent.sessions[session_key] = session

            resp = self.agent.process(req)
            self.assertEqual(resp.metadata.get("workflow_state"), "WIZARD_COMPLETED")
            mock_create.assert_called_once()
            # Verify that create_risk was called with exact validated payload kwargs
            kwargs = mock_create.call_args.kwargs
            self.assertEqual(kwargs["risk_name"], "High Pressure Gas Pipeline Leak")
            self.assertEqual(kwargs["inherent_likelihood"], 4)
            self.assertEqual(kwargs["inherent_impact"], 5)
            self.assertEqual(kwargs["current_likelihood"], 2)
            self.assertEqual(kwargs["current_impact"], 3)

    def test_changed_risk_name_invalidates_confirmation(self):
        session = self._create_ready_session()
        session.state = RiskCreationState.AWAITING_CONFIRMATION
        self.agent._bind_pending_confirmation(session)

        # User or attacker modifies risk_name between preview and confirmation
        session.risk_name = "Modified Pipeline Hazard Tampered"

        with patch.object(erm_db, "create_risk") as mock_create:
            req = AgentRequest(
                session_id="test-conf-integ",
                user_id="101",
                message="Confirm and save",
                metadata={"role": "Risk Owner", "user_id": 101, "dept_id": 2, "dept_name": "Operations"}
            )
            session_key = self.agent.get_session_key(req)
            self.agent.sessions[session_key] = session

            resp = self.agent.process(req)
            # Confirmation must be rejected due to fingerprint mismatch
            self.assertEqual(resp.metadata.get("workflow_state"), "WIZARD_CONFIRMATION")
            self.assertIn("Confirmation Verification Notice", resp.response)
            mock_create.assert_not_called()

    def test_changed_rating_invalidates_confirmation(self):
        session = self._create_ready_session()
        session.state = RiskCreationState.AWAITING_CONFIRMATION
        self.agent._bind_pending_confirmation(session)

        # Rating changed after preview generated
        session.inherent_likelihood = 2
        session.inherent_score = 10

        with patch.object(erm_db, "create_risk") as mock_create:
            req = AgentRequest(
                session_id="test-conf-integ",
                user_id="101",
                message="Confirm",
                metadata={"role": "Risk Owner", "user_id": 101, "dept_id": 2, "dept_name": "Operations"}
            )
            session_key = self.agent.get_session_key(req)
            self.agent.sessions[session_key] = session

            resp = self.agent.process(req)
            self.assertIn("Confirmation Verification Notice", resp.response)
            mock_create.assert_not_called()

    def test_field_edit_clears_pending_confirmation(self):
        session = self._create_ready_session()
        session.state = RiskCreationState.AWAITING_CONFIRMATION
        self.agent._bind_pending_confirmation(session)
        self.assertIsNotNone(session.pending_confirmation)

        # Applying edit clears pending confirmation
        self.agent._apply_field_edit(session, "target_date", "2027-01-15")
        self.assertIsNone(session.pending_confirmation)
        self.assertFalse(session.awaiting_confirmation)

    def test_generic_affirmative_without_pending_token_fails_closed(self):
        session = self._create_ready_session()
        session.state = RiskCreationState.AWAITING_CONFIRMATION
        session.pending_confirmation = None  # No active confirmation token

        with patch.object(erm_db, "create_risk") as mock_create:
            req = AgentRequest(
                session_id="test-conf-integ",
                user_id="101",
                message="Yes, please save it",
                metadata={"role": "Risk Owner", "user_id": 101, "dept_id": 2, "dept_name": "Operations"}
            )
            session_key = self.agent.get_session_key(req)
            self.agent.sessions[session_key] = session

            resp = self.agent.process(req)
            self.assertIn("Confirmation Verification Notice", resp.response)
            mock_create.assert_not_called()


class TestStateAndCheckpointConsistency(unittest.TestCase):
    """Test session serialization, checkpoint durability, and state reconstruction."""

    def test_session_serialization_and_restoration_preserves_validated_state(self):
        s = RiskCreationSession(session_id="test-chk-01", user_id=101, user_role="Risk Owner")
        s.dept_id = 2
        s.dept_name = "Operations"
        s.risk_name = "Pump Seal Leak"
        s.risk_description = "Mechanical seal failure resulting in hydrocarbon drip."
        s.inherent_likelihood = 3
        s.inherent_impact = 4
        s.inherent_score = 12
        s.inherent_level = "HIGH"
        s.current_likelihood = 2
        s.current_impact = 2
        s.current_score = 4
        s.current_level = "LOW"
        s.mitigation = "Secondary containment pan and drain connection."
        s.action_plan = "Replace seal faces with tungsten carbide components."
        s.action_owner_id = 101
        s.target_date = "2026-12-31"
        s.progress = 0
        s.status_id = 1
        s.status_name = "Draft"
        s.field_provenance["risk_name"] = "user_stated"
        s.field_provenance["inherent_score"] = "calculated"

        data = s.to_dict()
        restored = RiskCreationSession.from_dict(data)

        self.assertEqual(restored.session_id, "test-chk-01")
        self.assertEqual(restored.user_id, 101)
        self.assertEqual(restored.dept_id, 2)
        self.assertEqual(restored.risk_name, "Pump Seal Leak")
        self.assertEqual(restored.inherent_score, 12)
        self.assertEqual(restored.inherent_level, "HIGH")
        self.assertEqual(restored.current_score, 4)
        self.assertEqual(restored.current_level, "LOW")
        self.assertEqual(restored.field_provenance.get("inherent_score"), "calculated")


if __name__ == "__main__":
    unittest.main()
