"""
Prompt and Response Builders for the Approval Workflow Agent.
Provides formatted Markdown outputs for approval queues, risk cards,
audit timelines, confirmation gates, and policy advisories.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from ERM_Copilot.agents.approval_workflow.validation import ApprovalValidationResult


def format_pending_approvals_response(
    items: List[Dict[str, Any]],
    user_role: str,
    dept_name: Optional[str] = None
) -> str:
    """Format the list of risks pending approval at the user's governance stage."""
    if not items:
        scope = f"for **{dept_name}**" if dept_name else "across enterprise queues"
        return (
            f"### 📥 Approval Queue: All Clear\n\n"
            f"There are currently **no risks pending approval** {scope} for role **{user_role}**.\n\n"
            f"All submitted risks have either been reviewed or are pending action at another stage."
        )

    lines = [
        f"### 📥 Pending Approval Queue ({len(items)} Items)\n",
        f"The following risks require governance review for role **{user_role}**:\n",
        "| Risk ID | Risk Title | Department | Risk Owner | Actions |",
        "| :--- | :--- | :--- | :--- | :--- |"
    ]

    for r in items[:15]:
        r_id = r.get("risk_id") or f"RSK-{r.get('id', '')}"
        title = (r.get("risk_title") or r.get("risk_name") or "Untitled Risk").replace("|", "-")
        dept = r.get("department_name") or r.get("department") or "Enterprise"
        owner = r.get("owner_name") or "Risk Owner"
        
        btn_approve = f"[btn:✅ Approve|Approve {r_id}]"
        btn_details = f"[btn:🔍 Details|Show me the details of risk {r_id}]"
        lines.append(f"| **`{r_id}`** | {title} | {dept} | {owner} | {btn_approve} {btn_details} |")

    lines.append("\n👉 *Click an action button above, or type: `Approve <Risk ID>` or `Reject <Risk ID> because <reason>`.*")
    return "\n".join(lines)


def format_risk_details_response(risk: Dict[str, Any]) -> str:
    """Format full risk details and current approval status."""
    r_id = risk.get("risk_id") or f"RSK-{risk.get('risk_register_id', '')}"
    title = risk.get("risk_name") or risk.get("risk_title") or "Untitled Risk"
    dept = risk.get("department") or risk.get("department_name") or "Enterprise"
    owner = risk.get("owner_name") or "Risk Owner"
    fy = risk.get("financial_year") or "2026-2027"
    status = risk.get("current_status_name") or risk.get("status") or "Submitted for Review"

    desc = risk.get("description") or risk.get("risk_description") or "*No description provided.*"
    mitigation = risk.get("mitigation") or "*No mitigation strategy specified.*"

    inh_l = risk.get("inherent_likelihood") or risk.get("inherent_risk_likelihood_id") or 3
    inh_i = risk.get("inherent_impact") or risk.get("inherent_risk_impact_id") or 3
    inh_score = int(inh_l) * int(inh_i)

    # Approval indicators
    fh_status = "✅ Approved" if risk.get("fh_status") == 1 or risk.get("risk_function_head_approval_status") == 1 else "⏳ Pending"
    rm_status = "✅ Approved" if risk.get("rm_status") == 1 or risk.get("risk_manager_approval_status") == 1 else "⏳ Pending"
    rh_status = "✅ Approved" if risk.get("rh_status") == 1 or risk.get("risk_head_approval_status") == 1 else "⏳ Pending"

    text = (
        f"### 🛡️ Risk Details: **{r_id}**\n\n"
        f"**Title:** {title}\n\n"
        f"| Attribute | Value | Governance Stage | Status |\n"
        f"| :--- | :--- | :--- | :--- |\n"
        f"| **Department** | {dept} | **Stage 1 (FH)** | {fh_status} |\n"
        f"| **Risk Owner** | {owner} | **Stage 2 (RM)** | {rm_status} |\n"
        f"| **Financial Year** | {fy} | **Stage 3 (RH)** | {rh_status} |\n"
        f"| **Current Status** | `{status}` | **Overall Rating** | `{inh_l}×{inh_i}` (Score: {inh_score}) |\n\n"
        f"**Description:**\n{desc}\n\n"
        f"**Mitigation Strategy:**\n{mitigation}\n\n"
        f"👉 *Quick Actions:* [btn:✅ Approve {r_id}|Approve {r_id}] [btn:❌ Reject {r_id}|Reject {r_id}] [btn:📜 Approval History|Show the approval history for {r_id}]"
    )
    return text


