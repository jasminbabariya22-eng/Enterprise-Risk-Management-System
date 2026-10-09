"""
Structured Workflow Event Tracing and Audit Logging for ERM Copilot.
Records lifecycle events (created, paused, resumed, completed, rejected)
separately from immutable business audit trails.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ERM_Copilot.ai_harness.observability import observability_tracer
from ERM_Copilot.workflow.contracts import AgentWorkflowState

logger = logging.getLogger("ERM_Copilot.workflow.events")


class WorkflowEventLogger:
    """Emits structured workflow lifecycle events to observability tracer."""

    @staticmethod
    def log_workflow_created(state: AgentWorkflowState) -> None:
        observability_tracer.log_event(
            event_type="workflow_created",
            run_id=state.workflow_id,
            request_id=state.conversation_id,
            data={
                "workflow_id": state.workflow_id,
                "workflow_type": state.workflow_type,
                "owner_user_id": state.owner_user_id,
                "owner_role": state.owner_role,
                "current_agent": state.current_agent,
                "current_step": state.current_step,
            }
        )

    @staticmethod
    def log_checkpoint_persisted(state: AgentWorkflowState) -> None:
        observability_tracer.log_event(
            event_type="checkpoint_persisted",
            run_id=state.workflow_id,
            request_id=state.conversation_id,
            data={
                "workflow_id": state.workflow_id,
                "status": state.workflow_status,
                "step": state.current_step,
                "state_version": state.state_version,
            }
        )

    @staticmethod
    def log_checkpoint_restored(state: AgentWorkflowState) -> None:
        observability_tracer.log_event(
            event_type="checkpoint_restored",
            run_id=state.workflow_id,
            request_id=state.conversation_id,
            data={
                "workflow_id": state.workflow_id,
                "status": state.workflow_status,
                "step": state.current_step,
                "state_version": state.state_version,
            }
        )

    @staticmethod
    def log_confirmation_required(state: AgentWorkflowState, action_name: str, fingerprint: str) -> None:
        observability_tracer.log_event(
            event_type="confirmation_required",
            run_id=state.workflow_id,
            request_id=state.conversation_id,
            data={
                "workflow_id": state.workflow_id,
                "action_name": action_name,
                "fingerprint": fingerprint,
            }
        )

    @staticmethod
    def log_workflow_completed(state: AgentWorkflowState) -> None:
        observability_tracer.log_event(
            event_type="workflow_completed",
            run_id=state.workflow_id,
            request_id=state.conversation_id,
            data={
                "workflow_id": state.workflow_id,
                "total_steps": state.step_count,
                "risk_id": state.risk_id,
            }
        )


workflow_event_logger = WorkflowEventLogger()
