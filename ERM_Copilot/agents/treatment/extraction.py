"""
Enterprise Risk Management (ERM) - Natural Language Entity & Intent Extraction for Treatment Agent.
Extracts goals, risk codes, treatment IDs, action plans, owners, target dates, progress %, and remarks.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from ERM_Copilot.agents.treatment.state import (
    TreatmentGoal,
    extract_risk_identifier,
    extract_treatment_id,
    parse_date_string,
    parse_progress_percentage,
)

# Whole-word confirmation tokens
CONFIRM_WORDS = {
    "yes", "y", "confirm", "proceed", "agree", "ok", "okay", "sure",
    "confirm and save", "confirm save", "confirm update", "confirm reassignment",
    "save it", "update it", "proceed with save"
}

NEGATED_CONFIRM_PATTERNS = [
    r'\bdo\s+not\s+(?:confirm|save|update|proceed)\b',
    r'\bdon[\'t\s]+t\s+(?:confirm|save|update|proceed)\b',
    r'\bnot\s+confirm(?:ed)?\b',
    r'\bno\b',
    r'\bcancel\b'
]

CANCEL_WORDS = {
    "no", "n", "cancel", "stop", "abort", "discard", "exit", "quit",
    "nevermind", "never mind", "cancel action", "cancel treatment"
}


@dataclass
class ExtractedTreatmentInputs:
    """Structured extraction output from a conversational turn."""
    goal: Optional[TreatmentGoal] = None
    target_risk_id: Optional[str] = None
    treatment_id: Optional[int] = None
    action_plan: Optional[str] = None
    action_owner_id: Optional[int] = None
    action_owner_name: Optional[str] = None
    new_action_owner_id: Optional[int] = None
    new_action_owner_name: Optional[str] = None
    target_date: Optional[str] = None
    progress: Optional[int] = None
    remarks: Optional[str] = None
    is_confirmation: bool = False
    is_cancellation: bool = False


def is_user_confirming(text: str) -> bool:
    """Check if user provided an affirmative confirmation."""
    if not text:
        return False
    lower = text.strip().lower()
    for neg in NEGATED_CONFIRM_PATTERNS:
        if re.search(neg, lower):
            return False
    if lower in CONFIRM_WORDS:
        return True
    return bool(re.search(r'\b(?:confirm|confirm and save|proceed with save|yes please)\b', lower))


def is_user_cancelling(text: str) -> bool:
    """Check if user commanded cancellation."""
    if not text:
        return False
    # Strip risk or treatment codes first to prevent false matches on names
    sanitized = re.sub(r'\b(?:RSK-[A-Z0-9_-]+-\d+|TRT-\d+|#\d+)\b', '', text, flags=re.IGNORECASE).strip().lower()
    if sanitized in CANCEL_WORDS:
        return True
    return bool(re.search(r'\b(?:cancel|abort|stop|discard)\b', sanitized))


# Alias for backward compatibility and agent imports
is_cancellation = is_user_cancelling


def is_add_treatment_trigger(text: str) -> bool:
    """Detect intent to add a new mitigation action plan to a risk."""
    lower = text.strip().lower()
    if any(w in lower for w in ["show", "list", "view", "audit", "search"]):
        return False
    return any(w in lower for w in [
        "add action", "new action", "add treatment", "new treatment", "create action",
        "attach action", "add plan", "create treatment", "action plan to risk",
        "action plan for risk", "add action plan", "attach plan", "add mitigation to risk",
        "add mitigation plan", "mitigate risk", "create an action plan"
    ])


def is_update_progress_trigger(text: str) -> bool:
    """Detect intent to update progress % on an existing treatment."""
    lower = text.strip().lower()
    if is_add_treatment_trigger(text):
        return False
    return (
        any(w in lower for w in [
            "update progress", "change progress", "set progress", "progress to",
            "progress of", "mark progress", "update action progress", "record progress"
        ])
        or (
            any(w in lower for w in ["progress", "completed", "complete"])
            and any(w in lower for w in ["treatment", "action plan", "action", "trt"])
            and any(w in lower for w in ["to", "set", "%", "update"])
        )
    )


def is_reassign_owner_trigger(text: str) -> bool:
    """Detect intent to reassign action owner on an existing treatment."""
    lower = text.strip().lower()
    return any(w in lower for w in [
        "reassign action", "change action owner", "reassign owner", "reassign treatment",
        "assign action owner to", "transfer action", "transfer ownership", "change owner to"
    ])


def is_list_treatments_trigger(text: str) -> bool:
    """Detect query/listing intent for treatments."""
    lower = text.strip().lower()
    return any(w in lower for w in [
        "show treatment", "list treatment", "show action plan", "list action plan",
        "view treatment", "view action plan", "what are the treatments", "what are the action plans",
        "list treatments", "show action plans", "show treatments for", "get treatments"
    ])


def is_show_details_trigger(text: str) -> bool:
    """Detect intent to view single treatment details."""
    lower = text.strip().lower()
    return any(w in lower for w in [
        "treatment details", "action plan details", "show treatment #", "view treatment #"
    ]) and extract_treatment_id(text) is not None


def extract_treatment_inputs(text: str, current_goal: Optional[TreatmentGoal] = None) -> ExtractedTreatmentInputs:
    """
    Parse a user message and extract all available parameters.
    """
    if not text:
        return ExtractedTreatmentInputs()

    cleaned = text.strip()
    lower = cleaned.lower()

    confirming = is_user_confirming(cleaned)
    cancelling = is_user_cancelling(cleaned)

    # 1. Goal Detection
    goal: Optional[TreatmentGoal] = None
    if is_add_treatment_trigger(cleaned):
        goal = TreatmentGoal.ADD_TREATMENT
    elif is_update_progress_trigger(cleaned):
        goal = TreatmentGoal.UPDATE_PROGRESS
    elif is_reassign_owner_trigger(cleaned):
        goal = TreatmentGoal.REASSIGN_OWNER
    elif is_show_details_trigger(cleaned):
        goal = TreatmentGoal.SHOW_TREATMENT_DETAILS
    elif is_list_treatments_trigger(cleaned):
        goal = TreatmentGoal.LIST_TREATMENTS
    elif current_goal:
        goal = current_goal

    # 2. Extract Identifiers
    extracted_risk_id = extract_risk_identifier(cleaned)
    extracted_treatment_id = extract_treatment_id(cleaned)

    # 3. Extract Target Date & Progress
    extracted_date = parse_date_string(cleaned)
    extracted_progress = parse_progress_percentage(cleaned)

    # 4. Extract Action Owner (Assignee)
    action_owner_name: Optional[str] = None
    action_owner_id: Optional[int] = None
    new_action_owner_name: Optional[str] = None
    new_action_owner_id: Optional[int] = None

    # Owner assignment pattern: "assign it to John Doe", "Assign Action Owner Jane", "assign to 8"
    ao_match = re.search(
        r'(?:reassign(?:ed)?\s+.*?\bto|assign(?:ed)?\s+(?:it\s+)?to|assign(?:ed)?\s+(?:action\s+owner\s+|owner\s+)?|action\s+owner\s*(?:is|to|:)?|owner\s*(?:is|to|:)?|assignee\s*(?:is|to|:)?|transfer\s+(?:.*?\b)?to)\s+([A-Za-z0-9_\-\.\s]+?)(?:,|$|\.|\b(?:target|date|due|with|progress|and)\b)',
        cleaned,
        re.IGNORECASE,
    )
    if ao_match:
        raw_owner = ao_match.group(1).strip()
        if raw_owner.isdigit():
            if goal == TreatmentGoal.REASSIGN_OWNER:
                new_action_owner_id = int(raw_owner)
            else:
                action_owner_id = int(raw_owner)
        else:
            cleaned_owner = re.sub(r'^(?:an?\s+|the\s+|action\s+owner\s+)', '', raw_owner, flags=re.IGNORECASE).strip()
            if len(cleaned_owner) >= 2 and cleaned_owner.lower() not in ["eligible", "action owner", "eligible action owner", "someone"]:
                if goal == TreatmentGoal.REASSIGN_OWNER:
                    new_action_owner_name = cleaned_owner
                else:
                    action_owner_name = cleaned_owner

    # 5. Extract Action Plan Description
    action_plan_text: Optional[str] = None
    # Pattern: "Add an action plan for RSK-GAS-049: <action_plan>"
    colon_split = re.split(r':\s*', cleaned, maxsplit=1)
    if len(colon_split) > 1 and is_add_treatment_trigger(colon_split[0]):
        candidate_plan = colon_split[1].strip()
        # Strip trailing parameter clauses like "target in 60 days, assign to..."
        candidate_plan = re.split(
            r'(?:,\s*|\.\s*|\s+)(?:\b(?:assign|target|progress|due|owner|start at)\b)',
            candidate_plan,
            flags=re.IGNORECASE,
        )[0].strip()
        if len(candidate_plan) >= 5:
            action_plan_text = candidate_plan

    # Secondary pattern: "action plan is <text>"
    if not action_plan_text:
        plan_match = re.search(
            r'(?:action\s*plan\s*(?:is|:=|:)\s*|mitigation\s*(?:is|:=|:)\s*)(.+?)(?:,|$|\.|\b(?:assign|target|progress|due|owner)\b)',
            cleaned,
            re.IGNORECASE,
        )
        if plan_match:
            candidate = plan_match.group(1).strip()
            if len(candidate) >= 5 and not re.match(r'^(?:to\s+risk|for\s+risk|risk)\b', candidate, re.IGNORECASE):
                action_plan_text = candidate


    # 6. Extract Remarks / Reasons
    extracted_remark: Optional[str] = None
    remark_match = re.search(
        r'(?:with\s+remark|remark\s+is|reason\s+is|note\s+that|record\s+that)\s*:?\s*(.+)$',
        cleaned,
        re.IGNORECASE,
    )
    if remark_match:
        extracted_remark = remark_match.group(1).strip()

    return ExtractedTreatmentInputs(
        goal=goal,
        target_risk_id=extracted_risk_id,
        treatment_id=extracted_treatment_id,
        action_plan=action_plan_text,
        action_owner_id=action_owner_id,
        action_owner_name=action_owner_name,
        new_action_owner_id=new_action_owner_id,
        new_action_owner_name=new_action_owner_name,
        target_date=extracted_date,
        progress=extracted_progress,
        remarks=extracted_remark,
        is_confirmation=confirming,
        is_cancellation=cancelling,
    )