def format_audit_trail_response(audit_data: Dict[str, Any]) -> str:
    """Format sequential approval lifecycle and audit timeline."""
    r_id = audit_data.get("risk_id") or "Risk"
    title = audit_data.get("risk_name") or audit_data.get("risk_title") or ""
    dept = audit_data.get("department") or "Enterprise"

    fh_status = audit_data.get("fh_status") or audit_data.get("risk_function_head_approval_status")
    fh_approver = audit_data.get("fh_approver") or "N/A"
    fh_on = audit_data.get("fh_on") or audit_data.get("risk_function_head_approval_on") or "-"
    fh_remark = audit_data.get("fh_remark") or audit_data.get("risk_function_head_approval_remark") or "-"

    rm_status = audit_data.get("rm_status") or audit_data.get("risk_manager_approval_status")
    rm_approver = audit_data.get("rm_approver") or "N/A"
    rm_on = audit_data.get("rm_on") or audit_data.get("risk_manager_approved_on") or "-"
    rm_remark = audit_data.get("rm_remark") or audit_data.get("risk_manager_approval_remark") or "-"

    rh_status = audit_data.get("rh_status") or audit_data.get("risk_head_approval_status")
    rh_approver = audit_data.get("rh_approver") or "N/A"
    rh_on = audit_data.get("rh_on") or audit_data.get("risk_head_approved_on") or "-"
    rh_remark = audit_data.get("rh_remark") or audit_data.get("risk_head_approval_remark") or "-"

    def _badge(st):
        if st == 1: return "✅ Approved"
        if st == -1: return "❌ Rejected / Returned"
        return "⏳ Pending"

    text = (
        f"### 📜 Governance Audit Trail: **{r_id}**\n\n"
        f"**Risk Title:** {title} ({dept})\n\n"
        f"| Governance Stage | Status | Reviewed By | Timestamp | Decision Remarks |\n"
        f"| :--- | :--- | :--- | :--- | :--- |\n"
        f"| **Stage 1: Functional Head** | {_badge(fh_status)} | {fh_approver} | {str(fh_on)[:19]} | {fh_remark} |\n"
        f"| **Stage 2: Risk Manager** | {_badge(rm_status)} | {rm_approver} | {str(rm_on)[:19]} | {rm_remark} |\n"
        f"| **Stage 3: Risk Head** | {_badge(rh_status)} | {rh_approver} | {str(rh_on)[:19]} | {rh_remark} |\n"
    )
    return text


def format_status_check_response(
    risk: Dict[str, Any],
    val_res: Optional[ApprovalValidationResult],
    user_role: str
) -> str:
    """Explain risk approval status and eligibility to approve."""
    r_id = risk.get("risk_id") or "Risk"
    title = risk.get("risk_name") or risk.get("risk_title") or ""

    if val_res and val_res.is_valid:
        return (
            f"### ℹ️ Risk Status for **{r_id}**\n\n"
            f"**Risk Title:** {title}\n\n"
            f"- **Current Pending Stage:** {val_res.stage_name}\n"
            f"- **Your Role:** **{user_role}**\n"
            f"- **Eligibility:** ✅ **You are currently authorized to review this risk.**\n\n"
            f"👉 Reply **`Approve {r_id}`** or **`Reject {r_id} because <reason>`** to proceed."
        )
    else:
        reason = val_res.policy_block_reason if val_res else "Unable to verify approval eligibility."
        return (
            f"### ℹ️ Risk Status for **{r_id}**\n\n"
            f"**Risk Title:** {title}\n\n"
            f"**Policy Advisory:**\n"
            f"{reason}\n\n"
            f"👉 *If you need more details, ask: \"Show the approval history for {r_id}\"*."
        )


def format_missing_risk_id_prompt(action: Optional[str] = None) -> str:
    """Prompt user for missing risk ID."""
    act_str = f" to {action}" if action else ""
    return (
        f"### 🛡️ Risk Identification Required\n\n"
        f"Which risk would you like{act_str}? Please provide the Risk ID (e.g., `HR-2106` or `RSK-GAS-049`).\n\n"
        f"👉 *You can type the Risk ID or pick an option below:*\n"
        f"[btn:📋 Show Pending Approvals|Show risks pending my approval] [btn:❌ Cancel|cancel]"
    )


def format_missing_action_prompt(risk_id: str) -> str:
    """Prompt user for decision action."""
    return (
        f"### 🛡️ Governance Decision Required for `{risk_id}`\n\n"
        f"Would you like to **Approve** or **Reject** risk `{risk_id}`?\n\n"
        f"[btn-confirm:✅ Approve {risk_id}|Approve {risk_id}] "
        f"[btn-cancel:❌ Reject {risk_id}|Reject {risk_id}] "
        f"[btn:🔙 Cancel|cancel]"
    )


