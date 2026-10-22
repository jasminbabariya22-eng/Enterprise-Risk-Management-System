"""
Integration Tests: Treatment Service & Tool Execution Governance Lifecycle.
Tests:
- Adding action plan to risk
- Milestone progress update with status transition (In Progress -> Completed)
- Reassigning action owner
- Querying risk treatments and details
- Role authorization and confirmation enforcement
"""
import pytest
from unittest.mock import patch
from ERM_Copilot.ai_harness.execution import ExecutionCoordinator
from ERM_Copilot.ai_harness.exceptions import AuthorizationError, ConfirmationRequiredError


@pytest.mark.integration
def test_treatment_lifecycle_execution(ro_context, in_memory_db):
    """Test full treatment creation, progress update, and owner reassignment via AI Harness."""
    with patch("ERM_Copilot.ai_harness.tool_registry.erm_db.add_risk_treatment", side_effect=in_memory_db.add_risk_treatment), \
         patch("ERM_Copilot.ai_harness.tool_registry.erm_db.update_treatment_progress", side_effect=in_memory_db.update_treatment_progress), \
         patch("ERM_Copilot.ai_harness.tool_registry.erm_db.reassign_treatment_owner", side_effect=in_memory_db.reassign_treatment_owner), \
         patch("ERM_Copilot.ai_harness.tool_registry.erm_db.get_treatments_for_risk", side_effect=in_memory_db.get_risk_treatments), \
         patch("ERM_Copilot.ai_harness.tool_registry.erm_db.get_treatment_by_id", side_effect=in_memory_db.get_treatment_details):

        # 1. Add action plan
        res_add = ExecutionCoordinator.execute_tool(
            tool_name="add_risk_treatment",
            arguments={
                "risk_register_id": 49,
                "action_plan": "Install redundant pressure safety valves (PSV-401/402)",
                "action_owner_id": 8,
                "target_date": "2026-12-31",
                "progress": 0,
                "action_status_id": 1,
            },
            context=ro_context,
            bypass_confirmation=True,
        )
        assert res_add["success"] is True
        new_t = res_add["result"]
        t_id = new_t["risk_treatment_id"]
        assert t_id is not None
        assert new_t["action_owner_id"] == 8

        # 2. Update progress to 50% (Transitions to In Progress = 7)
        res_prog = ExecutionCoordinator.execute_tool(
            tool_name="update_treatment_progress",
            arguments={
                "treatment_id": t_id,
                "progress": 50,
                "remarks": "Procurement completed, installation underway",
            },
            context=ro_context,
            bypass_confirmation=True,
        )
        assert res_prog["success"] is True
        assert res_prog["result"]["progress"] == 50
        assert res_prog["result"]["action_status_id"] == 7

        # 3. Update progress to 100% (Transitions to Completed = 8)
        res_comp = ExecutionCoordinator.execute_tool(
            tool_name="update_treatment_progress",
            arguments={
                "treatment_id": t_id,
                "progress": 100,
                "remarks": "Commissioning and Hydrotest passed",
            },
            context=ro_context,
            bypass_confirmation=True,
        )
        assert res_comp["success"] is True
        assert res_comp["result"]["progress"] == 100
        assert res_comp["result"]["action_status_id"] == 8

        # 4. Reassign Action Owner
        res_reassign = ExecutionCoordinator.execute_tool(
            tool_name="reassign_treatment_owner",
            arguments={
                "treatment_id": t_id,
                "new_action_owner_id": 14,
            },
            context=ro_context,
            bypass_confirmation=True,
        )
        assert res_reassign["success"] is True
        assert res_reassign["result"]["new_action_owner_id"] == 14

        # 5. Inspect details
        res_details = ExecutionCoordinator.execute_tool(
            tool_name="get_treatment_details",
            arguments={"treatment_id": t_id},
            context=ro_context,
            bypass_confirmation=True,
        )
        assert res_details["success"] is True
        details = res_details["result"]
        assert details["risk_treatment_id"] == t_id
        assert details["progress"] == 100
        assert details["action_owner_id"] == 14


@pytest.mark.integration
def test_auditor_prohibited_from_mutating_treatments(aud_context, in_memory_db):
    """Verify that an Auditor role is strictly blocked by harness RBAC from mutating treatments."""
    with pytest.raises(AuthorizationError):
        ExecutionCoordinator.execute_tool(
            tool_name="add_risk_treatment",
            arguments={
                "risk_register_id": 49,
                "action_plan": "Auditor unauthorized plan",
                "action_owner_id": 8,
            },
            context=aud_context,
            bypass_confirmation=True,
        )

    with pytest.raises(AuthorizationError):
        ExecutionCoordinator.execute_tool(
            tool_name="update_treatment_progress",
            arguments={"treatment_id": 1, "progress": 100},
            context=aud_context,
            bypass_confirmation=True,
        )
