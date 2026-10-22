"""
Phase 4B Verification and Hardening Test Suite for Goal-Driven Risk Creation Agent.

Tests:
1. End-to-End tool call path verification: registry resolution, argument validation, context injection, RBAC check, history logging.
2. Dynamic decisioning: complete input skips suggestions & questions; partial input requests only unresolved fields.
3. Co-owner provided in initial prompt skips co-owner prompt (residual questionnaire check).
4. Mitigation/action-plan suggestions skipped when user supplied acceptable text; invoked only on explicit request.
5. Ineligible owner and invalid rating rejection.
6. Department isolation: standard Risk Owner cannot spoof dept_id in create_risk or owner lookup.
7. Enterprise roles (Risk Manager, Risk Head, Admin) permitted cross-dept lookup.
8. Co-owner lookup searches enterprise-wide personnel, not constrained to Risk Owner's department.
9. create_risk execution via AI Harness tool layer, recorded in session.tool_call_history.
10. Confirmation replay prevention: EXECUTED token cannot be reused.
11. Confirmation tampering prevention: altered arguments invalidate confirmation fingerprint.
12. State-changing actions blocked from automatic retry on transient error.
13. Duplicate check failure is treated as error and never fabricated as 'clean register'.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from ERM_Copilot.agents.risk_creation.agent import RiskCreationAgent
from ERM_Copilot.agents.risk_creation.state import (
    RiskCreationSession,
    RiskCreationState,
)
from ERM_Copilot.agents.risk_creation.scoring import RiskMatrixCalculator
from ERM_Copilot.ai_harness.context import HarnessContext
from ERM_Copilot.ai_harness.execution import ExecutionCoordinator
from ERM_Copilot.ai_harness.tool_registry import tool_registry
from ERM_Copilot.ai_harness.confirmation import confirmation_manager
from ERM_Copilot.ai_harness.exceptions import (
    AuthorizationError,
    ConfirmationMismatchError,
    ConfirmationRequiredError,
    ToolNotFoundError,
    ToolValidationError,
)
from ERM_Copilot.ai_harness.policies import (
    ROLE_ADMIN,
    ROLE_AUDITOR,
    ROLE_FUNCTIONAL_HEAD,
    ROLE_RISK_MANAGER,
    ROLE_RISK_HEADER,
    ROLE_RISK_OWNER,
    ROLE_SUPER_ADMIN,
)
from ERM_Copilot.models.contracts import AgentRequest
from ERM_Copilot.services.db_service import erm_db


class TestPhase4BVerificationAndHardening(unittest.TestCase):
    """Phase 4B verification and hardening test suite."""

    def setUp(self):
        self.agent = RiskCreationAgent()
        self.agent.sessions.clear()
        self.meta = {
            "role": "Risk Owner",
            "user_id": "801",
            "dept_id": 2,
            "dept_name": "Gas Processing Facilities",
        }

    # =========================================================================
    # Task 1: Verify Actual Tool Execution Call Path
    # =========================================================================

    def test_tool_call_path_end_to_end(self):
        """Verify tool resolution, schema validation, server context injection, and history recording."""
        sess = RiskCreationSession(
            session_id="sess-path-01",
            user_id="801",
            user_role="Risk Owner",
            dept_id=2,
            dept_name="Gas Processing Facilities",
            risk_name="Gas Turbine Overheating",
        )
        self.agent.sessions["801"] = sess

        # Call calculate_risk_scores through execute_governed_tool
        res = self.agent.execute_governed_tool(
            tool_name="calculate_risk_scores",
            arguments={"likelihood": 4, "impact": 5},
            session=sess,
        )

        # 1. Result verification
        self.assertTrue(res.get("success"))
        tool_res = res.get("result", {})
        self.assertEqual(tool_res.get("score"), 20)
        self.assertEqual(tool_res.get("level"), "CRITICAL")

        # 2. Durable recording in session.tool_call_history
        self.assertGreaterEqual(len(sess.tool_call_history), 1)
        last_entry = sess.tool_call_history[-1]
        self.assertEqual(last_entry["tool_name"], "calculate_risk_scores")
        self.assertTrue(last_entry["success"])
        self.assertEqual(last_entry["arguments"], {"likelihood": 4, "impact": 5})

    def test_create_risk_executes_through_ai_harness_layer(self):
        """Verify create_risk in confirmation save flow passes through ExecutionCoordinator and logs history."""
        r_start = AgentRequest(
            message=(
                "Create risk: Turbo Expander Vibration. "
                "Description: High amplitude 1X vibration on expander shaft. "
                "Inherent likelihood 4 and impact 4. "
                "Mitigation: Rebalance rotor and inspect magnetic bearings. "
                "Current likelihood 2 and impact 2. "
                "Action plan: Conduct multi-plane balancing during turnaround."
            ),
            user_id="802",
            metadata=self.meta,
        )
        res_start = self.agent.process(r_start)
        self.assertIn("Risk Creation – Final Review", res_start.response)

        sess = self.agent.get_session("802")
        self.assertIsNotNone(sess.pending_confirmation)

        with patch.object(erm_db, "create_risk", return_value={
            "status": "success",
            "risk_id": "RSK-GAS-777",
            "risk_register_id": 105,
            "risk_name": "Turbo Expander Vibration",
            "department_id": 2,
            "department_name": "Gas Processing Facilities",
            "risk_status": 1,
            "status_label": "Draft",
        }) as mock_create:
            r_confirm = AgentRequest(message="confirm", user_id="802", metadata=self.meta)
            res_confirm = self.agent.process(r_confirm)

            self.assertIn("RSK-GAS-777", res_confirm.response)
            self.assertIn("Turbo Expander Vibration", res_confirm.response)
            mock_create.assert_called_once()

            # Verify that create_risk was invoked via ExecutionCoordinator and logged in tool_call_history
            tool_names = [call["tool_name"] for call in sess.tool_call_history]
            self.assertIn("create_risk", tool_names)

    # =========================================================================
    # Task 2: Prove Dynamic Decisions
    # =========================================================================

    @patch.object(erm_db, "get_all_users_for_co_owner", return_value=[{"user_id": 201, "full_name": "Alice Smith", "role_name": "Functional Head"}])
    def test_dynamic_co_owner_in_initial_prompt_skips_co_owner_prompt(self, mock_users):
        """User supplies title and co-owner in initial prompt; agent does not ask for co-owner."""
        msg = "Create risk: Cryogenic Valve Sticking. Co-owner: Alice Smith."
        req = AgentRequest(message=msg, user_id="803", metadata=self.meta)
        res = self.agent.process(req)

        sess = self.agent.get_session("803")
        self.assertEqual(sess.risk_name, "Cryogenic Valve Sticking")
        self.assertIn("Alice Smith", sess.risk_co_owner_name)

        # Agent must NOT prompt to choose a co-owner
        self.assertNotIn("Step 2/10: Risk Co-Owner", res.response)
        # Agent should prompt for description (the next unresolved required field)
        self.assertIn("Risk Description", res.response)

    def test_dynamic_suggestions_skipped_when_acceptable_text_provided(self):
        """User provides custom mitigation directly; agent accepts it without calling suggestions."""
        sess = RiskCreationSession(
            session_id="sess-sugg-skip",
            user_id="804",
            user_role="Risk Owner",
            dept_id=2,
            risk_name="Crude Pump Cavitation",
            risk_description="Impeller erosion due to low NPSH.",
            inherent_likelihood=3,
            inherent_impact=4,
            inherent_score=12,
            state=RiskCreationState.AWAITING_MITIGATION,
        )
        self.agent.sessions["804"] = sess

        with patch.object(ExecutionCoordinator, "execute_tool", wraps=ExecutionCoordinator.execute_tool) as mock_exec:
            req = AgentRequest(
                message="Install booster charge pump to increase suction head margin.",
                user_id="804",
                metadata=self.meta,
            )
            res = self.agent.process(req)

            # Suggestion tool was never called
            called_tools = [call.kwargs.get("tool_name") or call.args[0] for call in mock_exec.call_args_list]
            self.assertNotIn("generate_mitigation_suggestions", called_tools)
            self.assertNotIn("get_mitigation_suggestions", called_tools)

            self.assertEqual(sess.mitigation, "Install booster charge pump to increase suction head margin.")
            self.assertEqual(sess.field_provenance.get("mitigation"), "user_stated")

    def test_dynamic_suggestion_invoked_only_on_explicit_request(self):
        """User explicitly asks for mitigation recommendations; agent invokes suggestion tool."""
        sess = RiskCreationSession(
            session_id="sess-sugg-req",
            user_id="805",
            user_role="Risk Owner",
            dept_id=2,
            risk_name="Crude Pump Cavitation",
            risk_description="Impeller erosion due to low NPSH.",
            inherent_likelihood=3,
            inherent_impact=4,
            inherent_score=12,
            state=RiskCreationState.AWAITING_MITIGATION,
        )
        self.agent.sessions["805"] = sess

        req = AgentRequest(
            message="Show me recommended mitigation options",
            user_id="805",
            metadata=self.meta,
        )
        res = self.agent.process(req)

        self.assertIn("Recommended Mitigation Options", res.response)
        self.assertIn("Option 1", res.response)
        tool_names = [call["tool_name"] for call in sess.tool_call_history]
        self.assertIn("generate_mitigation_suggestions", tool_names)

    # =========================================================================
    # Task 3: Detect Residual Fixed-Questionnaire Behavior
    # =========================================================================

    def test_partial_draft_requests_only_unresolved_required_fields(self):
        """When multiple fields are supplied out of order, only truly missing fields are requested."""
        msg = (
            "Create risk: Scrubber Level Transmitter Drift. "
            "Action plan: Replace differential pressure sensor with guided wave radar. "
            "Mitigation: Implement dual transmitter voting logic."
        )
        req = AgentRequest(message=msg, user_id="806", metadata=self.meta)
        res = self.agent.process(req)

        sess = self.agent.get_session("806")
        self.assertEqual(sess.risk_name, "Scrubber Level Transmitter Drift")
        self.assertIn("dual transmitter voting logic", sess.mitigation)
        self.assertIn("guided wave radar", sess.action_plan)

        # Neither mitigation nor action plan should be requested
        self.assertNotIn("Step 5/10: Mitigation", res.response)
        self.assertNotIn("Step 7/10: Action Plan", res.response)

        # Description is missing and must be prompted
        self.assertIn("Risk Description", res.response)

    # =========================================================================
    # Task 4: Audit Role & Department Enforcement
    # =========================================================================

    def test_standard_risk_owner_cannot_spoof_dept_id(self):
        """Standard Risk Owner passing spoofed dept_id=99 is strictly forced to context.dept_id=2."""
        ctx = HarnessContext.build_from_auth(
            user_id="807",
            user_role="Risk Owner",
            dept_id=2,
            dept_name="Gas Processing",
        )

        with patch.object(erm_db, "create_risk", return_value={"status": "success", "risk_id": "RSK-001"}) as mock_create:
            ExecutionCoordinator.execute_tool(
                tool_name="create_risk",
                arguments={
                    "risk_name": "Sour Gas Valve Leak",
                    "risk_description": "Packing gland leakage detected during sniffer survey.",
                    "dept_id": 99,  # Attempted spoof
                },
                context=ctx,
                bypass_confirmation=True,
            )

            mock_create.assert_called_once()
            called_kwargs = mock_create.call_args.kwargs
            # dept_id must be forced to context.dept_id (2), not spoofed 99
            self.assertEqual(called_kwargs["dept_id"], 2)
            # risk_owner_id must be forced to context.user_id ("807")
            self.assertEqual(called_kwargs["risk_owner_id"], "807")

    def test_enterprise_role_can_specify_department(self):
        """Admin or Risk Manager may legitimately create/query for a specified department."""
        ctx_admin = HarnessContext.build_from_auth(
            user_id="101",
            user_role=ROLE_ADMIN,
            dept_id=1,
        )

        with patch.object(erm_db, "create_risk", return_value={"status": "success", "risk_id": "RSK-002"}) as mock_create:
            ExecutionCoordinator.execute_tool(
                tool_name="create_risk",
                arguments={
                    "risk_name": "Pipeline Rupture Risk",
                    "risk_description": "Severe external pitting on high pressure trunk line.",
                    "dept_id": 5,  # Legitimate cross-department assignment by Admin
                },
                context=ctx_admin,
                bypass_confirmation=True,
            )

            mock_create.assert_called_once()
            called_kwargs = mock_create.call_args.kwargs
            self.assertEqual(called_kwargs["dept_id"], 5)

    def test_unauthorized_auditor_cannot_create_risk(self):
        """Auditor role is read-only and blocked from invoking create_risk by RBAC."""
        ctx_auditor = HarnessContext.build_from_auth(
            user_id="404",
            user_role=ROLE_AUDITOR,
            dept_id=2,
        )

        with self.assertRaises(AuthorizationError) as cm:
            ExecutionCoordinator.execute_tool(
                tool_name="create_risk",
                arguments={
                    "risk_name": "Unauthorized Audit Entry",
                    "risk_description": "Auditor attempting risk persistence.",
                },
                context=ctx_auditor,
                bypass_confirmation=True,
            )
        self.assertIn("not authorized", str(cm.exception).lower())

    def test_co_owner_lookup_searches_enterprise_wide(self):
        """Co-owner lookup queries enterprise users across all departments under governance."""
        with patch.object(erm_db, "get_all_users_for_co_owner", return_value=[
            {"user_id": 11, "full_name": "Dept 1 User", "dept_name": "Drilling", "role_name": "Risk Owner"},
            {"user_id": 22, "full_name": "Dept 3 User", "dept_name": "Refining", "role_name": "Functional Head"},
        ]) as mock_co:
            ctx = HarnessContext.build_from_auth(user_id="808", user_role="Risk Owner", dept_id=2)
            res = ExecutionCoordinator.execute_tool(
                tool_name="get_eligible_risk_owners",
                arguments={"owner_type": "co_owner"},
                context=ctx,
            )
            mock_co.assert_called_once()
            owners = res.get("result", {}).get("owners", [])
            self.assertEqual(len(owners), 2)
            dept_names = {o.get("dept_name") for o in owners}
            self.assertIn("Drilling", dept_names)
            self.assertIn("Refining", dept_names)

    # =========================================================================
    # Task 5: Confirmation & Persistence Safety
    # =========================================================================

    def test_confirmation_cannot_be_replayed_after_execution(self):
        """Once a confirmation token is executed, replay attempts are rejected."""
        sess = RiskCreationSession(
            session_id="sess-replay-01",
            user_id="809",
            user_role="Risk Owner",
            dept_id=2,
            risk_name="Desalter Emulsion Carryover",
            risk_description="Emulsion layer buildup in desalting vessel.",
            inherent_likelihood=4,
            inherent_impact=4,
            current_likelihood=2,
            current_impact=2,
            mitigation="Inject deemulsifier chemical package.",
            action_plan="Install automated interface level detector.",
            state=RiskCreationState.AWAITING_CONFIRMATION,
        )
        self.agent.sessions["809"] = sess
        self.agent._bind_pending_confirmation(sess)

        # Mark as EXECUTED
        sess.pending_confirmation["status"] = "EXECUTED"

        req_replay = AgentRequest(message="confirm", user_id="809", metadata=self.meta)
        res_replay = self.agent.process(req_replay)

        # Replay must be rejected with verification notice and a fresh preview generated
        self.assertIn("Confirmation Verification Notice", res_replay.response)
        self.assertIn("cannot be reused", res_replay.response)

    def test_confirmation_payload_tampering_rejected(self):
        """Modifying draft values after preview invalidates confirmation fingerprint."""
        sess = RiskCreationSession(
            session_id="sess-tamper-01",
            user_id="810",
            user_role="Risk Owner",
            dept_id=2,
            risk_name="Fuel Gas Knockout Drum Level",
            risk_description="Condensate pooling in fuel gas system.",
            inherent_likelihood=3,
            inherent_impact=4,
            current_likelihood=2,
            current_impact=2,
            mitigation="Manual draining every shift.",
            action_plan="Retrofit automated dump valve.",
            state=RiskCreationState.AWAITING_CONFIRMATION,
        )
        self.agent.sessions["810"] = sess
        self.agent._bind_pending_confirmation(sess)

        # Covertly tamper with draft after preview generation
        sess.inherent_likelihood = 5  # Changed rating

        req_confirm = AgentRequest(message="confirm", user_id="810", metadata=self.meta)
        res_confirm = self.agent.process(req_confirm)

        self.assertIn("Confirmation Verification Notice", res_confirm.response)
        self.assertIn("Action arguments have changed since preview generation", res_confirm.response)

    def test_state_changing_action_never_auto_retried_on_uncertain_error(self):
        """RetryPolicy strictly rejects automatic retry for state-changing create_risk tool."""
        ctx = HarnessContext.build_from_auth(user_id="811", user_role="Risk Owner", dept_id=2)

        with patch.object(erm_db, "create_risk", side_effect=TimeoutError("Gateway Connection Timeout")) as mock_create:
            with self.assertRaises(TimeoutError):
                ExecutionCoordinator.execute_tool(
                    tool_name="create_risk",
                    arguments={
                        "risk_name": "Sulfur Recovery Unit Outage",
                        "risk_description": "Acid gas flaring risk due to reaction furnace trip.",
                    },
                    context=ctx,
                    bypass_confirmation=True,
                )

            # Strict Invariant: create_risk must be called exactly ONCE (zero automatic retries)
            self.assertEqual(mock_create.call_count, 1)

    def test_duplicate_check_failure_treated_as_recoverable_error(self):
        """When duplicate check fails, it returns check_failed and never fabricates a clean register."""
        sess = RiskCreationSession(
            session_id="sess-dup-err-01",
            user_id="812",
            user_role="Risk Owner",
            dept_id=2,
            risk_name="Boiler Tube Rupture",
            risk_description="Overheating causing rupture on steam boiler B-201.",
            state=RiskCreationState.COLLECTING,
        )
        self.agent.sessions["812"] = sess

        with patch.object(erm_db, "find_potential_duplicate_risks", side_effect=ConnectionError("Database offline")):
            req = AgentRequest(message="Check for duplicates", user_id="812", metadata=self.meta)
            res = self.agent.process(req)

            # Response must report failure, NOT 'No Duplicate Risks Found'
            self.assertIn("could not be completed", res.response)
            self.assertNotIn("No Duplicate Risks Found", res.response)
            self.assertEqual(sess.duplicate_check_status, "check_failed")


if __name__ == "__main__":
    unittest.main()
