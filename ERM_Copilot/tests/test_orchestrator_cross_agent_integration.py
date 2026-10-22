"""
Comprehensive Integration Tests for ERMCopilotAgent Master Orchestrator.
Validates:
1. Routing Precedence & Intent Classification
2. Active Session Continuation vs Intent Switch
3. Safe Cross-Agent Transitions (Risk Creation -> Treatment, Treatment -> Approval)
4. Non-accidental confirmation execution across transitions
5. Read-only interruptions preserving drafts
6. Workflow cancellation
7. Fail-closed security contracts on missing identity and role
"""
import pytest
from unittest.mock import MagicMock, patch

from ERM_Copilot.agents.orchestrator.agent import ERMCopilotAgent, erm_copilot_agent
from ERM_Copilot.agents.risk_creation import risk_creation_agent
from ERM_Copilot.agents.treatment import treatment_management_agent
from ERM_Copilot.agents.approval_workflow import approval_workflow_agent
from ERM_Copilot.models.contracts import AgentRequest, AgentResponse
from ERM_Copilot.workflow import workflow_checkpointer, WorkflowStatus, WorkflowType


@pytest.fixture(autouse=True)
def clean_sessions():
    """Ensure in-memory sessions are cleared before and after each test."""
    risk_creation_agent.sessions.clear()
    treatment_management_agent.sessions.clear()
    approval_workflow_agent.sessions.clear()
    yield
    risk_creation_agent.sessions.clear()
    treatment_management_agent.sessions.clear()
    approval_workflow_agent.sessions.clear()


class TestOrchestratorSecurityContracts:
    """Tests fail-closed identity, role, and department security boundaries."""

    def test_missing_user_id_fails_closed(self):
        req = AgentRequest(
            message="Show top risks",
            user_id="",
            user_role="Risk Owner",
            metadata={"role": "Risk Owner"}
        )
        resp = erm_copilot_agent.process(req)
        assert resp.metadata.get("intent") == "AUTH_FAILURE"
        assert "Authentication Required" in resp.response

    def test_missing_role_fails_closed(self):
        req = AgentRequest(
            message="Show top risks",
            user_id="12",
            user_role="",
            metadata={}
        )
        resp = erm_copilot_agent.process(req)
        assert resp.metadata.get("intent") == "ROLE_MISSING"
        assert "Role Required" in resp.response


class TestOrchestratorRoutingPrecedence:
    """Tests precedence between Approval, Treatment, Risk Creation, and Direct Queries."""

    def test_approval_intent_precedence(self):
        req = AgentRequest(
            message="Approve RSK-001 with remark Approved by FH",
            user_id="12",
            user_role="Functional Head",
            session_id="sess-orch-01",
            metadata={"role": "Functional Head", "dept_id": 2, "dept_name": "Gas Processing Facilities"}
        )
        with patch.object(approval_workflow_agent, "process") as mock_proc:
            mock_proc.return_value = AgentResponse(
                request_id="req-1",
                agent_id="approval_workflow_agent",
                status="success",
                response="Please confirm approval for RSK-001.",
                metadata={"intent": "APPROVAL_CONFIRMATION_REQUIRED"}
            )
            resp = erm_copilot_agent.process(req)
            assert resp.agent_id == "approval_workflow_agent"
            mock_proc.assert_called_once()

    def test_treatment_intent_precedence(self):
        req = AgentRequest(
            message="Add treatment plan for RSK-GAS-087",
            user_id="12",
            user_role="Risk Owner",
            session_id="sess-orch-02",
            metadata={"role": "Risk Owner", "dept_id": 2, "dept_name": "Gas Processing Facilities"}
        )
        with patch.object(treatment_management_agent, "process") as mock_proc:
            mock_proc.return_value = AgentResponse(
                request_id="req-2",
                agent_id="treatment_management_agent",
                status="success",
                response="Please provide the action plan description.",
                metadata={"intent": "ADD_TREATMENT"}
            )
            resp = erm_copilot_agent.process(req)
            assert resp.agent_id == "treatment_management_agent"
            mock_proc.assert_called_once()

    def test_risk_creation_intent_precedence(self):
        req = AgentRequest(
            message="Create a new risk for Gas Leakage at Compressor",
            user_id="12",
            user_role="Risk Owner",
            session_id="sess-orch-03",
            metadata={"role": "Risk Owner", "dept_id": 2, "dept_name": "Gas Processing Facilities"}
        )
        with patch.object(risk_creation_agent, "process") as mock_proc:
            mock_proc.return_value = AgentResponse(
                request_id="req-3",
                agent_id="risk_creation_agent",
                status="success",
                response="Step 2: Please specify the Co-Owner.",
                metadata={"wizard_step": "STEP_CO_OWNER"}
            )
            resp = erm_copilot_agent.process(req)
            assert resp.agent_id == "risk_creation_agent"
            mock_proc.assert_called_once()


