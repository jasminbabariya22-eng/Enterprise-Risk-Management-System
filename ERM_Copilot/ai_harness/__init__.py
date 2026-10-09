"""
ERM AI Harness Package.
Shared execution, security, governance, observability, and tool policy layer for ERM Copilot.
"""
from ERM_Copilot.ai_harness.context import HarnessContext
from ERM_Copilot.ai_harness.exceptions import (
    AuthenticationError,
    AuthorizationError,
    BoundedExecutionError,
    ConfirmationError,
    ConfirmationMismatchError,
    ConfirmationRequiredError,
    GuardrailViolationError,
    HarnessError,
    NonIdempotentRetryError,
    ToolNotFoundError,
    ToolValidationError,
)
from ERM_Copilot.ai_harness.execution import ExecutionCoordinator, execution_coordinator
from ERM_Copilot.ai_harness.guardrails import HarnessGuardrails, harness_guardrails
from ERM_Copilot.ai_harness.harness import ERMAIHarness, erm_ai_harness
from ERM_Copilot.ai_harness.observability import ObservabilityTracer, TraceSpan, observability_tracer
from ERM_Copilot.ai_harness.policies import ToolCategory, enforce_tool_rbac, is_role_authorized_for_tool
from ERM_Copilot.ai_harness.retry import RetryPolicy
from ERM_Copilot.ai_harness.tool_registry import ToolDefinition, ToolRegistry, tool_registry

__all__ = [
    "ERMAIHarness",
    "erm_ai_harness",
    "HarnessContext",
    "ToolRegistry",
    "tool_registry",
    "ToolDefinition",
    "ToolCategory",
    "ExecutionCoordinator",
    "execution_coordinator",
    "HarnessGuardrails",
    "harness_guardrails",
    "ObservabilityTracer",
    "observability_tracer",
    "TraceSpan",
    "RetryPolicy",
    "enforce_tool_rbac",
    "is_role_authorized_for_tool",
    "HarnessError",
    "AuthenticationError",
    "AuthorizationError",
    "ToolNotFoundError",
    "ToolValidationError",
    "ConfirmationRequiredError",
    "ConfirmationMismatchError",
    "GuardrailViolationError",
    "BoundedExecutionError",
    "NonIdempotentRetryError",
]
