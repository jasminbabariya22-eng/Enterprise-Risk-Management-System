"""
End-to-End Recovery and Multi-Turn Resumption Tests.
Verifies conversational interruption and resumption across Risk Creation,
Treatment Management, and Approval Workflows.
"""
import pytest
import uuid
from ERM_Copilot.models.contracts import AgentRequest
from ERM_Copilot.agents.risk_creation.agent import RiskCreationAgent
from ERM_Copilot.agents.treatment.agent import TreatmentManagementAgent
from ERM_Copilot.agents.approval.graph import ApprovalWorkflowAgent
from ERM_Copilot.workflow.checkpointer import workflow_checkpointer
from ERM_Copilot.workflow.contracts import WorkflowType, WorkflowStatus


@pytest.fixture(autouse=True)
def cleanup_workflows():
    workflow_checkpointer.cleanup_expired()
    yield


def test_risk_creation_interrupted_and_resumed():
    """
    Test risk creation wizard interrupted mid-flow, agent instance discarded,
    and resumed seamlessly using persistent checkpoint state.
    """
    agent1 = RiskCreationAgent()
    uid = "101"
    sess_id = f"rc_{uuid.uuid4().hex[:8]}"
    
    # Step 1: Initiate
    req1 = AgentRequest(
        message="Create a new risk",
        user_id=uid,
        session_id=sess_id,
        user_role="Risk Owner",
        metadata={"dept_id": 2, "dept_name": "Gas Processing Facilities"}
    )
    resp1 = agent1.process(req1)
    assert "Risk Name" in resp1.response or "Title" in resp1.response

    # Step 2: Provide Title
    req2 = AgentRequest(
        message="Flare Header Corrosion",
        user_id=uid,
        session_id=sess_id,
        user_role="Risk Owner"
    )
    resp2 = agent1.process(req2)
    assert "Co-Owner" in resp2.response

    # SIMULATE APPLICATION RESTART / FRESH AGENT INSTANCE
    agent2 = RiskCreationAgent()
    assert sess_id not in agent2.sessions # In-memory session is empty in new instance!

    # Step 3: Resume by providing Co-Owner input
    req3 = AgentRequest(
        message="None",
        user_id=uid,
        session_id=sess_id,
        user_role="Risk Owner"
    )
    resp3 = agent2.process(req3)
    assert "Description" in resp3.response

    # Verify session was restored from persistent checkpoint
    restored_sess = agent2.get_session(f"{uid}::{sess_id}")
    assert restored_sess is not None
    assert restored_sess.risk_name == "Flare Header Corrosion"


def test_treatment_management_interrupted_and_resumed():
    """
    Test treatment management wizard interrupted mid-flow, agent instance discarded,
    and resumed seamlessly using persistent checkpoint state.
    """
    agent1 = TreatmentManagementAgent()
    uid = "101"
    sess_id = f"tm_{uuid.uuid4().hex[:8]}"

    # Step 1: Trigger Add Treatment
    req1 = AgentRequest(
        message="Add action plan for RSK-GAS-087",
        user_id=uid,
        session_id=sess_id,
        user_role="Risk Owner",
        metadata={"dept_id": 1}
    )
    resp1 = agent1.process(req1)
    assert "action plan" in resp1.response.lower()

    # SIMULATE APPLICATION RESTART
    agent2 = TreatmentManagementAgent()
    assert sess_id not in agent2.sessions

    # Step 2: Provide action plan description
    req2 = AgentRequest(
        message="Install ultrasonic thickness sensor",
        user_id=uid,
        session_id=sess_id,
        user_role="Risk Owner",
        metadata={"dept_id": 1}
    )
    resp2 = agent2.process(req2)
    assert any(w in resp2.response.lower() for w in ["action owner", "assign action owner", "step 3"])

    # Verify restored state
    restored_sess = agent2.get_session(f"{uid}::{sess_id}")
    assert restored_sess is not None
    assert restored_sess.target_risk_id == "RSK-GAS-087"
    assert restored_sess.action_plan == "Install ultrasonic thickness sensor"


def test_approval_workflow_interrupted_and_resumed():
    """
    Test approval workflow requiring multi-turn remark input survives process restart.
    """
    agent1 = ApprovalWorkflowAgent()
    uid = "201"
    sess_id = f"app_{uuid.uuid4().hex[:8]}"

    # Step 1: User indicates rejection without remark
    req1 = AgentRequest(
        message="reject RSK-GAS-087",
        user_id=uid,
        session_id=sess_id,
        user_role="Functional Head",
        metadata={"dept_id": 2}
    )
    resp1 = agent1.process(req1)
    assert "reason" in resp1.response.lower() or "remark" in resp1.response.lower()

    # SIMULATE APPLICATION RESTART
    agent2 = ApprovalWorkflowAgent()
    assert sess_id not in agent2._sessions

    # Step 2: Provide remark to fresh instance
    req2 = AgentRequest(
        message="Need deeper mitigation analysis",
        user_id=uid,
        session_id=sess_id,
        user_role="Functional Head"
    )
    resp2 = agent2.process(req2)
    # Rejection should now ask for confirmation
    assert "confirm" in resp2.response.lower() or "governance decision" in resp2.response.lower()

