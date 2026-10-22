"""
Pytest Fixtures and Configuration for ERM Copilot Comprehensive Test Framework.
Provides isolated in-memory test states, role-specific HarnessContext fixtures,
mocked database and email job queues, and deterministic response stubs.
"""
import pytest
import time
from typing import Dict, Any, List, Optional
from unittest.mock import MagicMock, patch

from ERM_Copilot.ai_harness.context import HarnessContext
from ERM_Copilot.ai_harness.tool_registry import ToolRegistry
from ERM_Copilot.models.contracts import AgentRequest, AgentResponse


# =====================================================================
# 1. Role-Specific Harness Context Fixtures
# =====================================================================
@pytest.fixture
def risk_owner_context() -> HarnessContext:
    """Standard authenticated context for a Risk Owner (Maker)."""
    return HarnessContext.build_from_auth(
        user_id="101",
        user_role="Risk Owner",
        dept_id=2,
        dept_name="Gas Processing Facilities",
        session_id="sess-ro-101",
        request_id="req-ro-001",
    )


@pytest.fixture
def functional_head_context() -> HarnessContext:
    """Authenticated context for Stage 2 Functional Head approver."""
    return HarnessContext.build_from_auth(
        user_id="201",
        user_role="Functional Head",
        dept_id=2,
        dept_name="Gas Processing Facilities",
        session_id="sess-fh-201",
        request_id="req-fh-002",
    )


@pytest.fixture
def risk_manager_context() -> HarnessContext:
    """Authenticated context for Stage 3 Risk Manager approver."""
    return HarnessContext.build_from_auth(
        user_id="301",
        user_role="Risk Manager",
        dept_id=2,
        dept_name="Gas Processing Facilities",
        session_id="sess-rm-301",
        request_id="req-rm-003",
    )


@pytest.fixture
def risk_head_context() -> HarnessContext:
    """Authenticated context for Stage 4 Risk Head (Final Approver)."""
    return HarnessContext.build_from_auth(
        user_id="401",
        user_role="Risk Head",
        dept_id=2,
        dept_name="Gas Processing Facilities",
        session_id="sess-rh-401",
        request_id="req-rh-004",
    )


@pytest.fixture
def auditor_context() -> HarnessContext:
    """Authenticated context for read-only Auditor."""
    return HarnessContext.build_from_auth(
        user_id="501",
        user_role="Auditor",
        dept_id=None,
        dept_name="Internal Audit",
        session_id="sess-aud-501",
        request_id="req-aud-005",
    )


@pytest.fixture
def admin_context() -> HarnessContext:
    """Authenticated context for Super Admin."""
    return HarnessContext.build_from_auth(
        user_id="1",
        user_role="Super Admin",
        dept_id=None,
        dept_name="Corporate Governance",
        session_id="sess-adm-001",
        request_id="req-adm-006",
    )


