"""
Prompts, Preview Builders, and Step UI Components for Risk Creation Agent.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from ERM_Copilot.agents.risk_creation.scoring import RiskMatrixCalculator
from ERM_Copilot.agents.risk_creation.state import RiskCreationSession, RiskCreationState
from ERM_Copilot.agents.risk_creation.suggestions import static_suggestion_provider
from ERM_Copilot.services.db_service import erm_db


def build_preview(session: RiskCreationSession) -> str:
    """Construct the Markdown preview table showing all verified risk parameters."""
    l_val = session.inherent_likelihood or 3
    i_val = session.inherent_impact or 4
    score = session.inherent_score or (l_val * i_val)
    badge = session.inherent_badge or "[HIGH]"
    l_name = RiskMatrixCalculator.LIKELIHOOD_LABELS.get(l_val, "Possible")
    i_name = RiskMatrixCalculator.IMPACT_LABELS.get(i_val, "Major")

    c_l = session.current_likelihood or 2
    c_i = session.current_impact or 2
    c_score = session.current_score or (c_l * c_i)
    c_badge = session.current_badge or f"[{session.current_level or 'LOW'}]"
    c_l_name = RiskMatrixCalculator.LIKELIHOOD_LABELS.get(c_l, "Unlikely")
    c_i_name = RiskMatrixCalculator.IMPACT_LABELS.get(c_i, "Minor")

    t_date_display = session.target_date or (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")

    preview = (
        f"### 📋 Risk Creation – Final Review\n\n"
        f"Please review the compiled risk details before confirmation:\n\n"
        f"| Field | Value |\n"
        f"| :--- | :--- |\n"
        f"| **Risk Name** | **{session.risk_name}** |\n"
        f"| **Risk Owner** | Authenticated User (ID: `{session.user_id}`) |\n"
        f"| **Risk Co-Owner** | {session.risk_co_owner_name or 'None'} |\n"
        f"| **Department** | {session.dept_name or 'General'} (ID: {session.dept_id or 'N/A'}) |\n"
        f"| **Risk Description** | {session.risk_description} |\n"
        f"| **Inherent Likelihood** | {l_val} ({l_name}) |\n"
        f"| **Inherent Impact** | {i_val} ({i_name}) |\n"
        f"| **Inherent Score** | **{score} / 25 {badge}** |\n"
        f"| **Inherent Level** | `{session.inherent_level or 'HIGH'}` |\n"
        f"| **Mitigation** | {session.mitigation} |\n"
        f"| **Current Likelihood** | {c_l} ({c_l_name}) |\n"
        f"| **Current Impact** | {c_i} ({c_i_name}) |\n"
        f"| **Current Score** | **{c_score} / 25 {c_badge}** |\n"
        f"| **Current Level** | `{session.current_level or 'LOW'}` |\n"
        f"| **Action Plan** | {session.action_plan} |\n"
        f"| **Action Owner** | **{session.action_owner_name or 'Unassigned'}** |\n"
        f"| **Target Date** | `{t_date_display}` |\n"
        f"| **Status** | `{session.status_name}` (ID: {session.status_id}) |\n\n"
        f"Do you want to save this risk?\n\n"
        f"[btn-confirm:✅ Confirm & Save|Confirm and Save to Database] "
        f"[btn-cancel:❌ Cancel|Cancel Risk Creation]\n\n"
        f"💡 *To modify any value, type e.g. `Change target date to 2026-12-31`, `Change mitigation to ...`, or `Change status to Submit`.*"
    )
    return preview


def prompt_risk_name(session: RiskCreationSession) -> str:
    session.state = RiskCreationState.AWAITING_RISK_NAME
    return (
        "### 🛡️ Step 1/10: Risk Name / Title\n\n"
        "What is the risk name or title?"
    )


def prompt_co_owner(session: RiskCreationSession) -> str:
    session.state = RiskCreationState.AWAITING_CO_OWNER
    co_users = erm_db.get_all_users_for_co_owner(limit=25)
    session.available_co_owners = co_users

    co_options = ["None / Skip Co-Owner::Skip Co-Owner"]
    for u in co_users:
        name = u.get("full_name") or u.get("log_id")
        role = u.get("role_name", "Team Member")
        dname = u.get("dept_name", "Enterprise")
        co_options.append(f"{name} ({role} - {dname})::Assign Co-Owner {name}")

    dropdown_str = f"[select:👤 Select Risk Co-Owner...|{';'.join(co_options)}]"

    return (
        f"### 🛡️ Step 2/10: Risk Co-Owner (Optional)\n\n"
        f"**Risk Title:** `{session.risk_name}`\n\n"
        f"Please select a **Risk Co-Owner** from the registered enterprise users dropdown below, or click **Skip**:\n\n"
        f"{dropdown_str} [btn:⏩ Skip / None|Skip Co-Owner]"
    )


def prompt_description(session: RiskCreationSession) -> str:
    session.state = RiskCreationState.AWAITING_DESCRIPTION
    title = session.risk_name or "Operational Hazard"
    suggs = static_suggestion_provider.get_description_suggestions(title)
    session.desc_options = suggs

    opt1 = suggs[0] if len(suggs) > 0 else f"Operational risk on {title} causing asset downtime."
    opt2 = suggs[1] if len(suggs) > 1 else f"Integrity degradation and safety hazard on {title}."
    opt3 = suggs[2] if len(suggs) > 2 else f"Process deviation and containment risk on {title}."

    return (
        f"### 🛡️ Step 3/10: Risk Description\n\n"
        f"**Risk Title:** `{title}` | **Co-Owner:** `{session.risk_co_owner_name or 'None'}`\n\n"
        f"Please provide the risk description.\n\n"
        f"You can write your own description, or choose one of these suggestions:\n\n"
        f"1. **Option 1:** {opt1}\n"
        f"2. **Option 2:** {opt2}\n"
        f"3. **Option 3:** {opt3}\n\n"
        f"👉 *Select an option below or type your custom description:*\n\n"
        f"[btn:1️⃣ Option 1|Option 1 Description] "
        f"[btn:2️⃣ Option 2|Option 2 Description] "
        f"[btn:3️⃣ Option 3|Option 3 Description]"
    )


def prompt_inherent_assessment(session: RiskCreationSession) -> str:
    session.state = RiskCreationState.AWAITING_INHERENT_ASSESSMENT
    return (
        f"### 🛡️ Step 4/10: Inherent Risk Assessment (5×5 Matrix)\n\n"
        f"**Risk Title:** `{session.risk_name}`\n\n"
        f"Please select both **Likelihood (1–5)** and **Impact (1–5)** from the dropdowns below (both are mandatory). The system will calculate the Inherent Risk Score and Severity Level:\n\n"
        f"[assessment-matrix:inherent]"
    )


def prompt_mitigation(session: RiskCreationSession) -> str:
    session.state = RiskCreationState.AWAITING_MITIGATION
    title = session.risk_name or "Operational Hazard"
    suggs = static_suggestion_provider.get_mitigation_suggestions(title)
    session.mitigation_options = suggs

    opt1 = suggs[0] if len(suggs) > 0 else "Implement engineering containment and component overhaul."
    opt2 = suggs[1] if len(suggs) > 1 else "Install automated sensors and emergency interlocks."
    opt3 = suggs[2] if len(suggs) > 2 else "Perform ultrasonic NDT inspection and scheduled maintenance."

    l_val = session.inherent_likelihood or 3
    i_val = session.inherent_impact or 4
    l_name = RiskMatrixCalculator.LIKELIHOOD_LABELS.get(l_val, "Possible")
    i_name = RiskMatrixCalculator.IMPACT_LABELS.get(i_val, "Major")

    return (
        f"### 🛡️ Step 5/10: Mitigation / Treatment Strategy\n\n"
        f"**Inherent Severity:** Likelihood {l_val} ({l_name}) × Impact {i_val} ({i_name}) = **{session.inherent_score} / 25 {session.inherent_badge}**\n\n"
        f"What mitigation or treatment should be applied?\n\n"
        f"Suggested mitigation options:\n\n"
        f"1. **Option 1 (Engineering Control):** {opt1}\n"
        f"2. **Option 2 (Safety Interlock & Sensors):** {opt2}\n"
        f"3. **Option 3 (Inspection & Maintenance):** {opt3}\n\n"
        f"👉 *Select one or enter your custom mitigation:*\n\n"
        f"[btn:1️⃣ Option 1: Engineering Control|Option 1 Engineering Control] "
        f"[btn:2️⃣ Option 2: Safety Interlocks|Option 2 Safety Interlock] "
        f"[btn:3️⃣ Option 3: Inspection Routine|Option 3 Inspection Routine]"
    )


def prompt_current_assessment(session: RiskCreationSession) -> str:
    session.state = RiskCreationState.AWAITING_CURRENT_ASSESSMENT
    return (
        f"### 🛡️ Step 6/10: Current / Residual Risk Assessment (5×5 Matrix)\n\n"
        f"**Mitigation Applied:** `{session.mitigation}`\n\n"
        f"Please select both **Current Likelihood (1–5)** and **Current Impact (1–5)** after mitigation from the dropdowns below (both are mandatory):\n\n"
        f"[assessment-matrix:current]"
    )


def prompt_action_plan(session: RiskCreationSession) -> str:
    session.state = RiskCreationState.AWAITING_ACTION_PLAN
    title = session.risk_name or "Operational Hazard"
    suggs = static_suggestion_provider.get_action_plan_suggestions(title, session.mitigation)
    session.action_plan_options = suggs

    opt1 = suggs[0] if len(suggs) > 0 else "Phase 1: Mobilize maintenance crew for physical barrier overhaul."
    opt2 = suggs[1] if len(suggs) > 1 else "Phase 2: Procure certified replacement parts and calibrate DCS trips."
    opt3 = suggs[2] if len(suggs) > 2 else "Phase 3: Update plant preventive maintenance SOP and baseline log."

    c_l = session.current_likelihood or 2
    c_i = session.current_impact or 2
    c_l_name = RiskMatrixCalculator.LIKELIHOOD_LABELS.get(c_l, "Unlikely")
    c_i_name = RiskMatrixCalculator.IMPACT_LABELS.get(c_i, "Minor")

    return (
        f"### 🛡️ Step 7/10: Action Plan\n\n"
        f"**Current / Residual Severity:** Likelihood {c_l} ({c_l_name}) × Impact {c_i} ({c_i_name}) = **{session.current_score} / 25 {session.current_badge}**\n\n"
        f"What is the structured action plan?\n\n"
        f"Suggested action plan options:\n\n"
        f"1. **Option 1:** {opt1}\n"
        f"2. **Option 2:** {opt2}\n"
        f"3. **Option 3:** {opt3}\n\n"
        f"👉 *Select one, edit it, or enter your custom action plan:*\n\n"
        f"[btn:1️⃣ Option 1 Plan|Option 1 Action Plan] "
        f"[btn:2️⃣ Option 2 Plan|Option 2 Action Plan] "
        f"[btn:3️⃣ Option 3 Plan|Option 3 Action Plan]"
    )


def prompt_action_owner(session: RiskCreationSession) -> str:
    session.state = RiskCreationState.AWAITING_ACTION_OWNER
    dept_action_owners = erm_db.get_department_action_owners(
        dept_id=session.dept_id,
        dept_name=session.dept_name
    )
    session.available_action_owners = dept_action_owners

    if not dept_action_owners:
        return (
            f"### 🛡️ Step 8/10: Assign Action Owner\n\n"
            f"⚠️ No active Action Owners were found registered for department **{session.dept_name or 'General'}**.\n\n"
            f"Please enter the name, login ID, or employee ID of the designated Action Owner:"
        )

    ao_options = []
    for u in dept_action_owners:
        name = u.get("full_name") or u.get("log_id")
        role = u.get("role_name", "Action Owner")
        dname = u.get("dept_name", session.dept_name or "General")
        ao_options.append(f"{name} ({role} - {dname})::Assign Action Owner {name}")

    dropdown_str = f"[select:👤 Select Action Owner...|{';'.join(ao_options)}]"

    return (
        f"### 🛡️ Step 8/10: Assign Action Owner\n\n"
        f"**Department Scope:** `{session.dept_name or 'General'}` (ID: {session.dept_id or 'N/A'})\n\n"
        f"Please select an **Action Owner** from the department dropdown below:\n\n"
        f"{dropdown_str}"
    )


def prompt_target_date(session: RiskCreationSession) -> str:
    session.state = RiskCreationState.AWAITING_TARGET_DATE
    return (
        f"### 🛡️ Step 9/10: Target Completion Date\n\n"
        f"**Assigned Action Owner:** `{session.action_owner_name}`\n\n"
        f"What is the target completion date for this risk action plan?\n\n"
        f"👉 *Enter a date (e.g. `31-Dec-2026`, `2026-12-31`, `+30 days`, or `+60 days`):*\n\n"
        f"[btn:📅 +30 Days|+30 days] [btn:📅 +60 Days|+60 days] [btn:📅 +90 Days|+90 days]"
    )


def prompt_status(session: RiskCreationSession) -> str:
    session.state = RiskCreationState.AWAITING_STATUS
    status_options = [
        "💾 Draft (Save in Department Workspace)::Draft",
        "🚀 Submit to Functional Head (Stage 2 Review)::Submit to Functional Head"
    ]
    dropdown_str = f"[select:📋 Select Governance Status...|{';'.join(status_options)}]"

    return (
        f"### 🛡️ Step 10/10: Governance Status\n\n"
        f"**Target Date:** `{session.target_date}`\n\n"
        f"Select the governance status for this risk entry:\n\n"
        f"{dropdown_str}\n\n"
        f"[btn:💾 Draft|Draft] [btn:🚀 Submit to Functional Head|Submit to Functional Head]"
    )
