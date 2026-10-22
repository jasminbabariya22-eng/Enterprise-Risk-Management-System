"""
Deterministic Natural Language Extraction for Approval Workflow Agent.
Extracts user goal, risk identifiers, decisions, remarks, and confirmation intents.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Optional, Tuple
from ERM_Copilot.agents.approval_workflow.state import ApprovalGoal

# Patterns for Risk ID extraction
RISK_ID_REGEX = re.compile(
    r'\b((?:RSK|HR|FIN|OPS|SEC|ENV|IT)-[A-Z0-9_-]+-\d+|[A-Z]{2,5}-\d{2,5}|RSK-\d+)\b',
    re.IGNORECASE
)
NUMERIC_RISK_REGEX = re.compile(r'\b(?:risk\s+|item\s+|#)?(\d{1,6})\b', re.IGNORECASE)

# Patterns for remarks
REMARK_PATTERN = re.compile(
    r'(?:because|due\s+to|with\s+remark\s+(?:is\s+)?|with\s+remark:?|remark\s+is:?|remark:?|reason\s+is:?|reason:?)\s*(.+)$',
    re.IGNORECASE
)

# Whole-word confirmation tokens
CONFIRM_WORDS = {
    "yes", "y", "confirm", "proceed", "agree", "ok", "okay", "sure",
    "confirm approval", "confirm rejection", "sign off", "approve it", "reject it"
}
NEGATED_CONFIRM_PATTERNS = [
    r'\bdo\s+not\s+(?:confirm|approve|proceed)\b',
    r'\bdon[\'t\s]+t\s+(?:confirm|approve|proceed)\b',
    r'\bnot\s+confirm(?:ed)?\b',
    r'\bno\b',
    r'\bcancel\b'
]
CANCEL_WORDS = {
    "no", "n", "cancel", "stop", "abort", "discard", "exit", "quit",
    "nevermind", "never mind"
}


@dataclass
class ExtractedApprovalInputs:
    """Structured parameters extracted from a conversational turn."""
    goal: Optional[ApprovalGoal] = None
    risk_id: Optional[str] = None
    action: Optional[Literal["approve", "reject"]] = None
    remark: Optional[str] = None
    is_confirmation: bool = False
    is_cancellation: bool = False


def extract_risk_id(text: str) -> Optional[str]:
    """Extract a canonical risk identifier from user text."""
    if not text:
        return None
    cleaned = text.strip()
    match = RISK_ID_REGEX.search(cleaned)
    if match:
        return match.group(1).upper()

    lower = cleaned.lower()
    num_match = NUMERIC_RISK_REGEX.search(cleaned)
    if num_match and any(w in lower for w in ["risk", "item", "approve", "reject", "status", "detail", "details", "history", "why"]):
        num_val = num_match.group(1)
        # Avoid false positives on stage numbers like "stage 2"
        if not any(f"stage {num_val}" in lower or f"level {num_val}" in lower for _ in [1]):
            return num_val
    return None


def extract_remark(text: str) -> Optional[str]:
    """Extract explanation, reason, or remark from text."""
    if not text:
        return None
    cleaned = text.strip()
    match = REMARK_PATTERN.search(cleaned)
    if match:
        extracted = match.group(1).strip()
        extracted = re.sub(r'^["\']|["\']$', '', extracted).strip()
        if len(extracted) >= 2:
            return extracted

    # Check multi-sentence replies: "Approve HR-2106. Residual risk is acceptable."
    sentences = [s.strip() for s in re.split(r'[.\n;]', cleaned) if s.strip()]
    if len(sentences) >= 2:
        first = sentences[0].lower()
        if any(w in first for w in ["approve", "reject", "signoff", "sign-off"]):
            rest = " ".join(sentences[1:]).strip()
            if len(rest) >= 4 and not any(rest.lower().startswith(w) for w in ["btn:", "show", "what", "which"]):
                return rest
    return None


def is_user_confirming(text: str) -> bool:
    """Verify if user has provided an explicit affirmative confirmation without negation."""
    if not text:
        return False
    lower = text.strip().lower()
    for neg_pat in NEGATED_CONFIRM_PATTERNS:
        if re.search(neg_pat, lower):
            return False
    if lower in CONFIRM_WORDS:
        return True
    return bool(re.search(r'\b(?:confirm|proceed|approve|approved)\b', lower))


def is_user_cancelling(text: str) -> bool:
    """Verify if user explicitly commands cancellation."""
    if not text:
        return False
    # Strip risk codes first so e.g. 'RSK-CANCEL-01' does not trigger false cancellation
    cleaned = re.sub(RISK_ID_REGEX, '', text).strip().lower()
    if cleaned in CANCEL_WORDS:
        return True
    return bool(re.search(r'\b(?:cancel|abort|stop|discard)\b', cleaned))


def extract_goal_and_inputs(text: str, current_goal: Optional[ApprovalGoal] = None) -> ExtractedApprovalInputs:
    """
    Parse a user message to extract goal and all available parameters.
    """
    if not text:
        return ExtractedApprovalInputs()

    cleaned = text.strip()
    lower = cleaned.lower()

    cancelling = is_user_cancelling(cleaned)
    confirming = is_user_confirming(cleaned)

    extracted_id = extract_risk_id(cleaned)
    extracted_remark = extract_remark(cleaned)

    # 1. Action extraction
    action: Optional[Literal["approve", "reject"]] = None
    if any(neg in lower for neg in ["don't approve", "dont approve", "do not approve", "reject", "rejection", "return for revision", "return"]):
        action = "reject"
    elif any(pos in lower for pos in ["approve", "approval", "signoff", "sign-off", "sign off"]):
        action = "approve"

    # 2. Goal detection
    goal: Optional[ApprovalGoal] = None

    # Check status questions: "why can't i approve...", "check whether risk 123 has already been approved", "has risk 123 been approved"
    if any(w in lower for w in [
        "why can't i approve", "why cant i approve", "why cannot i approve",
        "has already been approved", "has been approved", "is already approved", "is it approved",
        "check whether", "can i approve", "am i allowed to approve", "check if approved"
    ]):
        goal = ApprovalGoal.CHECK_STATUS

    # Audit trail / history questions
    elif any(w in lower for w in [
        "approval history", "audit trail", "who approved", "approval timeline",
        "history of risk", "show history", "view history"
    ]):
        goal = ApprovalGoal.SHOW_AUDIT_TRAIL

    # Pending approvals / queue questions
    elif any(w in lower for w in [
        "pending approvals", "pending approval", "approval queue", "approvals queue",
        "show my pending", "my pending approvals", "pending for my department",
        "show approvals", "view approvals", "list approvals", "show pending"
    ]) and not (action and extracted_id):
        goal = ApprovalGoal.SHOW_PENDING_APPROVALS

    # Risk details questions: "show me the details of risk 123", "details of risk 123"
    elif any(w in lower for w in ["show me the details", "risk details", "details of risk", "view risk details", "details of"]):
        goal = ApprovalGoal.SHOW_RISK_DETAILS

    # Mutation actions
    elif action == "reject":
        goal = ApprovalGoal.REJECT_RISK
    elif action == "approve":
        goal = ApprovalGoal.APPROVE_RISK

    # Fallback to current goal if continuing a multi-turn session
    if not goal and current_goal:
        goal = current_goal

    return ExtractedApprovalInputs(
        goal=goal,
        risk_id=extracted_id,
        action=action,
        remark=extracted_remark,
        is_confirmation=confirming,
        is_cancellation=cancelling,
    )