def format_missing_remark_prompt(risk_id: str, action: str = "reject") -> str:
    """Prompt user for mandatory rejection remark or optional approval remark."""
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


def format_confirmation_prompt(
    risk_id: str,
    action: str,
    remark: Optional[str],
    stage_name: Optional[str] = None,
    risk_title: Optional[str] = None
) -> str:
    """Render the authoritative confirmation preview for governance sign-off."""
    is_app = (action.lower() == "approve")
    action_title = "Risk Approval Summary — Confirm Risk Governance Sign-Off" if is_app else "Risk Rejection Summary — Confirm Risk Governance Sign-Off"
    decision_badge = "✅ **Approve**" if is_app else "❌ **Reject / Return for Revision**"
    btn_confirm_label = "✅ Confirm Approval" if is_app else "❌ Confirm Rejection"
    btn_confirm_cmd = f"confirm {action}"
    
    stage_line = f"| **Governance Stage** | {stage_name} |\n" if stage_name else ""
    title_line = f"| **Risk Title** | {risk_title} |\n" if risk_title else ""
    remark_display = remark or (f"Approved via ERM Copilot" if is_app else "N/A")

    return (
        f"### 📋 {action_title}\n\n"
        f"Please verify your governance decision before submitting:\n\n"
        f"| Parameter | Details |\n"
        f"| :--- | :--- |\n"
        f"| **Risk ID** | `{risk_id}` |\n"
        f"{title_line}"
        f"{stage_line}"
        f"| **Decision** | {decision_badge} |\n"
        f"| **Recorded Remark** | *\"{remark_display}\"* |\n\n"
        f"Do you want to confirm this {action}?\n\n"
        f"[btn-confirm:{btn_confirm_label}|{btn_confirm_cmd}] [btn-cancel:❌ Cancel|cancel]"
    )


def format_policy_block_response(reason: str, risk_id: Optional[str] = None) -> str:
    """Render policy block notification."""
    r_hdr = f" for **{risk_id}**" if risk_id else ""
    return (
        f"### ⛔ Action Not Permitted{r_hdr}\n\n"
        f"{reason}\n\n"
        f"If you believe this is in error, please contact your Enterprise Risk Administrator."
    )


def format_success_response(result: Dict[str, Any]) -> str:
    """Render completion summary after successful tool execution."""
    action_str = str(result.get("action") or "approved").strip().lower()
    is_app = "app" in action_str or "sign" in action_str or "accept" in action_str
    status_badge = "✅ **Risk Approved Successfully & Signed Off**" if is_app else "❌ **Risk Rejected Successfully / Returned for Revision**"

    r_id = result.get("risk_id") or "Risk"
    reg_id = result.get("risk_register_id", "")
    title = result.get("risk_title", "Risk Item")
    approver = result.get("approver_name", "Authorized Approver")
    role = result.get("approver_role", "Governance Tier")
    stage = result.get("stage_name") or result.get("stage", "Stage Review")
    next_q = result.get("next_queue", "Active Register")
    ts = result.get("timestamp") or ""
    remark = result.get("remark") or "-"

    return (
        f"## {status_badge}\n\n"
        f"The risk record has been successfully updated in the **Enterprise Risk Management database**:\n\n"
        f"| Property | Persisted Value |\n"
        f"|---|---|\n"
        f"| **Risk Identifier** | `{r_id}` (Register #{reg_id}) |\n"
        f"| **Risk Title** | {title} |\n"
        f"| **Action Taken** | {result.get('action')} |\n"
        f"| **Authorized Approver** | {approver} ({role}) |\n"
        f"| **Governance Tier** | {stage} |\n"
        f"| **Next Review Queue** | `{next_q}` |\n"
        f"| **Approval Timestamp** | `{ts}` |\n"
        f"| **Recorded Remark** | *\"{remark}\"* |\n\n"
        f"🛡️ *Audit Confirmation: Immutable governance audit history record updated. Status is live on ERM Portal.*"
    )


def format_cancellation_response(risk_id: Optional[str] = None) -> str:
    """Render cancellation notification."""
    r_text = f" on risk **{risk_id}**" if risk_id else ""
    return (
        f"❌ **Action Cancelled.** The proposed sign-off{r_text} has been aborted and no changes were made.\n\n"
        f"How else may I assist you?"
    )
