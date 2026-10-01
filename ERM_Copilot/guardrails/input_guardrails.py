"""
Input Guardrails for ERM Copilot.
Protects against prompt injection, PII/secret leakage, domain deviations, and role privilege escalations.
"""
import re
from typing import Tuple, Dict, Any, List, Optional
import logging

logger = logging.getLogger("ERM_Copilot.guardrails.input")

# Regular expressions for sensitive data masking
PII_PATTERNS = {
    "api_key": r'(?:gsk|AIza|rsk|sk|key|token|bearer|password|pwd)[a-zA-Z0-9_\-:=]{16,}',
    "credit_card": r'\b(?:\d{4}[-\s]?){3}\d{4}\b',
    "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b',
    "phone_in": r'\b(?:\+?91|0)?[6-9]\d{9}\b',
    "ipv4": r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
}

# Prompt injection & jailbreak signatures
JAILBREAK_PATTERNS = [
    r'ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|rules)',
    r'disregard\s+(all\s+)?(previous|prior)\s+(rules|guidelines)',
    r'forget\s+(all\s+)?(safety|rules|instructions|prompts)',
    r'you\s+are\s+now\s+(in\s+)?(unconstrained|dan|jailbroken|godmode|evil|unfiltered)',
    r'system\s+override',
    r'pretend\s+you\s+have\s+no\s+(restrictions|guardrails|safety)',
    r'bypass\s+all\s+(security|safety|governance)',
    r'output\s+(the\s+)?(raw\s+)?system\s+prompt',
    r'reveal\s+(your\s+)?(system\s+prompt|instructions)',
    r'drop\s+table\s+',
    r'delete\s+from\s+ers\.',
    r'truncate\s+table\s+',
    r'sudo\s+rm\s+-rf',
    r'<\s*script\b[^>]*>',
    r'javascript:'
]

# Industrial ERM domain keywords
ERM_DOMAIN_KEYWORDS = [
    "risk", "hazard", "threat", "mitigation", "likelihood", "impact", "score",
    "matrix", "treatment", "approval", "stage", "audit", "compliance", "action",
    "owner", "department", "plant", "refinery", "pipeline", "corrosion", "leakage",
    "pressure", "safety", "governance", "cro", "register", "heatmap", "incident",
    "control", "residual", "inherent", "vulnerability", "followup", "rejection",
    "remark", "status", "ro", "fh", "rm", "auditor", "admin", "hello", "hi", "hey",
    "help", "summary", "dashboard", "report", "show", "view", "list"
]


class InputGuardrail:
    """Evaluates and sanitizes incoming user prompts before agent execution."""

    @classmethod
    def sanitize_sensitive_data(cls, text: str) -> Tuple[str, bool]:
        """Redacts sensitive credentials, PII, and API keys."""
        sanitized = text
        redacted = False

        for pii_type, pattern in PII_PATTERNS.items():
            matches = list(re.finditer(pattern, sanitized, flags=re.IGNORECASE))
            if matches:
                redacted = True
                for match in reversed(matches):
                    val = match.group(0)
                    # Don't redact typical domain numbers or localhost
                    if pii_type == "ipv4" and (val.startswith("127.0.0.1") or val.startswith("0.0.0.0")):
                        continue
                    sanitized = sanitized[:match.start()] + f"[REDACTED_{pii_type.upper()}]" + sanitized[match.end():]

        return sanitized, redacted

    @classmethod
    def detect_prompt_injection(cls, text: str) -> Tuple[bool, Optional[str]]:
        """Detects adversarial jailbreak and prompt injection attempts."""
        lower_text = text.lower()
        for pattern in JAILBREAK_PATTERNS:
            if re.search(pattern, lower_text, flags=re.IGNORECASE):
                logger.warning(f"Guardrail Alert: Prompt injection pattern detected: '{pattern}'")
                return True, f"Adversarial instruction or security override detected: `{pattern}`"
        return False, None

    @classmethod
    def validate_domain_scope(cls, text: str) -> Tuple[bool, Optional[str]]:
        """Checks if the query has reasonable relevance to ERM / Plant Risk Operations."""
        cleaned = re.sub(r'[^\w\s]', ' ', text.lower()).strip()
        tokens = set(cleaned.split())

        # If very short greeting/command, allow
        if len(tokens) <= 3 and any(t in tokens for t in ["hi", "hello", "hey", "help", "status", "cancel"]):
            return True, None

        # Check for ERM keyword overlap
        has_erm_context = any(kw in cleaned for kw in ERM_DOMAIN_KEYWORDS)
        
        # Check for obvious out-of-scope requests (recipes, creative writing, non-ERM math/code)
        out_of_scope_cues = ["recipe", "poem", "song", "movie review", "write code for flappy bird", "joke"]
        if any(cue in cleaned for cue in out_of_scope_cues):
            return False, "Query is outside the Enterprise Risk Management (ERM) operational domain."

        if not has_erm_context and len(tokens) > 5:
            # Gentle out-of-scope steer
            return False, "Please focus your request on Enterprise Risk Management, plant hazard evaluations, or governance workflows."

        return True, None

    @classmethod
    def validate_role_authorization(cls, action_type: str, user_role_id: Optional[int]) -> Tuple[bool, Optional[str]]:
        """Prevents role escalation attempts during critical workflows."""
        if not user_role_id:
            return True, None  # Default permissive if role not attached to chat context

        # Stage 4 Executive Approvals require CRO (Role 4) or Admin (Role 7)
        if "approve_stage_4" in action_type and user_role_id not in [4, 7]:
            return False, f"Unauthorized: Stage 4 final executive approval requires Risk Head / CRO (Role 4). Current user is Role {user_role_id}."

        # Stage 2 Technical Reviews require Functional Head (Role 2) or Admin (Role 7)
        if "approve_stage_2" in action_type and user_role_id not in [2, 7]:
            return False, f"Unauthorized: Stage 2 reviews require Functional Head (Role 2). Current user is Role {user_role_id}."

        return True, None
