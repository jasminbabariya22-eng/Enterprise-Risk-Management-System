"""
Enterprise Risk Management (ERM) - Controlled Session Update and Provenance Merging for Treatment Agent.
Merges extracted inputs into the session while tracking provenance and user corrections.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from ERM_Copilot.agents.treatment.extraction import ExtractedTreatmentInputs
from ERM_Copilot.agents.treatment.state import (
    TreatmentGoal,
    TreatmentSession,
    TreatmentWorkflowState,
    parse_date_string,
    parse_progress_percentage,
)


def merge_treatment_inputs(
    session: TreatmentSession,
    extracted: ExtractedTreatmentInputs,
    raw_message: str = "",
) -> TreatmentSession:
    """
    Merge newly extracted parameters into session state with provenance tracking.
    """
    # 1. Goal update
    if extracted.goal and extracted.goal != TreatmentGoal.UNKNOWN:
        if session.goal != extracted.goal:
            session.goal = extracted.goal
            session.provenance["goal"] = "user_extracted"

    # 2. Target Risk ID
    if extracted.target_risk_id:
        if session.target_risk_id != extracted.target_risk_id:
            tag = "user_corrected" if session.target_risk_id else "user_extracted"
            session.target_risk_id = extracted.target_risk_id
            session.provenance["target_risk_id"] = tag
            # Invalidate previously cached risk details on ID change
            session.target_risk_register_id = None
            session.target_risk_name = None
            session.risk_data = None

    # 3. Treatment ID
    if extracted.treatment_id is not None:
        if session.treatment_id != extracted.treatment_id:
            tag = "user_corrected" if session.treatment_id else "user_extracted"
            session.treatment_id = extracted.treatment_id
            session.provenance["treatment_id"] = tag

    # 4. Action Plan Text
    if extracted.action_plan:
        if session.action_plan != extracted.action_plan:
            tag = "user_corrected" if session.action_plan else "user_extracted"
            session.action_plan = extracted.action_plan
            session.provenance["action_plan"] = tag

    # 5. Action Owner (Add Treatment mode)
    if extracted.action_owner_id is not None:
        if session.action_owner_id != extracted.action_owner_id:
            tag = "user_corrected" if session.action_owner_id else "user_extracted"
            session.action_owner_id = extracted.action_owner_id
            session.provenance["action_owner_id"] = tag

    if extracted.action_owner_name:
        if session.action_owner_name != extracted.action_owner_name:
            tag = "user_corrected" if session.action_owner_name else "user_extracted"
            session.action_owner_name = extracted.action_owner_name
            session.provenance["action_owner_name"] = tag

    # 6. New Action Owner (Reassign mode)
    if extracted.new_action_owner_id is not None:
        tag = "user_corrected" if (session.new_action_owner_id is not None and session.new_action_owner_id != extracted.new_action_owner_id) else "user_extracted"
        session.new_action_owner_id = extracted.new_action_owner_id
        session.provenance["new_action_owner_id"] = tag

    if extracted.new_action_owner_name:
        tag = "user_corrected" if (session.new_action_owner_name and session.new_action_owner_name != extracted.new_action_owner_name) else "user_extracted"
        session.new_action_owner_name = extracted.new_action_owner_name
        session.provenance["new_action_owner_name"] = tag

    # 7. Target Date
    if extracted.target_date:
        tag = "user_corrected" if (session.target_date and session.target_date != extracted.target_date) else "user_extracted"
        session.target_date = extracted.target_date
        session.provenance["target_date"] = tag

    # 8. Progress Percentage
    if extracted.progress is not None:
        tag = "user_corrected" if ("progress" in session.provenance and session.progress != extracted.progress) else "user_extracted"
        session.progress = extracted.progress
        session.provenance["progress"] = tag

    # 9. Remarks
    if extracted.remarks:
        session.remarks = extracted.remarks
        session.provenance["remarks"] = "user_extracted"

    # 10. Multi-turn single-input fallbacks based on current missing state
    clean_msg = raw_message.strip()
    clean_msg_lower = clean_msg.lower()

    from ERM_Copilot.agents.treatment.extraction import is_add_treatment_trigger

    if (
        session.goal == TreatmentGoal.ADD_TREATMENT
        and not session.action_plan
        and not extracted.is_confirmation
        and not extracted.is_cancellation
        and not is_add_treatment_trigger(clean_msg)
    ):
        # Exclude small-talk, greeting, or button prefix
        if len(clean_msg) >= 6 and not any(w in clean_msg_lower for w in ["cancel", "no", "yes", "confirm", "help", "hi", "select"]):
            # If user selected an Option button e.g. "Option 1"
            opt_match = re.search(r'\boption\s*([123])\b', clean_msg_lower)
            if opt_match and session.action_plan_suggestions:
                idx = int(opt_match.group(1)) - 1
                if 0 <= idx < len(session.action_plan_suggestions):
                    session.action_plan = session.action_plan_suggestions[idx]
                    session.provenance["action_plan"] = "user_selected_suggestion"
            else:
                session.action_plan = clean_msg
                session.provenance["action_plan"] = "user_extracted"

    # If waiting for date and user typed a relative offset or date
    if not session.target_date and session.goal == TreatmentGoal.ADD_TREATMENT:
        d = parse_date_string(clean_msg)
        if d:
            session.target_date = d
            session.provenance["target_date"] = "user_extracted"

    # If waiting for progress %
    if "progress" not in session.provenance and clean_msg:
        pct = parse_progress_percentage(clean_msg)
        if pct is not None:
            session.progress = pct
            session.provenance["progress"] = "user_extracted"

    return session


def apply_documented_treatment_defaults(session: TreatmentSession) -> TreatmentSession:
    """
    Apply documented defaults for optional fields if not explicitly provided by the user.
    """
    if session.goal == TreatmentGoal.ADD_TREATMENT:
        # Default target date: +30 days from now
        if not session.target_date:
            session.target_date = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")
            session.provenance["target_date"] = "default"

        # Default initial progress: 0%
        if "progress" not in session.provenance:
            session.progress = 0
            session.provenance["progress"] = "default"

        # Default action status: 1 (Draft) or 7 (In Progress if progress > 0)
        session.action_status_id = 7 if session.progress > 0 else 1

    return session
