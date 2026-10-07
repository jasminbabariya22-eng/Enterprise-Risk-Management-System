"""
LangGraph Nodes for the Conversational Approval / Rejection Workflow.
"""
import re
import logging
from typing import Dict, Any, Optional, Literal, Tuple

from ERM_Copilot.agents.approval.state import ApprovalState
from ERM_Copilot.agents.approval.tools import approve_or_reject_risk
from ERM_Copilot.agents.approval.prompts import (
    format_missing_risk_id_prompt,
    format_missing_action_prompt,
    format_missing_remark_prompt,
    format_confirmation_prompt,
    format_success_response,
    format_error_response,
    format_cancellation_response,
)

logger = logging.getLogger("ERM_Copilot.agents.approval.nodes")


# Regex patterns for fast deterministic extraction & fallback
RISK_ID_PATTERN = re.compile(r'\b(RSK-[A-Z0-9_-]+-\d+|[A-Z]{2,5}-\d{2,5}|RSK-\d+)\b', re.IGNORECASE)
REMARK_SPLIT_PATTERN = re.compile(r'(?:because|due\s+to|with\s+remark\s+(?:is\s+)?|with\s+remark:?|remark\s+is:?|remark:?|reason\s+is:?|reason:?)\s*(.+)$', re.IGNORECASE)

CONFIRM_WORDS = {"yes", "y", "confirm", "proceed", "agree", "ok", "okay", "sure", "confirm approval", "confirm rejection", "sign off", "approve it", "reject it"}
CANCEL_WORDS = {"no", "n", "cancel", "stop", "abort", "don't", "dont", "do not", "cancel this", "exit", "quit", "nevermind", "never mind"}


def extract_parameters_from_text(text: str) -> Tuple[Optional[str], Optional[Literal["approve", "reject"]], Optional[str]]:
    """
    Extract risk_id, action, and remark from a user prompt using robust pattern analysis.
    """
    cleaned = text.strip()
    lower = cleaned.lower()

    # 1. Action Extraction
    action: Optional[Literal["approve", "reject"]] = None
    if any(neg in lower for neg in ["don't approve", "dont approve", "do not approve", "reject", "rejection", "return for revision", "return"]):
        action = "reject"
    elif any(pos in lower for pos in ["approve", "approval", "signoff", "sign-off", "sign off", "signed off"]):
        action = "approve"

    # 2. Risk ID Extraction
    risk_id: Optional[str] = None
    risk_match = RISK_ID_PATTERN.search(cleaned)
    if risk_match:
        risk_id = risk_match.group(1).upper()
    else:
        # Check for numeric risk IDs like 'risk 49'
        num_match = re.search(r'\b(?:risk\s+|#)?(\d+)\b', cleaned, re.IGNORECASE)
        if num_match and any(w in lower for w in ["risk", "approve", "reject", "item"]):
            # Only treat as risk_id if contextualized
            if not any(num_match.group(1) == w for w in ["1", "2", "3", "4", "5"] if f"stage {w}" in lower or f"level {w}" in lower):
                risk_id = num_match.group(1)

    # 3. Remark Extraction
    remark: Optional[str] = None
    remark_match = REMARK_SPLIT_PATTERN.search(cleaned)
    if remark_match:
        extracted = remark_match.group(1).strip()
        # Clean trailing punctuation / quotes
        extracted = re.sub(r'^["\']|["\']$', '', extracted).strip()
        if len(extracted) >= 2:
            remark = extracted
    else:
        # Check for multi-sentence patterns: "Approve HR-2106. The residual risk is acceptable."
        sentences = [s.strip() for s in re.split(r'[.\n;]', cleaned) if s.strip()]
        if len(sentences) >= 2:
            first_sent = sentences[0].lower()
            if any(w in first_sent for w in ["approve", "reject", "signoff", "sign-off"]):
                second_part = " ".join(sentences[1:]).strip()
                if len(second_part) >= 4 and not any(second_part.lower().startswith(w) for w in ["btn:", "show", "what", "which"]):
                    remark = second_part

    return risk_id, action, remark


# =====================================================================
# NODE IMPLEMENTATIONS
# =====================================================================

def extract_approval_request(state: ApprovalState) -> ApprovalState:
    """
    First node: parses the user's initial or ongoing request.
    Extracts risk_id, action, and remark if present.
    """
    msg = state.get("last_user_message") or ""
    
    # Check for cancellation early
    lower_msg = msg.lower().strip()
    if lower_msg in CANCEL_WORDS or any(lower_msg.startswith(w + " ") or lower_msg.endswith(" " + w) for w in ["cancel", "stop", "abort"]):
        state["cancelled"] = True
        state["is_completed"] = True
        state["response_message"] = format_cancellation_response(state.get("risk_id"))
        state["step_code"] = "APPROVAL_CANCELLED"
        return state

    extracted_id, extracted_action, extracted_remark = extract_parameters_from_text(msg)

    # Merge with existing state (do not overwrite with None if already present)
    if extracted_id:
        state["risk_id"] = extracted_id
    if extracted_action:
        state["action"] = extracted_action
    if extracted_remark:
        state["remark"] = extracted_remark

    return state