class TestSafeCrossAgentTransitions:
    """Verifies seamless suspension, draft preservation, and non-accidental execution."""

    def test_switch_from_active_risk_creation_to_treatment(self):
        session_key = "12::sess-trans-01"
        # Simulate active Risk Creation session
        req_start = AgentRequest(
            message="Create a new risk for Pipeline Vibration",
            user_id="12",
            user_role="Risk Owner",
            session_id="sess-trans-01",
            metadata={"role": "Risk Owner", "dept_id": 2, "dept_name": "Gas Processing Facilities"}
        )
        resp1 = risk_creation_agent.process(req_start)
        assert risk_creation_agent.is_session_active(session_key)

        # Now user switches intent explicitly to Treatment Management
        req_switch = AgentRequest(
            message="Add treatment plan for RSK-GAS-087",
            user_id="12",
            user_role="Risk Owner",
            session_id="sess-trans-01",
            metadata={"role": "Risk Owner", "dept_id": 2, "dept_name": "Gas Processing Facilities"}
        )
        with patch.object(treatment_management_agent, "process") as mock_treat:
            mock_treat.return_value = AgentResponse(
                request_id="req-sw",
                agent_id="treatment_management_agent",
                status="success",
                response="Please provide the action plan description.",
                metadata={"intent": "ADD_TREATMENT"}
            )
            resp2 = erm_copilot_agent.process(req_switch)
            assert resp2.agent_id == "treatment_management_agent"
            assert "safely paused in the background" in resp2.response
            assert resp2.metadata.get("suspended_workflow") == "RISK_CREATION"
            # Risk creation session draft is preserved in memory and checkpointer!
            assert session_key in risk_creation_agent.sessions

    def test_switch_from_active_treatment_to_approval(self):
        from ERM_Copilot.agents.treatment.state import TreatmentSession, TreatmentWorkflowState
        session_key = "14::sess-trans-02"
        # Initialize treatment session
        sess = TreatmentSession(
            session_id="sess-trans-02",
            user_id="14",
            user_role="Risk Manager",
            dept_id=2,
            dept_name="Gas Processing Facilities",
            state=TreatmentWorkflowState.COLLECTING_INFO,
            target_risk_id="RSK-001"
        )
        treatment_management_agent.sessions[session_key] = sess
        assert treatment_management_agent.is_session_active(session_key)

        # User switches intent to Approval
        req_switch = AgentRequest(
            message="Approve RSK-001 with remark Approved",
            user_id="14",
            user_role="Risk Manager",
            session_id="sess-trans-02",
            metadata={"role": "Risk Manager", "dept_id": 2, "dept_name": "Gas Processing Facilities"}
        )
        with patch.object(approval_workflow_agent, "process") as mock_app:
            mock_app.return_value = AgentResponse(
                request_id="req-app",
                agent_id="approval_workflow_agent",
                status="success",
                response="Please confirm approval for RSK-001.",
                metadata={"intent": "APPROVAL_CONFIRMATION_REQUIRED"}
            )
            resp2 = erm_copilot_agent.process(req_switch)
            assert resp2.agent_id == "approval_workflow_agent"
            assert "safely paused in the background" in resp2.response
            assert resp2.metadata.get("suspended_workflow") == "TREATMENT"

    def test_message_during_pending_confirmation_cannot_trigger_stale_mutation(self):
        """A new message intended for a different agent cannot execute a pending confirmation."""
        from ERM_Copilot.agents.treatment.state import TreatmentSession, TreatmentWorkflowState
        session_key = "12::sess-conf-01"
        # Setup session with pending confirmation in treatment agent
        sess = TreatmentSession(
            session_id="sess-conf-01",
            user_id="12",
            user_role="Risk Owner",
            dept_id=2,
            dept_name="Gas Processing Facilities",
            state=TreatmentWorkflowState.AWAITING_CONFIRMATION,
            pending_confirmation={
                "action": "add_risk_treatment",
                "token": "hmac_secret_token_123",
                "digest": "digest_abc",
                "arguments": {"risk_id": "RSK-001"}
            }
        )
        treatment_management_agent.sessions[session_key] = sess

        # User sends a switch message to Risk Creation
        req = AgentRequest(
            message="Create a new risk for Flare Header Pressure",
            user_id="12",
            user_role="Risk Owner",
            session_id="sess-conf-01",
            metadata={"role": "Risk Owner", "dept_id": 2, "dept_name": "Gas Processing Facilities"}
        )
        resp = erm_copilot_agent.process(req)
        # Verify the pending confirmation was cleared/invalidated so it cannot accidentally fire
        assert sess.pending_confirmation is None
        assert resp.agent_id == "risk_creation_agent"


