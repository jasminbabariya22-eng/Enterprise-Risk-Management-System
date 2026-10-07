"""
Prompts and Preview Builders for Treatment Management Agent.
"""
from __future__ import annotations

from typing import List
from ERM_Copilot.agents.treatment.state import TreatmentSession, TreatmentState
from ERM_Copilot.services.db_service import erm_db


def prompt_risk_selection(session: TreatmentSession) -> str:
    session.state = TreatmentState.AWAITING_RISK_SELECTION
    recent_risks = erm_db.search_risks(department=session.dept_name, limit=6)
    session.available_risks = recent_risks

    options = []
    for r in recent_risks:
        rid = r.get("risk_id") or f"ID-{r.get('id')}"
        title = r.get("risk_title") or "Operational Risk"
        options.append(f"{rid}: {title[:40]}::Select Risk {rid}")

    dropdown_str = f"[select:🛡️ Select Target Risk...|{';'.join(options)}]" if options else ""

    return (
        f"### 🛡️ Step 1/5: Select Target Risk\n\n"
        f"Which risk would you like to attach an additional Action Plan to?\n\n"
        f"{dropdown_str}\n\n"
        f"👉 *Select a risk from the dropdown or type the Risk ID (e.g. `RSK-GAS-049`):*"
    )


def prompt_action_plan_step(session: TreatmentSession) -> str:
    session.state = TreatmentState.AWAITING_ACTION_PLAN
    r_title = session.target_risk_name or "Operational Hazard"
    
    suggs = [
        f"Phase 1: Mobilize engineering crew for inspection and seal replacement on {r_title}.",
        f"Phase 2: Install automated safety interlocks and calibrate alarm setpoints for {r_title}.",
        f"Phase 3: Update plant preventive maintenance SOP and baseline vibration logs on {r_title}."
    ]
    session.action_plan_suggestions = suggs

    return (
        f"### 🛡️ Step 2/5: Action Plan Details\n\n"
        f"**Target Risk:** `{session.target_risk_name}` (`{session.target_risk_id}`)\n\n"
        f"Please enter the structured action plan description, or choose one of these suggestions:\n\n"
        f"1. **Option 1:** {suggs[0]}\n"
        f"2. **Option 2:** {suggs[1]}\n"
        f"3. **Option 3:** {suggs[2]}\n\n"
        f"👉 *Select an option or type your custom action plan:*\n\n"
        f"[btn:1️⃣ Option 1 Plan|Option 1] [btn:2️⃣ Option 2 Plan|Option 2] [btn:3️⃣ Option 3 Plan|Option 3]"
    )


def prompt_action_owner_step(session: TreatmentSession) -> str:
    session.state = TreatmentState.AWAITING_ACTION_OWNER
    dept_action_owners = erm_db.get_department_action_owners(dept_id=session.dept_id, dept_name=session.dept_name)
    session.available_action_owners = dept_action_owners

    ao_options = []
    for u in dept_action_owners:
        name = u.get("full_name") or u.get("log_id")
        role = u.get("role_name", "Action Owner")
        dname = u.get("dept_name", session.dept_name or "General")
        ao_options.append(f"{name} ({role} - {dname})::Assign Action Owner {name}")

    dropdown_str = f"[select:👤 Select Action Owner...|{';'.join(ao_options)}]"

    return (
        f"### 🛡️ Step 3/5: Assign Action Owner\n\n"
        f"**Action Plan:** `{session.action_plan}`\n\n"
        f"Who from your department team should own the execution of this action plan?\n\n"
        f"{dropdown_str}\n\n"
        f"👉 *Select from dropdown or type a personnel name:*"
    )


def prompt_target_date_step(session: TreatmentSession) -> str:
    session.state = TreatmentState.AWAITING_TARGET_DATE
    return (
        f"### 🛡️ Step 4/5: Target Completion Date\n\n"
        f"**Action Owner:** `{session.action_owner_name}`\n\n"
        f"What is the target completion date for this action plan?\n\n"
        f"👉 *Select a timeline or enter a date (e.g. `2026-12-31`, `31-Dec-2026`):*\n\n"
        f"[btn:📅 +30 Days|+30 days] [btn:📅 +60 Days|+60 days] [btn:📅 +90 Days|+90 days]"
    )


def prompt_progress_step(session: TreatmentSession) -> str:
    session.state = TreatmentState.AWAITING_PROGRESS
    return (
        f"### 🛡️ Step 5/5: Current Progress Percentage\n\n"
        f"**Target Date:** `{session.target_date}`\n\n"
        f"What is the current execution progress percentage for this action plan?\n\n"
        f"[btn:0% (Not Started)|0%] [btn:25% (Mobilized)|25%] [btn:50% (In Progress)|50%] [btn:75% (Testing)|75%]"
    )


def build_treatment_preview(session: TreatmentSession) -> str:
    return (
        f"### 📋 Action Plan Review\n\n"
        f"Please review the action plan details before saving:\n\n"
        f"| Field | Value |\n"
        f"| :--- | :--- |\n"
        f"| **Target Risk** | **{session.target_risk_name}** (`{session.target_risk_id}`) |\n"
        f"| **Action Plan** | {session.action_plan} |\n"
        f"| **Action Owner** | **{session.action_owner_name}** (ID: `{session.action_owner_id}`) |\n"
        f"| **Target Date** | `{session.target_date}` |\n"
        f"| **Progress** | `{session.progress}%` |\n"
        f"| **Status** | `{'Completed' if session.progress >= 100 else ('In Progress' if session.progress > 0 else 'Draft')}` |\n\n"
        f"Do you want to save this action plan?\n\n"
        f"[btn-confirm:✅ Confirm & Save|Confirm and Save to Database] "
        f"[btn-cancel:❌ Cancel|Cancel Action Creation]"
    )
