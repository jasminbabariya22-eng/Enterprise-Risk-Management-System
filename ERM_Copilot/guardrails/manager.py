"""
Unified Guardrail Manager for ERM Copilot.
Coordinates pre-execution input filters and post-execution output sanitization.
"""
from typing import Tuple, Dict, Any, Optional
import logging

from ERM_Copilot.guardrails.input_guardrails import InputGuardrail
from ERM_Copilot.guardrails.output_guardrails import OutputGuardrail
from ERM_Copilot.models.contracts import AgentRequest, AgentResponse, RequestContext

logger = logging.getLogger("ERM_Copilot.guardrails.manager")


class GuardrailResult:
    def __init__(self, passed: bool, sanitized_text: str, reason: Optional[str] = None, blocked: bool = False):
        self.passed = passed
        self.sanitized_text = sanitized_text
        self.reason = reason
        self.blocked = blocked


class GuardrailManager:
    """Enterprise safety and compliance gateway manager."""

    @classmethod
    def process_input(cls, request: AgentRequest) -> GuardrailResult:
        """Runs the complete suite of input checks before invoking agent reasoning."""
        raw_message = request.message or ""

        # 1. Prompt Injection & Jailbreak Check
        is_injection, injection_reason = InputGuardrail.detect_prompt_injection(raw_message)
        if is_injection:
            return GuardrailResult(
                passed=False,
                sanitized_text="",
                reason=f"🛡️ **Security Guardrail Triggered**: {injection_reason}. Your request was safely blocked.",
                blocked=True
            )

        # 2. PII / Secret Redaction
        sanitized_msg, was_redacted = InputGuardrail.sanitize_sensitive_data(raw_message)
        if was_redacted:
            logger.info("Guardrail info: Sensitive credentials were masked before LLM processing.")

        # 3. Domain Scope Relevance Check
        is_in_scope, scope_reason = InputGuardrail.validate_domain_scope(sanitized_msg)
        if not is_in_scope:
            return GuardrailResult(
                passed=False,
                sanitized_text="",
                reason=f"⚠️ **Domain Notice**: {scope_reason}\n\n*How can I assist you with Plant Hazard Assessment, 5×5 Matrix Scoring, or ERM Approvals?*",
                blocked=True
            )

        # 4. Role-Based Action Validation
        metadata = getattr(request, "metadata", {}) or {}
        params = getattr(request, "parameters", {}) or {}
        user_role_id = metadata.get("role_id") or params.get("role_id") or getattr(request, "role_id", None)
        is_authorized, auth_reason = InputGuardrail.validate_role_authorization(sanitized_msg, user_role_id)
        if not is_authorized:
            return GuardrailResult(
                passed=False,
                sanitized_text="",
                reason=f"🚫 **Access Control Guardrail**: {auth_reason}",
                blocked=True
            )

        return GuardrailResult(passed=True, sanitized_text=sanitized_msg, blocked=False)

    @classmethod
    def process_output(cls, raw_output: str) -> str:
        """Validates and enforces post-generation safety, math accuracy, and clean markdown."""
        if not raw_output:
            return ""

        # 1. Industrial Safety Check
        is_safe, safety_msg = OutputGuardrail.check_industrial_safety(raw_output)
        if not is_safe:
            return f"⚠️ {safety_msg}"

        # 2. Mathematical Consistency (Score = L * I)
        math_verified_output, _ = OutputGuardrail.verify_mathematical_consistency(raw_output)

        # 3. Clean Markdown & Output Sanitization
        final_output = OutputGuardrail.sanitize_output(math_verified_output)

        return final_output