class TestReadOnlyInterruptionAndCancellation:
    """Verifies that read-only queries during active workflows preserve drafts, and cancel cleans up."""

    def test_read_only_heatmap_query_preserves_active_risk_creation_draft(self):
        session_key = "12::sess-draft-01"
        # Start risk creation
        req1 = AgentRequest(
            message="Create a new risk for Boiler Tube Leaks",
            user_id="12",
            user_role="Risk Owner",
            session_id="sess-draft-01",
            metadata={"role": "Risk Owner", "dept_id": 2, "dept_name": "Gas Processing Facilities"}
        )
        resp1 = risk_creation_agent.process(req1)
        assert risk_creation_agent.is_session_active(session_key)

        # Interruption with 5x5 heatmap query
        req_query = AgentRequest(
            message="Show 5x5 heatmap matrix",
            user_id="12",
            user_role="Risk Owner",
            session_id="sess-draft-01",
            metadata={"role": "Risk Owner", "dept_id": 2, "dept_name": "Gas Processing Facilities"}
        )
        resp_query = erm_copilot_agent.process(req_query)
        assert resp_query.metadata.get("active_workflow_preserved") == "RISK_CREATION"
        assert "Draft Saved" in resp_query.response
        assert "5×5" in resp_query.response or "Matrix" in resp_query.response
        # Session draft still alive
        assert risk_creation_agent.is_session_active(session_key)

    def test_cancellation_cleans_up_active_workflow(self):
        session_key = "12::sess-cancel-01"
        req_start = AgentRequest(
            message="Create a new risk for Turbine Bearing High Temp",
            user_id="12",
            user_role="Risk Owner",
            session_id="sess-cancel-01",
            metadata={"role": "Risk Owner", "dept_id": 2, "dept_name": "Gas Processing Facilities"}
        )
        resp1 = risk_creation_agent.process(req_start)
        assert risk_creation_agent.is_session_active(session_key)

        # Send cancellation
        req_cancel = AgentRequest(
            message="cancel",
            user_id="12",
            user_role="Risk Owner",
            session_id="sess-cancel-01",
            metadata={"role": "Risk Owner", "dept_id": 2, "dept_name": "Gas Processing Facilities"}
        )
        resp_cancel = erm_copilot_agent.process(req_cancel)
        assert resp_cancel.metadata.get("intent") == "WORKFLOW_CANCELLED"
        assert "Cancelled" in resp_cancel.response
        assert not risk_creation_agent.is_session_active(session_key)

    def test_cancellation_when_idle_returns_informative_notice(self):
        req_cancel = AgentRequest(
            message="cancel",
            user_id="12",
            user_role="Risk Owner",
            session_id="sess-idle-01",
            metadata={"role": "Risk Owner", "dept_id": 2, "dept_name": "Gas Processing Facilities"}
        )
        resp = erm_copilot_agent.process(req_cancel)
        assert resp.metadata.get("intent") == "NO_ACTIVE_WORKFLOW"
        assert "No active workflow" in resp.response
