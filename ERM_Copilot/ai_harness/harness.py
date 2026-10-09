"""
Enterprise Risk Management AI Harness (ERMAIHarness).
Coordinates security, RBAC policies, input/output guardrails, tool execution governance,
human confirmation lifecycle, and execution tracing around the ERMCopilotAgent.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from ERM_Copilot.ai_harness.context import HarnessContext
from ERM_Copilot.ai_harness.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConfirmationMismatchError,
    ConfirmationRequiredError,
    GuardrailViolationError,
    HarnessError,
)
from ERM_Copilot.ai_harness.execution import execution_coordinator
from ERM_Copilot.ai_harness.guardrails import harness_guardrails
from ERM_Copilot.ai_harness.observability import observability_tracer
from ERM_Copilot.ai_harness.tool_registry import tool_registry
from ERM_Copilot.models.contracts import AgentRequest, AgentResponse

logger = logging.getLogger("ERM_Copilot.ai_harness.harness")


class ERMAIHarness:
    """
    Production-grade ERM AI Harness.
    Acts as the shared execution and governance layer around the ERM Copilot orchestrator.
    """

    CANCELLATION_KEYWORDS = {"cancel", "abort", "stop", "no cancel", "cancel action", "discard", "no"}

    @classmethod
    def run(
        cls,
        context: HarnessContext,
        message: str,
        copilot_agent: Optional[Any] = None,
        **kwargs: Any,
    ) -> AgentResponse:
        """
        Main Harness execution entry point.
        
        Args:
            context: Verified, immutable server-side context containing user_id, user_role, dept_id, etc.
            message: Untrusted user chat prompt.
            copilot_agent: Optional custom master orchestrator instance (defaults to erm_copilot_agent).
            
        Returns:
            AgentResponse: Sanitized, role-compliant response with trace metadata.
        """
        # 1. Enforce Trusted Context Verification
        if not context or not isinstance(context, HarnessContext) or not context.is_authenticated:
            raise AuthenticationError("ERM AI Harness requires an authenticated, verified HarnessContext.")

        span = observability_tracer.start_span(
            name="erm_ai_harness_run",
            span_type="harness_execution",
            run_id=context.run_id,
            request_id=context.request_id,
            metadata=context.to_safe_trace_dict(),
        )

        try:
            # 2. Input Guardrail Inspection
            clean_message = harness_guardrails.validate_input(message, user_role=context.user_role)

            # 3. Check for Explicit Cancellation of Pending Action
            lower_msg = clean_message.strip().lower()
            if context.confirmation_state and lower_msg in cls.CANCELLATION_KEYWORDS:
                action_name = context.confirmation_state.get("action_name", "action")
                context.confirmation_state["status"] = "CANCELLED"
                observability_tracer.log_event("confirmation_cancelled", context.run_id, context.request_id, context.confirmation_state)
                
                resp = AgentResponse(
                    request_id=context.request_id,
                    agent_id="erm_ai_harness",
                    status="success",
                    success=True,
                    response=f"❌ Pending {action_name.replace('_', ' ')} has been cancelled. No database changes were made.",
                    metadata={"confirmation_status": "CANCELLED", "run_id": context.run_id}
                )
                span.complete(success=True)
                observability_tracer.record_span(span)
                return resp

            # 4. Resolve Master Orchestrator
            if copilot_agent is None:
                from ERM_Copilot import erm_copilot_agent
                copilot_agent = erm_copilot_agent

            # 5. Construct governed AgentRequest
            request_metadata = {
                "user_id": context.user_id,
                "role": context.user_role,
                "dept_id": context.dept_id,
                "dept_name": context.dept_name,
                "run_id": context.run_id,
                "request_id": context.request_id,
                "session_id": context.session_id,
                "confirmation_state": context.confirmation_state,
            }
            if context.trace_metadata:
                request_metadata.update(context.trace_metadata)

            agent_req = AgentRequest(
                message=clean_message,
                user_id=context.user_id,
                user_role=context.user_role,
                session_id=context.session_id,
                metadata=request_metadata,
                parameters=request_metadata,
            )

            # 6. Execute Orchestrator
            agent_resp = copilot_agent.process(agent_req)

            # 7. Output Guardrail Sanitization
            raw_response_text = getattr(agent_resp, "response", "") or getattr(agent_resp, "answer", "")
            sanitized_text = harness_guardrails.sanitize_output(raw_response_text)
            
            # Enrich response metadata with harness run_id and trace correlation
            resp_metadata = getattr(agent_resp, "metadata", {}) or {}
            resp_metadata["run_id"] = context.run_id
            resp_metadata["request_id"] = context.request_id
            resp_metadata["harness_governed"] = True

            final_response = AgentResponse(
                request_id=context.request_id,
                agent_id=getattr(agent_resp, "agent_id", "erm_copilot_agent"),
                status=getattr(agent_resp, "status", "success"),
                success=getattr(agent_resp, "success", True),
                response=sanitized_text,
                metadata=resp_metadata,
            )

            span.complete(success=True)
            observability_tracer.record_span(span)
            return final_response

        except GuardrailViolationError as gve:
            span.complete(success=False, error=gve)
            observability_tracer.record_span(span)
            return AgentResponse(
                request_id=context.request_id,
                agent_id="erm_ai_harness",
                status="blocked",
                success=False,
                response=f"🛡️ **Compliance Guardrail**: {gve.message}",
                metadata={"reason": gve.reason, "error_type": "GuardrailViolationError", "run_id": context.run_id}
            )

        except HarnessError as he:
            span.complete(success=False, error=he)
            observability_tracer.record_span(span)
            return AgentResponse(
                request_id=context.request_id,
                agent_id="erm_ai_harness",
                status="error",
                success=False,
                response=f"⚠️ **Governance Notice**: {he.message}",
                metadata={"error": he.to_dict(), "run_id": context.run_id}
            )

        except Exception as ex:
            span.complete(success=False, error=ex)
            observability_tracer.record_span(span)
            logger.error(f"[HARNESS_ERROR] Unhandled exception in ERMAIHarness: {ex}", exc_info=True)
            return AgentResponse(
                request_id=context.request_id,
                agent_id="erm_ai_harness",
                status="error",
                success=False,
                response="An unexpected error occurred while processing your risk management request. Please try again or contact support.",
                metadata={"run_id": context.run_id, "error_type": ex.__class__.__name__}
            )

    @classmethod
    def execute_governed_tool(
        cls,
        tool_name: str,
        arguments: Dict[str, Any],
        context: HarnessContext,
        bypass_confirmation: bool = False,
    ) -> Dict[str, Any]:
        """Direct programmatic interface for governed tool execution."""
        return execution_coordinator.execute_tool(
            tool_name=tool_name,
            arguments=arguments,
            context=context,
            bypass_confirmation=bypass_confirmation,
        )


erm_ai_harness = ERMAIHarness()
