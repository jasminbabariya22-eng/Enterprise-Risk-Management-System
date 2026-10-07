"""
Generic Approval Tool for ERM Copilot.
Acts as the single point of execution to the authenticated FastAPI / ERM database backend.
"""
import logging
from typing import Literal, Dict, Any, Optional
from ERM_Copilot.services.db_service import erm_db

logger = logging.getLogger("ERM_Copilot.agents.approval.tools")


def approve_or_reject_risk(
    risk_id: str,
    action: Literal["approve", "reject"],
    remark: str,
    approver_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Execute an approved/rejected risk decision through the authenticated ERM backend.
    
    The backend determines the actual:
    - user and identity verification
    - actual user role & governance tier
    - current approval stage sequence (Stage 2 FH -> Stage 3 RM -> Stage 4 RH)
    - authorization and permissions
    
    Args:
        risk_id: Identifier of the risk (e.g., 'HR-2106', 'RSK-GAS-049').
        action: User requested decision ('approve' or 'reject').
        remark: Non-empty user-supplied remark or justification.
        approver_id: Authenticated user ID (injected from verified session context, NOT from LLM).
        
    Returns:
        Dict[str, Any]: Execution result from the backend.
    """
    # 1. Validate risk_id
    if not risk_id or not str(risk_id).strip():
        return {
            "success": False,
            "status_code": 400,
            "message": "A valid risk identifier (e.g., 'HR-2106', 'RSK-GAS-049') is required."
        }
    clean_risk_id = str(risk_id).strip()

    # 2. Validate action
    if not action or action.lower() not in ["approve", "reject"]:
        return {
            "success": False,
            "status_code": 400,
            "message": "Invalid action. Decision must be either 'approve' or 'reject'."
        }
    clean_action = action.lower()

    # 3. Validate remark - Never allow empty, blank, or fabricated remarks
    if not remark or not str(remark).strip():
        action_title = "an approval remark" if clean_action == "approve" else "a reason for rejection"
        return {
            "success": False,
            "status_code": 400,
            "message": f"A mandatory remark is required. Please provide {action_title}."
        }
    clean_remark = str(remark).strip()

    # 4. Validate authenticated approver_id - Strict security check
    if approver_id is None:
        return {
            "success": False,
            "status_code": 401,
            "message": "Authentication required. No authenticated user identity was provided."
        }
    
    try:
        valid_approver_id = int(approver_id)
        if valid_approver_id <= 0:
            return {
                "success": False,
                "status_code": 401,
                "message": "Authentication failure: Invalid approver identifier."
            }
    except (ValueError, TypeError):
        return {
            "success": False,
            "status_code": 401,
            "message": f"Authentication failure: Invalid approver identifier '{approver_id}'."
        }

    # 5. Call existing backend approval engine
    try:
        result = erm_db.approve_or_reject_risk(
            risk_id=clean_risk_id,
            approver_id=valid_approver_id,
            action=clean_action,
            remark=clean_remark
        )
        return result
    except Exception as e:
        logger.error(f"Error calling backend approval engine for {clean_risk_id}: {e}", exc_info=True)
        return {
            "success": False,
            "status_code": 500,
            "message": f"Backend approval engine error: {str(e)}"
        }
