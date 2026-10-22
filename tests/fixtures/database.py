import copy
import time
from typing import Dict, Any, List, Optional
from tests.fixtures.risks import TEST_RISKS


class TestDatabase:
    """Disposable, isolated in-memory test database."""

    def __init__(self):
        self.risks: Dict[str, Dict[str, Any]] = copy.deepcopy(TEST_RISKS)
        self.treatments: Dict[int, Dict[str, Any]] = {
            1: {
                "risk_treatment_id": 1,
                "risk_register_id": 49,
                "risk_id": "RSK-GAS-049",
                "action_plan": "Install automatic shutdown valves",
                "action_owner_id": 8,
                "action_owner_name": "Jasmin Babariya",
                "target_date": "2026-11-30",
                "progress": 50,
                "action_status_id": 7,
                "status_name": "In Progress",
                "dept_id": 2,
            }
        }
        self.history: List[Dict[str, Any]] = []
        self.email_jobs: List[Dict[str, Any]] = []

    def reset(self):
        self.risks = copy.deepcopy(TEST_RISKS)
        self.treatments.clear()
        self.history.clear()
        self.email_jobs.clear()

    def get_risk_by_id(self, risk_id: str) -> Optional[Dict[str, Any]]:
        return self.risks.get(risk_id.upper())

    def search_risks(self, query: str = "", department: str = "", limit: int = 10) -> List[Dict[str, Any]]:
        results = []
        q = query.lower()
        dept = department.lower()
        for r in self.risks.values():
            if dept and dept not in str(r.get("department", "")).lower():
                continue
            if q and q not in str(r.get("risk_name", "")).lower() and q not in str(r.get("risk_id", "")).lower():
                continue
            results.append(r)
        return results[:limit]

    def create_risk(self, risk_name: str = "", dept_id: int = 1, user_id: int = 1, risk_data: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        data = risk_data or {}
        name = risk_name or data.get("risk_name") or kwargs.get("risk_name", "Untitled Risk")
        dept = kwargs.get("department") or data.get("department", "General")
        u_id = user_id or data.get("owner_id", 1)
        risk_id = data.get("risk_id") or kwargs.get("risk_id") or f"RSK-GEN-{len(self.risks) + 1:03d}"
        entry = {
            "risk_id": risk_id,
            "risk_name": name,
            "dept_id": dept_id,
            "department": dept,
            "owner_id": u_id,
            "owner_name": kwargs.get("owner_name") or data.get("owner_name", "Risk Owner"),
            "risk_status": 2, # Submitted to FH
            "risk_function_head_approval_status": 0,
            "risk_manager_approval_status": 0,
            "risk_head_approval_status": 0,
            "inherent_score": kwargs.get("inherent_score") or data.get("inherent_score", 15),
            "residual_score": kwargs.get("residual_score") or data.get("residual_score", 6),
            "created_at": time.time(),
        }
        self.risks[risk_id.upper()] = entry
        self.history.append({
            "risk_id": risk_id,
            "action": "create",
            "user_id": u_id,
            "timestamp": time.time(),
        })
        return {"status": "success", "success": True, "risk_id": risk_id, "data": entry}

    def approve_or_reject_risk(self, risk_id: str, approver_id: int, action: str, remark: str = "") -> Dict[str, Any]:
        risk = self.risks.get(risk_id.upper())
        if not risk:
            return {"success": False, "status_code": 404, "message": f"Risk '{risk_id}' not found."}

        is_approve = action.lower() == "approve"
        current_status = risk.get("risk_status", 2)

        if current_status == 2:  # FH Stage
            if is_approve:
                risk["risk_function_head_approval_status"] = 1
                risk["risk_status"] = 3  # Moves to RM
                next_stage = "Stage 3 RM"
            else:
                risk["risk_function_head_approval_status"] = 2
                risk["risk_status"] = 5  # Returned / Rejected
                next_stage = "Returned to Risk Owner"
        elif current_status == 3:  # RM Stage
            if is_approve:
                risk["risk_manager_approval_status"] = 1
                risk["risk_status"] = 4  # Moves to RH
                next_stage = "Stage 4 RH"
            else:
                risk["risk_manager_approval_status"] = 2
                risk["risk_status"] = 5
                next_stage = "Returned to Risk Owner"
        elif current_status == 4:  # RH Stage
            if is_approve:
                risk["risk_head_approval_status"] = 1
                risk["risk_status"] = 1  # Final Active
                next_stage = "Final Approval Signoff Complete"
            else:
                risk["risk_head_approval_status"] = 2
                risk["risk_status"] = 5
                next_stage = "Returned to Risk Owner"
        else:
            return {"success": False, "status_code": 400, "message": f"Risk '{risk_id}' not in approval queue."}

        # Audit History
        self.history.append({
            "risk_id": risk_id,
            "approver_id": approver_id,
            "action": action,
            "remark": remark,
            "new_status": risk["risk_status"],
            "timestamp": time.time(),
        })

        # Email Notification Job
        self.email_jobs.append({
            "recipient_role": "Risk Owner" if not is_approve else next_stage,
            "risk_id": risk_id,
            "action": action,
            "remark": remark,
            "queued_at": time.time(),
        })

        return {
            "success": True,
            "status_code": 200,
            "risk_id": risk_id,
            "new_status": risk["risk_status"],
            "next_stage": next_stage,
            "message": f"Risk {risk_id} successfully processed with action '{action}'."
        }

    def add_risk_treatment(
        self,
        risk_register_id: int,
        action_plan: str,
        action_owner_id: int,
        target_date: Optional[str] = None,
        progress: int = 0,
        action_status_id: int = 1,
        created_by: int = 1,
    ) -> Dict[str, Any]:
        t_id = len(self.treatments) + 1
        entry = {
            "risk_treatment_id": t_id,
            "risk_register_id": risk_register_id,
            "risk_id": f"RSK-GEN-{risk_register_id:03d}",
            "action_plan": action_plan,
            "action_owner_id": action_owner_id,
            "action_owner_name": "Test Action Owner",
            "target_date": target_date or "2026-12-31",
            "progress": progress,
            "action_status_id": action_status_id,
            "created_by": created_by,
            "created_on": time.time(),
        }
        self.treatments[t_id] = entry
        return {
            "status": "success",
            "risk_treatment_id": t_id,
            "risk_register_id": risk_register_id,
            "action_plan": action_plan,
            "action_owner_id": action_owner_id,
            "progress": progress,
            "action_status_id": action_status_id,
        }

    def update_treatment_progress(
        self,
        treatment_id: int,
        progress: int,
        modified_by: int = 1,
        remarks: Optional[str] = None,
    ) -> Dict[str, Any]:
        t = self.treatments.get(treatment_id)
        if not t:
            return {"status": "error", "message": f"Treatment #{treatment_id} not found."}
        t["progress"] = progress
        t["action_status_id"] = 8 if progress >= 100 else (7 if progress > 0 else 1)
        t["status_name"] = "Completed" if progress >= 100 else ("In Progress" if progress > 0 else "Draft")
        t["modified_by"] = modified_by
        t["remarks"] = remarks
        return {
            "status": "success",
            "risk_treatment_id": treatment_id,
            "progress": progress,
            "action_status_id": t["action_status_id"],
            "status_name": t["status_name"],
        }

    def reassign_treatment_owner(
        self,
        treatment_id: int,
        new_action_owner_id: int,
        modified_by: int = 1,
    ) -> Dict[str, Any]:
        t = self.treatments.get(treatment_id)
        if not t:
            return {"status": "error", "message": f"Treatment #{treatment_id} not found."}
        t["action_owner_id"] = new_action_owner_id
        t["action_owner_name"] = f"Action Owner #{new_action_owner_id}"
        t["modified_by"] = modified_by
        return {
            "status": "success",
            "risk_treatment_id": treatment_id,
            "new_action_owner_id": new_action_owner_id,
            "action_owner_name": t["action_owner_name"],
        }

    def get_risk_treatments(self, risk_id: Optional[str] = None, risk_register_id: Optional[int] = None) -> List[Dict[str, Any]]:
        results = []
        for t in self.treatments.values():
            if risk_id and str(t.get("risk_id", "")).upper() == str(risk_id).upper():
                results.append(t)
            elif risk_register_id and t.get("risk_register_id") == risk_register_id:
                results.append(t)
        return results

    def get_treatment_details(self, treatment_id: int) -> Optional[Dict[str, Any]]:
        return self.treatments.get(treatment_id)
