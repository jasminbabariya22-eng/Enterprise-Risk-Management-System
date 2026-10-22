"""
Governed Tool Execution Coordinator for ERM AI Harness.
Coordinates tool lookup, argument validation, RBAC checks, confirmation enforcement,
timeout bounding, retry policies, and trace recording.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from ERM_Copilot.ai_harness.confirmation import confirmation_manager
from ERM_Copilot.ai_harness.context import HarnessContext
from ERM_Copilot.ai_harness.exceptions import (
    AuthorizationError,
    BoundedExecutionError,
    ConfirmationMismatchError,
    ConfirmationRequiredError,
    HarnessError,
    ToolNotFoundError,
    ToolValidationError,
)
from ERM_Copilot.ai_harness.observability import observability_tracer
from ERM_Copilot.ai_harness.policies import (
    ROLE_ADMIN,
    ROLE_SUPER_ADMIN,
    ROLE_RISK_MANAGER,
    ROLE_RISK_HEADER,
    enforce_tool_rbac,
    normalize_role,
)
from ERM_Copilot.ai_harness.retry import RetryPolicy
from ERM_Copilot.ai_harness.tool_registry import tool_registry

logger = logging.getLogger("ERM_Copilot.ai_harness.execution")


class ExecutionCoordinator:
    """
    Executes tools under strict governance, security, and safety constraints.
    """

    @classmethod
    def execute_tool(
        cls,
        tool_name: str,
        arguments: Dict[str, Any],
        context: HarnessContext,
        bypass_confirmation: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute a registered tool under full harness governance.
        """
        span = observability_tracer.start_span(
            name=f"tool:{tool_name}",
            span_type="tool_execution",
            run_id=context.run_id,
            request_id=context.request_id,
            metadata={"tool_name": tool_name, "user_id": context.user_id, "user_role": context.user_role},
        )

        try:
            # 1. Look up tool in centralized registry
            tool = tool_registry.get(tool_name)

            # 2. RBAC Policy Check: user role must be permitted
            enforce_tool_rbac(tool.name, context.user_role, tool.allowed_roles)

            # 3. Argument validation
            validated_args = tool_registry.validate_arguments(tool.name, arguments)

            # Injected trusted server credentials (never trust LLM for user_id/approver_id)
            if "approver_id" in validated_args or tool_name == "approve_or_reject_risk":
                validated_args["approver_id"] = int(context.user_id)
            if "created_by" in validated_args or "user_id" in validated_args:
                if "created_by" in validated_args:
                    validated_args["created_by"] = int(context.user_id)
                if "user_id" in validated_args and tool_name in ("save_risk", "resubmit_risk"):
                    validated_args["user_id"] = int(context.user_id)
            if "modified_by" in validated_args or tool_name == "update_treatment_progress":
                validated_args["modified_by"] = int(context.user_id)
            if tool_name in (
                "lookup_eligible_owners", "get_eligible_risk_owners",
                "get_mitigation_suggestions", "generate_mitigation_suggestions",
                "get_action_plan_suggestions", "generate_action_plan_suggestions",
                "detect_duplicate_risks", "check_risk_duplicates",
                "assess_risk_completeness", "validate_risk_payload",
                "get_risk_creation_requirements",
            ):
                validated_args["caller_role"] = context.user_role
                validated_args["caller_dept_id"] = context.dept_id
                validated_args["caller_user_id"] = context.user_id
            if tool_name in (
                "resolve_reference_data", "get_risk_reference_options",
                "get_mitigation_suggestions", "generate_mitigation_suggestions",
                "get_action_plan_suggestions", "generate_action_plan_suggestions",
                "detect_duplicate_risks", "check_risk_duplicates",
                "assess_risk_completeness", "validate_risk_payload",
                "get_risk_creation_requirements",
            ):
                if validated_args.get("dept_id") is None and context.dept_id is not None:
                    validated_args["dept_id"] = context.dept_id
            if tool_name in ("create_risk", "save_risk"):
                validated_args["risk_owner_id"] = context.user_id
                # Enforce department context: standard users cannot spoof department
                is_admin_or_enterprise = normalize_role(context.user_role) in (
                    ROLE_ADMIN, ROLE_SUPER_ADMIN, ROLE_RISK_MANAGER, ROLE_RISK_HEADER
                )
                if not is_admin_or_enterprise or not validated_args.get("dept_id"):
                    if context.dept_id is not None:
                        validated_args["dept_id"] = context.dept_id

            # 4. Confirmation verification for state-changing operations
            if tool.requires_confirmation and not bypass_confirmation:
                cls._verify_or_require_confirmation(tool_name, validated_args, context)

            # 5. Bounded execution with retry governance
            def _runner():
                return tool.handler(**validated_args)

            result, retry_count = RetryPolicy.execute_with_retry(
                func=_runner,
                tool_name=tool.name,
                is_idempotent=tool.is_idempotent,
                is_state_changing=tool.is_state_changing,
                max_retries=tool.max_retries,
                timeout_seconds=tool.timeout_seconds,
            )

            # Mark confirmation state as EXECUTED to prevent replay
            if context.confirmation_state and tool.requires_confirmation:
                context.confirmation_state["status"] = "EXECUTED"

            span.complete(success=True, retry_count=retry_count)
            observability_tracer.record_span(span)

            return {
                "success": True,
                "tool_name": tool.name,
                "result": result,
                "retry_count": retry_count,
            }


        except Exception as e:
            span.complete(success=False, error=e)
            observability_tracer.record_span(span)
            logger.error(f"[TOOL_EXEC_FAIL] tool='{tool_name}' user='{context.user_id}' error: {e}")
            raise e

    @classmethod
    def _verify_or_require_confirmation(
        cls,
        tool_name: str,
        arguments: Dict[str, Any],
        context: HarnessContext,
    ) -> None:
        """
        Check if valid pending confirmation exists and matches current payload.
        If no confirmation exists, create pending confirmation and raise ConfirmationRequiredError.
        """
        pending_state = context.confirmation_state
        risk_id = arguments.get("risk_id") or arguments.get("risk_identifier")

        if not pending_state:
            # Create a new pending confirmation state
            new_state = confirmation_manager.create_pending_confirmation(
                action_name=tool_name,
                user_id=context.user_id,
                user_role=context.user_role,
                risk_id=risk_id,
                parameters=arguments,
                summary_text=f"Please confirm execution of '{tool_name}' on risk '{risk_id or 'N/A'}'.",
            )
            context.confirmation_state = new_state
            raise ConfirmationRequiredError(
                message=f"Action '{tool_name}' requires explicit confirmation.",
                confirmation_token=new_state["token"],
                pending_action=new_state,
            )

        # Validate provided confirmation against arguments & user identity
        confirmation_manager.validate_confirmation(
            pending_state=pending_state,
            executing_user_id=context.user_id,
            executing_action=tool_name,
            executing_params=arguments,
            executing_risk_id=risk_id,
        )


execution_coordinator = ExecutionCoordinator()
