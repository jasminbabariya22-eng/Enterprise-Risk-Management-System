"""
Prompts and formatters for LangGraph Approval Workflow.
"""
from typing import Dict, Any, Optional

EXTRACTION_SYSTEM_PROMPT = """You are an Enterprise Risk Management (ERM) Governance Assistant.
Your task is to analyze the user's message and extract risk decision parameters:
1. `risk_id`: The risk code/identifier (e.g., "HR-2106", "RSK-GAS-049", "RSK-001", "49").
2. `action`: Either "approve" (for approval/signoff) or "reject" (for return/rejection). If not clear, null.
3. `remark`: The rationale, justification, reason, or remark provided in the message. If no reason is given, null.

Examples:
- "Approve HR-2106 because the mitigation plan is adequate." -> {"risk_id": "HR-2106", "action": "approve", "remark": "The mitigation plan is adequate."}
- "Approve HR-2106" -> {"risk_id": "HR-2106", "action": "approve", "remark": null}
- "Reject HR-2106 because the mitigation plan is insufficient." -> {"risk_id": "HR-2106", "action": "reject", "remark": "The mitigation plan is insufficient."}
- "Reject HR-2106" -> {"risk_id": "HR-2106", "action": "reject", "remark": null}
- "Please sign off risk RSK-GAS-047" -> {"risk_id": "RSK-GAS-047", "action": "approve", "remark": null}
- "I don't approve HR-2106 because the action plan needs revision." -> {"risk_id": "HR-2106", "action": "reject", "remark": "The action plan needs revision."}
"""


def format_missing_risk_id_prompt(action: Optional[str] = None) -> str:
    act_str = f" to {action}" if action else ""
    return (
        f"### 🛡️ Risk Identification Required\n\n"
        f"Which risk would you like{act_str}? Please provide the Risk ID (e.g., `HR-2106` or `RSK-GAS-049`).\n\n"
        f"👉 *You can type the Risk ID or pick an option below:*\n"
        f"[btn:📋 Show Pending Approvals|Show risks pending my approval] [btn:❌ Cancel|cancel]"
    )


def format_missing_action_prompt(risk_id: str) -> str:
    return (
        f"### 🛡️ Governance Decision Required for `{risk_id}`\n\n"
        f"Would you like to **Approve** or **Reject** risk `{risk_id}`?\n\n"
        f"[btn-confirm:✅ Approve {risk_id}|Approve {risk_id}] "
        f"[btn-cancel:❌ Reject {risk_id}|Reject {risk_id}] "
        f"[btn:🔙 Cancel|cancel]"
    )


def format_missing_remark_prompt(risk_id: str, action: str) -> str:
    if action == "approve":
        return (
            f"### ✍️ Approval Remark Required\n\n"
            f"Please provide your **approval remark** or sign-off comment for risk `{risk_id}`.\n\n"
            f"> *Example:* `The mitigation plan is adequate and residual risk is acceptable.`\n\n"
            f"[btn:The mitigation plan is adequate|The mitigation plan is adequate and residual risk is acceptable.] "
            f"[btn-cancel:❌ Cancel|cancel]"
        )
    else:
        return (
            f"### ⚠️ Rejection Reason Required\n\n"
            f"Please provide the **reason for rejecting** risk `{risk_id}`.\n\n"
            f"> *Example:* `Mitigation controls are insufficient and require revision.`\n\n"
            f"[btn:Controls are insufficient|Mitigation controls are insufficient and require revision.] "
            f"[btn-cancel:❌ Cancel|cancel]"
        )


def format_confirmation_prompt(risk_id: str, action: str, remark: str) -> str:
    is_app = (action == "approve")
    action_title = "Risk Approval Summary" if is_app else "Risk Rejection Summary"
    decision_badge = "✅ **Approve**" if is_app else "❌ **Reject / Return for Revision**"
    btn_confirm_label = "✅ Confirm Approval" if is_app else "❌ Confirm Rejection"
    btn_confirm_cmd = f"confirm {action}"
    
    return (
        f"### 📋 {action_title}\n\n"
        f"Please verify your governance decision before submitting:\n\n"
        f"| Parameter | Details |\n"
        f"| :--- | :--- |\n"
        f"| **Risk ID** | `{risk_id}` |\n"
        f"| **Decision** | {decision_badge} |\n"
        f"| **Recorded Remark** | *\"{remark}\"* |\n\n"
        f"Do you want to confirm this {action}?\n\n"
        f"[btn-confirm:{btn_confirm_label}|{btn_confirm_cmd}] [btn-cancel:❌ Cancel|cancel]"
    )


def format_success_response(result: Dict[str, Any]) -> str:
    action_str = str(result.get("action") or "approved").strip().lower()
    is_app = "app" in action_str or "sign" in action_str or "accept" in action_str
    status_badge = "✅ **Risk Approved & Signed Off**" if is_app else "❌ **Risk Rejected / Returned for Revision**"
    
    return (
        f"## {status_badge}\n\n"
        f"The risk record has been successfully updated in the **Enterprise Risk Management database**:\n\n"
        f"| Property | Persisted Value |\n"
        f"|---|---|\n"
        f"| **Risk Identifier** | `{result.get('risk_id')}` (Register #{result.get('risk_register_id')}) |\n"
        f"| **Risk Title** | {result.get('risk_title', 'Risk Item')} |\n"
        f"| **Action Taken** | {result.get('action')} |\n"
        f"| **Authorized Approver** | {result.get('approver_name', 'Authorized Approver')} ({result.get('approver_role', 'Governance Tier')}) |\n"
        f"| **Governance Tier** | {result.get('stage', 'Stage Review')} |\n"
        f"| **Next Review Queue** | `{result.get('next_queue', 'Completed')}` |\n"
        f"| **Approval Timestamp** | `{result.get('timestamp')}` |\n"
        f"| **Recorded Remark** | *\"{result.get('remark')}\"* |\n\n"
        f"🛡️ *Audit Confirmation: Immutable governance audit history record updated. Status is live on ERM Portal.*"
    )


def format_error_response(message: str, risk_id: Optional[str] = None) -> str:
    rid_str = f" for `{risk_id}`" if risk_id else ""
    return (
        f"### ⚠️ Governance Operation Failed{rid_str}\n\n"
        f"{message}\n\n"
        f"👉 *You can try again or check current approval queues:*\n"
        f"[btn:📋 Show Pending Approvals|Show risks pending my approval]"
    )


def format_cancellation_response(risk_id: Optional[str] = None) -> str:
    rid_str = f" for `{risk_id}`" if risk_id else ""
    return (
        f"### 🛑 Governance Decision Cancelled\n\n"
        f"The requested approval/rejection operation{rid_str} has been cancelled. No changes were made to the risk register or audit trail.\n\n"
        f"[btn:📋 Show Pending Approvals|Show risks pending my approval] [btn:🛡️ Show Open Risks|Show my open risks]"
    )
