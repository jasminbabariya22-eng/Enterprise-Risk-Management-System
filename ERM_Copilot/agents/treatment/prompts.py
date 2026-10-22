"""
Enterprise Risk Management (ERM) - Prompts, Clarifications, and Preview Card Builders for Treatment Agent.
Generates concise, role-aware conversational prompts and UI chips.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from ERM_Copilot.agents.treatment.state import TreatmentSession


def format_missing_risk_prompt(session: TreatmentSession) -> str:
    """Prompt user to identify the target risk for treatment."""
    options = []
    for r in session.available_risks:
        rid = r.get("risk_id") or f"ID-{r.get('id')}"
        title = r.get("risk_title") or r.get("risk_name") or "Operational Hazard"
        options.append(f"{rid}: {title[:35]}...::Select Risk {rid}")

    dropdown_str = f"\n\n[select:🛡️ Select Target Risk...|{';'.join(options)}]" if options else ""
    return (
        f"### 🛡️ Select Target Risk\n\n"
        f"Which risk would you like to attach an additional Action Plan to?{dropdown_str}\n\n"
        f"👉 *Please provide or select a Risk ID (e.g. `RSK-GAS-049`):*"
    )


def format_missing_action_plan_prompt(session: TreatmentSession) -> str:
    """Prompt user for the mitigation action plan description with suggestions."""
    r_title = session.target_risk_name or "Operational Hazard"
    suggs = [
        f"Phase 1: Mobilize engineering crew for inspection and seal replacement on {r_title}.",
        f"Phase 2: Install automated safety interlocks and calibrate alarm setpoints for {r_title}.",
        f"Phase 3: Update plant preventive maintenance SOP and baseline vibration logs on {r_title}."
    ]
    session.action_plan_suggestions = suggs

    return (
        f"### 📝 Action Plan Details\n\n"
        f"**Target Risk:** **{session.target_risk_name or 'Risk'}** (`{session.target_risk_id}`)\n\n"
        f"Please describe the mitigation action plan, or choose one of these suggestions:\n\n"
        f"1. **Option 1:** {suggs[0]}\n"
        f"2. **Option 2:** {suggs[1]}\n"
        f"3. **Option 3:** {suggs[2]}\n\n"
        f"[btn:1️⃣ Option 1 Plan|Option 1] [btn:2️⃣ Option 2 Plan|Option 2] [btn:3️⃣ Option 3 Plan|Option 3]"
    )


def format_missing_action_owner_prompt(session: TreatmentSession) -> str:
    """Prompt user to designate an eligible Action Owner."""
    ao_options = []
    for u in session.available_action_owners:
        name = u.get("full_name") or u.get("log_id")
        role = u.get("role_name", "Action Owner")
        dname = u.get("dept_name", session.dept_name or "Department")
        ao_options.append(f"{name} ({role} - {dname})::Assign Action Owner {name}")

    dropdown_str = f"\n\n[select:👤 Select Action Owner...|{';'.join(ao_options)}]" if ao_options else ""
    return (
        f"### 👤 Assign Action Owner\n\n"
        f"**Target Risk:** `{session.target_risk_id}`\n\n"
        f"Who from your department should be responsible for executing this action plan?{dropdown_str}\n\n"
        f"👉 *Select an owner from the dropdown or type their name:*"
    )


def format_missing_treatment_id_prompt(session: TreatmentSession) -> str:
    """Prompt user for treatment ID."""
    return (
        "### 🔍 Target Treatment Required\n\n"
        "Which treatment or action plan would you like to update?\n\n"
        "👉 *Please specify the Treatment ID (e.g. `TRT-12`, `Treatment #14`):*"
    )


def format_missing_progress_prompt(session: TreatmentSession) -> str:
    """Prompt user for progress percentage."""
    return (
        f"### 📊 Progress Update for Treatment #{session.treatment_id}\n\n"
        f"What is the current execution progress percentage?\n\n"
        f"[btn:0% (Not Started)|0%] [btn:25% (Mobilized)|25%] [btn:50% (In Progress)|50%] [btn:75% (Testing)|75%] [btn:100% (Completed)|100%]"
    )


def format_missing_new_owner_prompt(session: TreatmentSession) -> str:
    """Prompt user for new action owner in reassignment mode."""
    ao_options = []
    for u in session.available_action_owners:
        name = u.get("full_name") or u.get("log_id")
        role = u.get("role_name", "Action Owner")
        ao_options.append(f"{name} ({role})::Assign {name}")

    dropdown_str = f"\n\n[select:👤 Select New Owner...|{';'.join(ao_options)}]" if ao_options else ""
    return (
        f"### 🔄 Reassign Action Owner for Treatment #{session.treatment_id}\n\n"
        f"Who should be the new designated Action Owner?{dropdown_str}\n\n"
        f"👉 *Select from dropdown or type personnel name:*"
    )


def format_add_treatment_preview(session: TreatmentSession) -> str:
    """Format markdown confirmation preview for adding a treatment."""
    status_label = "Completed" if session.progress >= 100 else ("In Progress" if session.progress > 0 else "Draft")
    return (
        f"### 📋 Action Plan Review — Confirm Mitigation Attachment\n\n"
        f"Please verify the action plan details before persisting to the Enterprise Register:\n\n"
        f"| Field | Proposed Value |\n"
        f"| :--- | :--- |\n"
        f"| **Target Risk** | **{session.target_risk_name or 'Risk'}** (`{session.target_risk_id}`) |\n"
        f"| **Action Plan** | {session.action_plan} |\n"
        f"| **Action Owner** | **{session.action_owner_name or 'Assigned Personnel'}** (ID: `{session.action_owner_id}`) |\n"
        f"| **Target Date** | `{session.target_date}` |\n"
        f"| **Progress** | `{session.progress}%` |\n"
        f"| **Initial Status** | `{status_label}` |\n\n"
        f"⚠️ *Note: Adding an action plan automatically resubmits draft/returned risks for Functional Head review.*\n\n"
        f"Do you want to confirm and save this action plan?\n\n"
        f"[btn-confirm:✅ Confirm & Save|confirm] [btn-cancel:❌ Cancel|cancel]"
    )


def format_update_progress_preview(session: TreatmentSession, current_progress: Optional[int] = None) -> str:
    """Format markdown preview for progress update."""
    curr_str = f"`{current_progress}%`" if current_progress is not None else "*Not recorded*"
    new_status = "Completed" if session.progress >= 100 else ("In Progress" if session.progress > 0 else "Draft")
    remark_str = f"\n| **Recorded Remark** | *\"{session.remarks}\"* |" if session.remarks else ""
    return (
        f"### 📊 Confirm Treatment Progress Update\n\n"
        f"Please verify the progress milestone change for Treatment **#{session.treatment_id}**:\n\n"
        f"| Parameter | Details |\n"
        f"| :--- | :--- |\n"
        f"| **Treatment ID** | `#{session.treatment_id}` |\n"
        f"| **Current Progress** | {curr_str} |\n"
        f"| **Proposed Progress** | **`{session.progress}%`** ({new_status}) |{remark_str}\n\n"
        f"Do you want to confirm this progress update?\n\n"
        f"[btn-confirm:✅ Confirm Update|confirm] [btn-cancel:❌ Cancel|cancel]"
    )


def format_reassign_owner_preview(session: TreatmentSession, current_owner: Optional[str] = None) -> str:
    """Format markdown preview for owner reassignment."""
    curr_str = f"**{current_owner}**" if current_owner else "*Current Assignee*"
    return (
        f"### 🔄 Confirm Action Owner Reassignment\n\n"
        f"Please verify the ownership transfer for Treatment **#{session.treatment_id}**:\n\n"
        f"| Parameter | Details |\n"
        f"| :--- | :--- |\n"
        f"| **Treatment ID** | `#{session.treatment_id}` |\n"
        f"| **Current Owner** | {curr_str} |\n"
        f"| **New Owner** | **{session.new_action_owner_name or 'Designated Assignee'}** (ID: `{session.new_action_owner_id}`) |\n\n"
        f"Do you want to confirm this reassignment?\n\n"
        f"[btn-confirm:✅ Confirm Reassignment|confirm] [btn-cancel:❌ Cancel|cancel]"
    )


def format_add_treatment_success(res: Dict[str, Any]) -> str:
    """Format success message after adding a treatment."""
    tid = res.get("risk_treatment_id")
    rid = res.get("risk_id")
    rname = res.get("risk_name") or "Risk"
    owner = res.get("action_owner_name") or "Action Owner"
    date_val = res.get("target_date")
    prog = res.get("progress", 0)
    return (
        f"### ✅ Action Plan Successfully Added!\n\n"
        f"Treatment task **#{tid}** has been formally persisted in the Enterprise Risk Register.\n\n"
        f"- **Target Risk:** **{rname}** (`{rid}`)\n"
        f"- **Assigned Action Owner:** **{owner}**\n"
        f"- **Target Completion Date:** `{date_val}`\n"
        f"- **Initial Progress:** `{prog}%`\n"
        f"- **Workflow Governance:** Resubmitted to Functional Head for Stage 1 sign-off.\n\n"
        f"👉 *You can track or update this action plan at any time by saying:* `\"Update progress of #{tid} to ...\"`"
    )


def format_update_progress_success(res: Dict[str, Any]) -> str:
    """Format success message after updating treatment progress."""
    tid = res.get("risk_treatment_id")
    prog = res.get("progress")
    status_label = res.get("status_label", "In Progress")
    return (
        f"### ✅ Treatment Progress Updated!\n\n"
        f"Progress for Treatment **#{tid}** has been updated to **`{prog}%`** ({status_label}).\n\n"
        f"The updated milestone is now reflected in the departmental workload dashboard."
    )


def format_reassign_owner_success(res: Dict[str, Any]) -> str:
    """Format success message after reassigning owner."""
    tid = res.get("risk_treatment_id")
    new_owner = res.get("action_owner_name")
    return (
        f"### ✅ Action Owner Successfully Reassigned!\n\n"
        f"Treatment **#{tid}** has been transferred to **{new_owner}**.\n\n"
        f"Audit logs and action assignment records have been updated."
    )


def format_list_treatments_response(treatments: List[Dict[str, Any]], risk_identifier: Optional[str] = None) -> str:
    """Format listing of treatments for a risk."""
    if not treatments:
        r_str = f" for risk **{risk_identifier}**" if risk_identifier else ""
        return (
            f"### 📋 Action Plans\n\n"
            f"No active treatment plans were found{r_str}.\n\n"
            f"👉 *To attach an action plan, reply:* `\"Add action plan for {risk_identifier or 'RSK-...'}\"`"
        )

    lines = [f"### 📋 Active Action Plans ({len(treatments)} found)\n"]
    if risk_identifier:
        lines.append(f"**Target Risk:** `{risk_identifier}`\n")

    lines.append("| ID | Action Plan | Owner | Due Date | Progress | Status |")
    lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")

    for t in treatments:
        tid = t.get("risk_treatment_id")
        plan = (t.get("action_plan") or "")[:35] + ("..." if len(t.get("action_plan") or "") > 35 else "")
        owner = t.get("action_owner_name") or "Unassigned"
        due = t.get("target_date") or "-"
        prog = f"{t.get('progress', 0)}%"
        status = t.get("action_status_name") or "Active"
        lines.append(f"| `#{tid}` | {plan} | {owner} | {due} | {prog} | {status} |")

    lines.append("\n👉 *To update any of these action plans, reply:* `\"Update progress of #{ID} to ...\"`")
    return "\n".join(lines)


def format_treatment_details_response(t: Dict[str, Any]) -> str:
    """Format detailed view of a single treatment record."""
    tid = t.get("risk_treatment_id")
    return (
        f"### 🛠️ Treatment #{tid} Details\n\n"
        f"| Field | Value |\n"
        f"| :--- | :--- |\n"
        f"| **Treatment ID** | `#{tid}` |\n"
        f"| **Linked Risk** | **{t.get('risk_name')}** (`{t.get('risk_id')}`) |\n"
        f"| **Action Plan** | {t.get('action_plan')} |\n"
        f"| **Action Owner** | **{t.get('action_owner_name')}** (`{t.get('action_owner_email') or 'N/A'}`) |\n"
        f"| **Target Date** | `{t.get('target_date')}` |\n"
        f"| **Progress** | `{t.get('progress')}%` |\n"
        f"| **Status** | `{t.get('action_status_name')}` |\n"
        f"| **Created On** | `{t.get('created_on')}` |"
    )


def format_policy_block_response(reason: str, target_id: Optional[str] = None) -> str:
    """Format policy rejection response."""
    return f"🚫 **Action Blocked by Governance Policy:**\n\n{reason}"


def format_cancellation_response(target_id: Optional[str] = None) -> str:
    """Format cancellation confirmation."""
    tgt_str = f" for `{target_id}`" if target_id else ""
    return f"🛑 **Treatment Action Cancelled:** The current operation{tgt_str} has been discarded. Session reset."


def format_missing_target_date_prompt(session: TreatmentSession) -> str:
    """Prompt user for target completion date."""
    return (
        f"### 📅 Target Completion Date\n\n"
        f"**Target Risk:** `{session.target_risk_id}`\n\n"
        f"When should this action plan be completed? You can specify a date (YYYY-MM-DD) or relative duration:\n\n"
        f"[btn:30 Days|+30 days] [btn:60 Days|+60 days] [btn:90 Days|+90 days] [btn:End of Year|2026-12-31]"
    )


# Backward-compatible prompt aliases
prompt_risk_selection = format_missing_risk_prompt
prompt_action_plan_step = format_missing_action_plan_prompt
prompt_action_owner_step = format_missing_action_owner_prompt
prompt_target_date_step = format_missing_target_date_prompt
prompt_progress_step = format_missing_progress_prompt
build_treatment_preview = format_add_treatment_preview

