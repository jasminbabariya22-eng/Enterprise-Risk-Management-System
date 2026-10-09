"""
Harness Guardrail Integration Layer.
Governs input validation, prompt injection resistance, output sanitization,
and cache isolation across all ERM roles.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from ERM_Copilot.ai_harness.exceptions import GuardrailViolationError
from ERM_Copilot.guardrails.manager import GuardrailManager


class HarnessGuardrails:
    """
    Harness-level security and safety guardrails.
    Extends and complements the core GuardrailManager.
    """

    INJECTION_PATTERNS = [
        re.compile(r'(?i)\bignore\s+(all\s+)?(previous|prior|system)\s+(instructions|prompts|rules)\b'),
        re.compile(r'(?i)\byou\s+are\s+now\s+(acting\s+as\s+)?(the\s+|a\s+)?(super\s+admin|root|system\s+override|functional\s+head|risk\s+manager|risk\s+head|admin)\b'),
        re.compile(r'(?i)\bbypass\s+(approval|governance|authorization|sequence|workflow)\b'),
        re.compile(r'(?i)\b(elevate\s+privilege|grant\s+admin\s+rights|force\s+approve\s+without)\b'),
        re.compile(r'(?i)\b(drop\s+table|delete\s+from\s+users|update\s+tbl_user|select\s+\*\s+from\s+passwords)\b'),
    ]


    SECRET_OUTPUT_PATTERNS = [
        (re.compile(r'(?i)bearer\s+[A-Za-z0-9_\-\.]{15,}'), '[REDACTED_BEARER_TOKEN]'),
        (re.compile(r'(?i)("?password"?\s*[:=]\s*"?)[^",\s]{4,}("?)'), r'\1[REDACTED_PASSWORD]\2'),
        (re.compile(r'(?i)("?api_key"?\s*[:=]\s*"?)[A-Za-z0-9_\-]{8,}("?)'), r'\1[REDACTED_API_KEY]\2'),
        (re.compile(r'(?i)("?secret"?\s*[:=]\s*"?)[A-Za-z0-9_\-]{8,}("?)'), r'\1[REDACTED_SECRET]\2'),
    ]

    @classmethod
    def validate_input(cls, message: str, user_role: str) -> str:
        """
        Validate incoming user message against prompt injection and malicious exploit payloads.
        Returns the sanitized text or raises GuardrailViolationError.
        """
        if not message or not str(message).strip():
            return ""

        raw_text = str(message).strip()

        # Check injection patterns
        for pattern in cls.INJECTION_PATTERNS:
            if pattern.search(raw_text):
                raise GuardrailViolationError(
                    message="Your request contains prohibited system-override or privilege-elevation instructions.",
                    reason="PROMPT_INJECTION_DETECTED",
                    details={"pattern_matched": pattern.pattern}
                )

        return raw_text

    @classmethod
    def sanitize_output(cls, output_text: str) -> str:
        """
        Sanitize agent response output, stripping any accidentally leaked tokens, passwords, or secrets.
        """
        if not output_text:
            return ""

        sanitized = output_text
        for pattern, replacement in cls.SECRET_OUTPUT_PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)

        return sanitized

    @classmethod
    def generate_isolated_cache_key(cls, user_id: str, dept_id: Optional[int], user_role: str, query: str) -> str:
        """
        Generate a strictly isolated cache key that prevents cross-user and cross-department data leakage.
        """
        dept_str = str(dept_id) if dept_id is not None else "enterprise"
        cleaned_query = re.sub(r'\s+', ' ', query.strip().lower())
        return f"erm_cache:u_{user_id}:d_{dept_str}:r_{user_role}:{cleaned_query}"

    @classmethod
    def is_cacheable_operation(cls, tool_name: Optional[str], is_state_changing: bool) -> bool:
        """
        Only safe read-only queries may be cached.
        State-changing operations and approvals must NEVER be cached.
        """
        if is_state_changing:
            return False
        if tool_name and tool_name in ["approve_or_reject_risk", "save_risk", "create_risk_full", "add_risk_treatment", "update_treatment_progress"]:
            return False
        return True


harness_guardrails = HarnessGuardrails()