# =====================================================================
# 2. In-Memory Mock Database & Audit History Service
# =====================================================================
class InMemoryERMDatabase:
    """Stateful in-memory database simulating PostgreSQL 'ers' tables for integration tests."""

    def __init__(self):
        self.risks: Dict[str, Dict[str, Any]] = {
            "RSK-GAS-087": {
                "risk_register_id": 87,
                "risk_id": "RSK-GAS-087",
                "risk_name": "Pipeline Dust and Particle Contamination",
                "risk_description": "High velocity particulate accumulation in export gas pipeline.",
                "dept_id": 2,
                "dept_name": "Gas Processing Facilities",
                "risk_owner_id": 101,
                "risk_owner_name": "Karan Malhotra",
                "risk_status": 2, # Stage 2 (Submitted to FH)
                "risk_function_head_approval_status": 0,
                "risk_manager_approval_status": 0,
                "risk_head_approval_status": 0,
                "inherent_likelihood": 4,
                "inherent_impact": 4,
                "inherent_score": 16,
                "current_likelihood": 2,
                "current_impact": 3,
                "current_score": 6,
                "treatments": [
                    {
                        "treatment_id": 1,
                        "action_plan": "Install inline particulate filtration units.",
                        "action_owner_id": 101,
                        "progress": 30,
                        "target_date": "2026-12-31"
                    }
                ]
            }
        }
        self.history: List[Dict[str, Any]] = []
        self.email_jobs: List[Dict[str, Any]] = []

    def get_risk_details(self, risk_id: str, dept_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        risk = self.risks.get(risk_id.upper())
        if risk and dept_id and risk["dept_id"] != dept_id:
            return None
        return risk

    def search_risk_register(self, query: str = "", dept_id: Optional[int] = None, limit: int = 20) -> List[Dict[str, Any]]:
        results = []
        for r in self.risks.values():
            if dept_id and r["dept_id"] != dept_id:
                continue
            if query.lower() in r["risk_name"].lower() or query.lower() in r["risk_id"].lower():
                results.append(r)
        return results[:limit]

    def get_approval_queues(self, approver_role: str, dept_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
        role_lower = approver_role.lower()
        items = []
        for r in self.risks.values():
            if dept_id and r["dept_id"] != dept_id:
                continue
            if "functional head" in role_lower and r["risk_function_head_approval_status"] == 0 and r["risk_status"] == 2:
                items.append(r)
            elif "risk manager" in role_lower and r["risk_function_head_approval_status"] == 1 and r["risk_manager_approval_status"] == 0:
                items.append(r)
            elif ("risk head" in role_lower or "risk champion" in role_lower) and r["risk_manager_approval_status"] == 1 and r["risk_head_approval_status"] == 0:
                items.append(r)
        return items[:limit]

    def approve_or_reject_risk(self, risk_id: str, approver_id: int, action: str, remark: str) -> Dict[str, Any]:
        risk = self.risks.get(risk_id.upper())
        if not risk:
            return {"success": False, "status_code": 404, "message": f"Risk '{risk_id}' not found."}

        is_approve = action.lower() == "approve"
        current_status = risk["risk_status"]

        # Enforce FH -> RM -> RH sequence
        if current_status == 2: # Stage 2 FH
            if is_approve:
                risk["risk_function_head_approval_status"] = 1
                risk["risk_status"] = 3 # Moves to Stage 3 RM
                next_stage = "Stage 3 RM"
            else:
                risk["risk_function_head_approval_status"] = 2
                risk["risk_status"] = 5 # Returned / Rejected
                next_stage = "Returned to Risk Owner"
        elif current_status == 3: # Stage 3 RM
            if is_approve:
                risk["risk_manager_approval_status"] = 1
                risk["risk_status"] = 4 # Moves to Stage 4 RH
                next_stage = "Stage 4 RH"
            else:
                risk["risk_manager_approval_status"] = 2
                risk["risk_status"] = 5
                next_stage = "Returned to Risk Owner"
        elif current_status == 4: # Stage 4 RH
            if is_approve:
                risk["risk_head_approval_status"] = 1
                risk["risk_status"] = 1 # Fully Approved / Active
                next_stage = "Final Approval Signoff Complete"
            else:
                risk["risk_head_approval_status"] = 2
                risk["risk_status"] = 5
                next_stage = "Returned to Risk Owner"
        else:
            return {"success": False, "status_code": 400, "message": f"Risk '{risk_id}' is not in an active approval stage (status={current_status})."}

        # Record history
        hist_entry = {
            "risk_id": risk_id,
            "approver_id": approver_id,
            "action": action,
            "remark": remark,
            "new_status": risk["risk_status"],
            "timestamp": time.time(),
        }
        self.history.append(hist_entry)

        # Queue email notification
        email_job = {
            "recipient_role": "Risk Owner" if not is_approve else next_stage,
            "risk_id": risk_id,
            "action": action,
            "remark": remark,
        }
        self.email_jobs.append(email_job)

        return {
            "success": True,
            "status_code": 200,
            "risk_id": risk_id,
            "action": "Approved" if is_approve else "Rejected",
            "next_stage": next_stage,
            "remark": remark
        }

    def create_risk(self, risk_name: str, dept_id: int, **kwargs) -> Dict[str, Any]:
        count = len(self.risks) + 1
        new_id = f"RSK-GEN-{count:03d}"
        new_record = {
            "risk_register_id": count,
            "risk_id": new_id,
            "risk_name": risk_name,
            "dept_id": dept_id,
            "risk_status": 1, # Draft / Active
            "created_on": time.time(),
            **kwargs
        }
        self.risks[new_id] = new_record
        self.history.append({"risk_id": new_id, "action": "CREATE_RISK", "timestamp": time.time()})
        self.email_jobs.append({"type": "RISK_CREATED", "risk_id": new_id})
        return {
            "status": "success",
            "risk_id": new_id,
            "risk_register_id": count,
            "message": "Risk created successfully."
        }

    def add_risk_treatment(self, risk_register_id: int, action_plan: str, action_owner_id: int, target_date: str, progress: int = 0, **kw) -> Dict[str, Any]:
        for r in self.risks.values():
            if r["risk_register_id"] == risk_register_id:
                t_id = len(r.get("treatments", [])) + 1
                t_entry = {
                    "treatment_id": t_id,
                    "action_plan": action_plan,
                    "action_owner_id": action_owner_id,
                    "target_date": target_date,
                    "progress": progress
                }
                r.setdefault("treatments", []).append(t_entry)
                self.history.append({"risk_id": r["risk_id"], "action": "ADD_TREATMENT", "treatment_id": t_id})
                return {"success": True, "treatment_id": t_id, "message": "Treatment plan added."}
        return {"success": False, "message": "Risk register not found."}

    def update_treatment_progress(self, treatment_id: int, progress: int, modified_by: int = 1, remarks: Optional[str] = None, **kw) -> Dict[str, Any]:
        for r in self.risks.values():
            for t in r.get("treatments", []):
                if t.get("treatment_id") == treatment_id:
                    t["progress"] = progress
                    t["remarks"] = remarks
                    self.history.append({"risk_id": r["risk_id"], "action": "UPDATE_PROGRESS", "progress": progress, "by": modified_by})
                    return {"success": True, "treatment_id": treatment_id, "progress": progress, "remarks": remarks}
        return {"success": False, "message": "Treatment record not found."}


@pytest.fixture
def in_memory_db() -> InMemoryERMDatabase:
    """Fixture supplying an isolated in-memory ERM database instance."""
    return InMemoryERMDatabase()
