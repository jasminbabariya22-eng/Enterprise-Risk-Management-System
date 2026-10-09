"""
Tests for BoundedPlanner.
Verifies max step enforcement, circular delegation prevention,
tool validation against ToolRegistry, and policy validation.
"""
import pytest
from ERM_Copilot.workflow.contracts import (
    AgentWorkflowState,
    WorkflowStatus,
    WorkflowType,
)
from ERM_Copilot.workflow.planner import (
    BoundedPlanner,
    PlannerDecisionType,
)
from ERM_Copilot.ai_harness.context import HarnessContext


def test_planner_detects_step_limit_exceeded():
    """Verify planner halts safely when step_count exceeds max_steps."""
    state = AgentWorkflowState(
        session_id="101::plan_1",
        owner_user_id="101",
        owner_role="Risk Owner",
        step_count=16,
        max_steps=15
    )
    decision = BoundedPlanner.plan_next_step(state, "What should we do next?")
    assert decision.decision_type == PlannerDecisionType.FAIL_SAFELY.value
    assert "limit" in decision.reasoning.lower()


def test_planner_detects_circular_delegation():
    """Verify planner detects alternating agent loops (A -> B -> A -> B)."""
    state = AgentWorkflowState(
        session_id="101::plan_2",
        owner_user_id="101",
        owner_role="Risk Owner",
        agent_handoff_history=[
            "risk_creation_agent",
            "treatment_management_agent",
            "risk_creation_agent",
            "treatment_management_agent"
        ]
    )
    decision = BoundedPlanner.plan_next_step(state, "Continue workflow")
    assert decision.decision_type == PlannerDecisionType.FAIL_SAFELY.value
    assert "circular" in decision.reasoning.lower()


def test_planner_validates_known_tools():
    """Verify decision validation fails if target tool is hallucinated or unregistered."""
    decision = BoundedPlanner.plan_next_step(
        AgentWorkflowState(session_id="101::plan_3", owner_user_id="101", owner_role="Risk Owner"),
        "search my risks"
    )
    decision.target_tool = "fake_hallucinated_database_delete"

    with pytest.raises(ValueError) as exc_info:
        BoundedPlanner.validate_decision(decision, user_role="Risk Owner")
    assert "not registered" in str(exc_info.value)


def test_planner_validates_unauthorized_tool():
    """Verify decision validation fails if user role is not authorized for target tool."""
    decision = BoundedPlanner.plan_next_step(
        AgentWorkflowState(session_id="101::plan_4", owner_user_id="101", owner_role="Risk Owner"),
        "approve risk"
    )
    decision.target_tool = "approve_or_reject_risk"

    # Risk Owner is not in APPROVER_ROLES
    with pytest.raises(ValueError) as exc_info:
        BoundedPlanner.validate_decision(decision, user_role="Risk Owner")
    assert "not authorized" in str(exc_info.value)


def test_planner_delegates_to_active_subagent():
    """Verify planner delegates to appropriate specialized subagent when workflow is active."""
    state = AgentWorkflowState(
        session_id="101::plan_5",
        owner_user_id="101",
        owner_role="Risk Owner",
        workflow_type=WorkflowType.TREATMENT_MANAGEMENT,
        current_step="AWAITING_ACTION_PLAN"
    )
    decision = BoundedPlanner.plan_next_step(state, "Add preventative maintenance")
    assert decision.decision_type == PlannerDecisionType.DELEGATE_TO_AGENT.value
    assert decision.target_agent == "treatment_management_agent"