def validate_required_fields(state: ApprovalState) -> ApprovalState:
    """
    Validates what information is currently available and sets state flags.
    """
    if state.get("cancelled"):
        return state

    risk_id = state.get("risk_id")
    action = state.get("action")
    remark = state.get("remark")

    # Reset waiting flags
    state["awaiting_risk_id"] = False
    state["awaiting_action"] = False
    state["awaiting_remark"] = False
    state["awaiting_confirmation"] = False

    if not risk_id:
        state["awaiting_risk_id"] = True
        state["response_message"] = format_missing_risk_id_prompt(action)
        state["step_code"] = "AWAITING_RISK_ID"
        return state

    if not action:
        state["awaiting_action"] = True
        state["response_message"] = format_missing_action_prompt(risk_id)
        state["step_code"] = "AWAITING_ACTION"
        return state

    if not remark or not str(remark).strip():
        state["awaiting_remark"] = True
        state["response_message"] = format_missing_remark_prompt(risk_id, action)
        state["step_code"] = "AWAITING_REMARK"
        return state

    # All fields present -> proceed to confirmation
    state["awaiting_confirmation"] = True
    state["response_message"] = format_confirmation_prompt(risk_id, action, remark)
    state["step_code"] = "AWAITING_CONFIRMATION"
    return state


def capture_continuation_input(state: ApprovalState) -> ApprovalState:
    """
    Captures input during an active multi-turn waiting state (missing risk ID, action, remark, or confirmation).
    """
    msg = (state.get("last_user_message") or "").strip()
    lower_msg = msg.lower()

    # 1. Cancellation check
    if lower_msg in CANCEL_WORDS or any(lower_msg == w for w in ["cancel", "no", "stop", "abort", "don't approve", "dont approve", "cancel this"]):
        state["cancelled"] = True
        state["is_completed"] = True
        state["response_message"] = format_cancellation_response(state.get("risk_id"))
        state["step_code"] = "APPROVAL_CANCELLED"
        return state

    # 2. If awaiting confirmation
    if state.get("awaiting_confirmation"):
        if lower_msg in CONFIRM_WORDS or any(lower_msg.startswith(w) for w in ["confirm", "proceed", "yes", "approve", "reject"]):
            state["confirmed"] = True
            state["awaiting_confirmation"] = False
            return state
        else:
            # Ambiguous input during confirmation
            state["response_message"] = (
                f"⚠️ Please confirm your decision or cancel.\n\n" +
                format_confirmation_prompt(state.get("risk_id", "Risk"), state.get("action", "approve"), state.get("remark", ""))
            )
            state["step_code"] = "AWAITING_CONFIRMATION"
            return state

    # 3. If awaiting remark
    if state.get("awaiting_remark"):
        # The entire message (or extracted remark) becomes the remark
        extracted_id, extracted_action, extracted_remark = extract_parameters_from_text(msg)
        chosen_remark = extracted_remark or msg
        # Clean button tokens if user clicked a suggestion button
        chosen_remark = re.sub(r'\[btn.*?\]', '', chosen_remark).strip()
        if len(chosen_remark) >= 2:
            state["remark"] = chosen_remark
            state["awaiting_remark"] = False
            # Now proceed to confirmation
            return validate_required_fields(state)
        else:
            state["response_message"] = format_missing_remark_prompt(state.get("risk_id", "Risk"), state.get("action", "approve"))
            return state

    # 4. If awaiting action
    if state.get("awaiting_action"):
        extracted_id, extracted_action, extracted_remark = extract_parameters_from_text(msg)
        if extracted_action:
            state["action"] = extracted_action
            state["awaiting_action"] = False
            if extracted_remark:
                state["remark"] = extracted_remark
            return validate_required_fields(state)
        else:
            state["response_message"] = format_missing_action_prompt(state.get("risk_id", "Risk"))
            return state

    # 5. If awaiting risk_id
    if state.get("awaiting_risk_id"):
        extracted_id, extracted_action, extracted_remark = extract_parameters_from_text(msg)
        if extracted_id:
            state["risk_id"] = extracted_id
            state["awaiting_risk_id"] = False
            if extracted_action:
                state["action"] = extracted_action
            if extracted_remark:
                state["remark"] = extracted_remark
            return validate_required_fields(state)
        else:
            state["response_message"] = format_missing_risk_id_prompt(state.get("action"))
            return state

    return validate_required_fields(state)


def execute_approval_tool(state: ApprovalState) -> ApprovalState:
    """
    Final execution node: Calls the single generic approve_or_reject_risk tool
    with authenticated approver_id from context.
    """
    if not state.get("confirmed"):
        state["response_message"] = "⚠️ Operation not confirmed. No changes were made."
        state["step_code"] = "UNCONFIRMED_ABORT"
        state["is_completed"] = True
        return state

    risk_id = state.get("risk_id")
    action = state.get("action")
    remark = state.get("remark")
    user_id_raw = state.get("user_id")

    # Strict approver ID validation
    try:
        approver_id = int(user_id_raw) if user_id_raw is not None else None
    except (ValueError, TypeError):
        approver_id = None

    result = approve_or_reject_risk(
        risk_id=risk_id,
        action=action,
        remark=remark,
        approver_id=approver_id
    )

    state["api_result"] = result
    state["is_completed"] = True

    if result.get("success"):
        state["response_message"] = format_success_response(result)
        state["step_code"] = "APPROVAL_EXECUTED" if action == "approve" else "REJECTION_EXECUTED"
    else:
        err_msg = result.get("message", "Approval action failed in backend.")
        state["error"] = err_msg
        state["response_message"] = format_error_response(err_msg, risk_id)
        state["step_code"] = "APPROVAL_FAILED"

    return state
