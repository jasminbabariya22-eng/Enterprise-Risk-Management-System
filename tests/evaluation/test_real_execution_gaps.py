"""
Focused Evaluation Tests for Verified Execution Gaps in ERM Copilot.
Tests real tool registry execution, RBAC enforcement before execution,
grounding against authoritative database records, non-existent entity handling,
and cross-department scope isolation.
"""
import pytest
from ERM_Copilot.ai_harness.harness import ERMAIHarness
from ERM_Copilot.ai_harness.context import HarnessContext
from ERM_Copilot.ai_harness.tool_registry import tool_registry
from ERM_Copilot.ai_harness.policies import ROLE_RISK_OWNER, ROLE_FUNCTIONAL_HEAD, ROLE_RISK_MANAGER
from ERM_Copilot.ai_harness.exceptions import AuthorizationError, ConfirmationRequiredError
from ERM_Copilot.models.contracts import AgentRequest
from ERM_Copilot.agents.orchestrator.agent import ERMCopilotAgent
from ERM_Copilot.services.db_service import erm_db
from ERM_Copilot.agents.treatment import treatment_management_agent
from ERM_Copilot.agents.risk_creation import risk_creation_agent
from ERM_Copilot.agents.approval import approval_agent
from ERM_Copilot.cache.response_cache import erm_response_cache


@pytest.fixture(autouse=True)
def clean_copilot_sessions():
    """Ensure clean test isolation across all agent sessions and response caches."""
    erm_response_cache.invalidate_all()
    for uid in ["101", "201", "301", "401", "501", "999"]:
        treatment_management_agent.clear_session(uid)
        risk_creation_agent.clear_session(uid)
        approval_agent.clear_session(uid)
    yield
    erm_response_cache.invalidate_all()
    for uid in ["101", "201", "301", "401", "501", "999"]:
        treatment_management_agent.clear_session(uid)
        risk_creation_agent.clear_session(uid)
        approval_agent.clear_session(uid)



@pytest.mark.evaluation
def test_real_harness_unauthorized_tool_execution_blocked():
    """
    Verifies that ERMAIHarness.execute_governed_tool strictly enforces RBAC
    and raises AuthorizationError BEFORE invoking a protected tool for unauthorized roles.
    """
    ro_context = HarnessContext(
        user_id="101",
        user_role=ROLE_RISK_OWNER,
        dept_id=2,
        dept_name="Gas Processing Facilities",
        email="risk_owner@massers.com"
    )
    
    with pytest.raises(AuthorizationError) as exc_info:
        ERMAIHarness.execute_governed_tool(
            tool_name="approve_or_reject_risk",
            arguments={"risk_id": "RSK-GAS-087", "action": "approve", "remark": "Should fail", "approver_id": 101},
            context=ro_context
        )
    assert "not authorized" in str(exc_info.value).lower()


@pytest.mark.evaluation
def test_real_harness_authorized_tool_confirmation_mandated():
    """
    Verifies that state-changing governance tools (approve_or_reject_risk) require
    explicit confirmation tokens when called by authorized roles without bypass.
    """
    fh_context = HarnessContext(
        user_id="201",
        user_role=ROLE_FUNCTIONAL_HEAD,
        dept_id=2,
        dept_name="Gas Processing Facilities",
        email="functional_head@massers.com"
    )

    with pytest.raises(ConfirmationRequiredError) as exc_info:
        ERMAIHarness.execute_governed_tool(
            tool_name="approve_or_reject_risk",
            arguments={"risk_id": "RSK-GAS-087", "action": "approve", "remark": "Valid remark", "approver_id": 201},
            context=fh_context,
            bypass_confirmation=False
        )
    assert "confirmation" in str(exc_info.value).lower()


@pytest.mark.evaluation
def test_real_orchestrator_nonexistent_risk_handling():
    """
    Verifies that when a user asks about a non-existent risk, the orchestrator queries
    the DB layer, receives None/empty, and returns an explicit 'No Matching Risk Records Found'
    message without hallucinating fake records or fake approval stages.
    """
    agent = ERMCopilotAgent()
    req = AgentRequest(
        message="Show audit trail for RSK-UNKNOWN-99999",
        user_id="101",
        user_role=ROLE_RISK_OWNER,
        metadata={"role": ROLE_RISK_OWNER, "user_id": "101", "dept_id": 2, "dept_name": "Gas Processing Facilities"}
    )
    resp = agent.process(req)
    resp_text = resp.response if hasattr(resp, "response") else str(resp)
    
    # Must explicitly inform that no matching records were found
    assert any(phrase in resp_text.lower() for phrase in [
        "no matching risk records found",
        "no active risk items matched",
        "no risk found",
        "no records found"
    ])
    # Must not invent fake approval stages
    assert "stage 4 approved" not in resp_text.lower()
    assert "stage 1" not in resp_text.lower()



@pytest.mark.evaluation
def test_real_orchestrator_cross_department_isolation():
    """
    Verifies that a Risk Owner query is filtered strictly to their assigned department.
    """
    agent = ERMCopilotAgent()
    req = AgentRequest(
        message="Show my open risks",
        user_id="101",
        user_role=ROLE_RISK_OWNER,
        metadata={"role": ROLE_RISK_OWNER, "user_id": "101", "dept_id": 2, "dept_name": "Gas Processing Facilities"}
    )
    resp = agent.process(req)
    resp_text = resp.response if hasattr(resp, "response") else str(resp)
    
    assert "Gas Processing Facilities" in resp_text
    assert "Refining Operations" not in resp_text


@pytest.mark.evaluation
def test_real_tool_registry_live_read():
    """
    Verifies that tool_registry handlers can invoke live DB read operations
    and return authoritative entity records.
    """
    audit_tool = tool_registry.get("get_risk_audit_trail")
    assert audit_tool is not None
    assert audit_tool.is_state_changing is False

    result = audit_tool.handler(risk_identifier="RSK-GAS-087")
    assert result is not None
    assert isinstance(result, dict)
    assert result.get("risk_id") == "RSK-GAS-087"
    assert "risk_name" in result
