"""
Enterprise Risk Management (ERM) - Goal-Driven Treatment Management Agent.
A state-driven, adaptive, tool-using conversational agent coordinating ISO-31000 risk treatments,
mitigation action plans, progress updates, owner reassignments, and audit inspections.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    import logfire
except ImportError:
    class DummyLogfire:
        def info(self, *args, **kwargs): pass
        def error(self, *args, **kwargs): pass
        def warning(self, *args, **kwargs): pass
        def debug(self, *args, **kwargs): pass
    logfire = DummyLogfire()

from ERM_Copilot.agents.base import BaseAgent
from ERM_Copilot.services.db_service import erm_db
from ERM_Copilot.agents.treatment.execution import (
    bind_pending_confirmation,
    execute_confirmed_treatment_decision,
)
from ERM_Copilot.agents.treatment.extraction import (
    extract_treatment_inputs,
    is_add_treatment_trigger,
    is_cancellation,
    is_list_treatments_trigger,
    is_reassign_owner_trigger,
    is_show_details_trigger,
    is_update_progress_trigger,
    is_user_cancelling,
    is_user_confirming,
)
from ERM_Copilot.agents.treatment.merge import (
    apply_documented_treatment_defaults,
    merge_treatment_inputs,
)
from ERM_Copilot.agents.treatment.planner import (
    TreatmentActionType,
    TreatmentPlanDecision,
    TreatmentWorkflowPlanner,
)
from ERM_Copilot.agents.treatment.prompts import (
    format_add_treatment_preview,
    format_add_treatment_success,
    format_cancellation_response,
    format_list_treatments_response,
    format_missing_action_owner_prompt,
    format_missing_action_plan_prompt,
    format_missing_new_owner_prompt,
    format_missing_progress_prompt,
    format_missing_risk_prompt,
    format_missing_treatment_id_prompt,
    format_policy_block_response,
    format_reassign_owner_preview,
    format_reassign_owner_success,
    format_treatment_details_response,
    format_update_progress_preview,
    format_update_progress_success,
)
from ERM_Copilot.agents.treatment.state import (
    TreatmentGoal,
    TreatmentSession,
    TreatmentState,
    TreatmentWorkflowState,
    extract_risk_identifier,
    extract_treatment_id,
    parse_date_string,
    parse_progress_percentage,
)
from ERM_Copilot.agents.treatment.tools import (
    fetch_eligible_action_owners,
    fetch_risk_info,
    fetch_treatment_details,
    fetch_treatments_for_risk,
)
from ERM_Copilot.models.contracts import AgentRequest, AgentResponse, RequestContext

logger = logging.getLogger("ERM_Copilot.agents.treatment.agent")


class TreatmentManagementAgent(BaseAgent):
    """
    Goal-driven, adaptive agent for Enterprise Risk Treatment / Action Plan Management.
    Handles formulation, tracking, milestone progress updates, owner reassignment, and listings.
    """

    MAX_ITERATIONS = 4

    def __init__(self):
        super().__init__(
            agent_id="treatment_management_agent",
            name="ERM Treatment Management Agent",
            description="Goal-driven agent for multi-turn ISO-31000 Risk Treatment & Action Plan formulation, tracking, and reassignment.",
            capabilities=[
                "add_action_plan",
                "update_treatment_progress",
                "reassign_action_owner",
                "list_risk_treatments",
                "get_treatment_details",
            ]
        )
        self.sessions: Dict[str, TreatmentSession] = {}
        self.planner = TreatmentWorkflowPlanner()

    def execute(self, request: AgentRequest, context: RequestContext) -> Any:
        return self.process(request)

    # -----------------------------------------------------------------
    # Session Management & Checkpointing
    # -----------------------------------------------------------------

    def get_session_key(self, request: AgentRequest) -> str:
        """Derive isolated session key bound to authenticated user and session."""
        user_id = str(getattr(request, "user_id", None) or (request.metadata or {}).get("user_id") or "").strip()
        sess_id = str(getattr(request, "session_id", None) or (request.metadata or {}).get("session_id") or "").strip()
        return f"{user_id}::{sess_id}" if sess_id else user_id

    def get_session(self, session_key: str) -> Optional[TreatmentSession]:
        """Retrieve active in-memory session or restore from PostgreSQL checkpoint."""
        if session_key in self.sessions:
            return self.sessions[session_key]
        try:
            from ERM_Copilot.workflow import workflow_checkpointer, WorkflowType
            active_wf = workflow_checkpointer.load_active_for_session(session_key)
            if active_wf and active_wf.workflow_type == WorkflowType.TREATMENT_MANAGEMENT.value and active_wf.collected_fields:
                sess = TreatmentSession.from_dict(active_wf.collected_fields)
                self.sessions[session_key] = sess
                return sess
        except Exception as e:
            logger.debug(f"[CHECKPOINTER_LOAD] Fallback in treatment agent: {e}")
        return None

    def is_session_active(self, session_key: str) -> bool:
        """Check if an active, non-terminal session exists."""
        sess = self.get_session(session_key)
        return sess is not None and not sess.is_terminal

    def clear_session(self, session_key: str) -> None:
        """Cancel and purge in-memory session and mark checkpoint cancelled."""
        if session_key in self.sessions:
            del self.sessions[session_key]
        try:
            from ERM_Copilot.workflow import workflow_checkpointer, WorkflowStatus
            active_wf = workflow_checkpointer.load_active_for_session(session_key)
            if active_wf and not active_wf.is_terminal:
                active_wf.transition_to(WorkflowStatus.CANCELLED, reason="Session cleared")
                workflow_checkpointer.save(active_wf)
        except Exception as e:
            logger.debug(f"[CHECKPOINT_CANCEL_ERROR] {e}")

    # -----------------------------------------------------------------
    # Trigger & Intent Detection Helpers (Backward Compatible)
    # -----------------------------------------------------------------

    @staticmethod
    def is_cancellation(msg: str) -> bool:
        return is_user_cancelling(msg)

    @staticmethod
    def is_add_treatment_trigger(msg: str) -> bool:
        return is_add_treatment_trigger(msg)

    @staticmethod
    def is_update_progress_trigger(msg: str) -> bool:
        return is_update_progress_trigger(msg)

    @staticmethod
    def is_reassign_owner_trigger(msg: str) -> bool:
        return is_reassign_owner_trigger(msg)

    @staticmethod
    def is_list_treatments_trigger(msg: str) -> bool:
        return is_list_treatments_trigger(msg)

    def is_treatment_trigger(self, msg: str) -> bool:
        """Unified check whether a message is meant for the treatment management agent."""
        if not msg:
            return False
        return (
            is_add_treatment_trigger(msg)
            or is_update_progress_trigger(msg)
            or is_reassign_owner_trigger(msg)
            or is_list_treatments_trigger(msg)
            or is_show_details_trigger(msg)
        )

    # -----------------------------------------------------------------
    # Main Goal-Driven Process Loop
    # -----------------------------------------------------------------

    def process(self, request: AgentRequest) -> AgentResponse:
        """
        Execute goal-driven turn: extract goal, select tools dynamically,
        evaluate results, and decide next action.
        """
        req_id = getattr(request, "request_id", None) or str(uuid.uuid4())
        session_key = self.get_session_key(request)
        msg = (request.message or "").strip()

        # 1. Strict Authentication & Role Check - Fail Closed
        auth_uid = getattr(request, "user_id", None) or (request.metadata or {}).get("user_id")
        if not auth_uid or not str(auth_uid).strip():
            return AgentResponse(
                request_id=req_id,
                agent_id=self.agent_id,
                status="error",
                success=False,
                response="❌ **Authentication Failure:** No authenticated user detected. Treatment management actions require user identity.",
                metadata={"intent": "AUTH_FAILURE"}
            )

        raw_role = getattr(request, "user_role", None) or (request.metadata or {}).get("role")
        if not raw_role or not str(raw_role).strip():
            return AgentResponse(
                request_id=req_id,
                agent_id=self.agent_id,
                status="error",
                success=False,
                response="❌ **Authorization Failure:** No authenticated role detected. Treatment management actions require a valid assigned role.",
                metadata={"intent": "ROLE_MISSING"}
            )

        user_role = str(raw_role).strip()
        dept_id = (request.metadata or {}).get("dept_id") or getattr(request, "dept_id", None)
        dept_name = (request.metadata or {}).get("dept_name") or getattr(request, "dept_name", None)

        # 2. Session Loading or Initialization
        session = self.get_session(session_key)
        extracted = extract_treatment_inputs(msg, current_goal=session.goal if session else None)

        # Reset session if starting a brand new goal or on explicit action switch
        is_action_switch = bool(
            session and extracted.goal and extracted.goal != TreatmentGoal.UNKNOWN and session.goal != extracted.goal
        )
        is_new_target = bool(
            session and extracted.target_risk_id and session.target_risk_id and extracted.target_risk_id != session.target_risk_id
        )
        is_new_trigger = bool(
            session and (is_add_treatment_trigger(msg) or is_update_progress_trigger(msg) or is_reassign_owner_trigger(msg))
        )

        if not session or session.is_terminal or is_action_switch or is_new_target or is_new_trigger:
            session = TreatmentSession(
                session_id=session_key,
                user_id=str(auth_uid),
                user_role=user_role,
                dept_id=dept_id,
                dept_name=dept_name,
                goal=extracted.goal or TreatmentGoal.UNKNOWN,
                state=TreatmentWorkflowState.INITIATION,
                last_user_message=msg,
            )
            self.sessions[session_key] = session
        else:
            session.user_id = str(auth_uid)
            session.user_role = user_role
            if dept_id is not None:
                session.dept_id = dept_id
            if dept_name is not None:
                session.dept_name = dept_name
            session.last_user_message = msg

        # Unconditionally merge extracted inputs with full provenance tracking
        merge_treatment_inputs(session, extracted, raw_message=msg)

        session.step_count += 1

        # 3. Dynamic Bounded Execution Loop (max 4 tool iterations per turn)
        final_response_text = ""
        final_intent = "TREATMENT_PROCESSING"
        is_success = True

        for iteration in range(self.MAX_ITERATIONS):
            plan = self.planner.plan(
                session=session,
                is_confirmation=extracted.is_confirmation,
                is_cancellation=extracted.is_cancellation,
            )

            # --- A. CANCEL SESSION ---
            if plan.action_type == TreatmentActionType.CANCEL_SESSION:
                if session.pending_confirmation:
                    session.pending_confirmation["status"] = "CANCELLED"
                session.state = TreatmentWorkflowState.CANCELLED
                final_response_text = format_cancellation_response(session.target_risk_id or f"#{session.treatment_id}")
                final_intent = "TREATMENT_CANCELLED"
                self.clear_session(session_key)
                break

            # --- B. REQUEST MISSING INPUT ---
            elif plan.action_type == TreatmentActionType.REQUEST_MISSING_INPUT:
                if plan.missing_field == "target_risk_id":
                    # Load candidate risks for dropdown
                    session.available_risks = fetch_risk_info(session, "") or []
                    final_response_text = format_missing_risk_prompt(session)
                    final_intent = "AWAITING_RISK_ID"
                    session.state = TreatmentWorkflowState.COLLECTING_INFO
                elif plan.missing_field == "action_plan":
                    final_response_text = format_missing_action_plan_prompt(session)
                    final_intent = "AWAITING_ACTION_PLAN"
                    session.state = TreatmentWorkflowState.COLLECTING_INFO
                elif plan.missing_field == "action_owner_id":
                    final_response_text = format_missing_action_owner_prompt(session)
                    final_intent = "AWAITING_ACTION_OWNER"
                    session.state = TreatmentWorkflowState.COLLECTING_INFO
                elif plan.missing_field == "treatment_id":
                    final_response_text = format_missing_treatment_id_prompt(session)
                    final_intent = "AWAITING_TREATMENT_ID"
                    session.state = TreatmentWorkflowState.COLLECTING_INFO
                elif plan.missing_field == "progress":
                    final_response_text = format_missing_progress_prompt(session)
                    final_intent = "AWAITING_PROGRESS"
                    session.state = TreatmentWorkflowState.COLLECTING_INFO
                elif plan.missing_field == "new_action_owner_id":
                    final_response_text = format_missing_new_owner_prompt(session)
                    final_intent = "AWAITING_NEW_OWNER"
                    session.state = TreatmentWorkflowState.COLLECTING_INFO
                else:
                    final_response_text = "How can I assist with your risk treatment plans today?"
                    final_intent = "TREATMENT_HELP"
                break

            # --- C. FETCH RISK INFO ---
            elif plan.action_type == TreatmentActionType.FETCH_RISK_INFO:
                risk = fetch_risk_info(session, session.target_risk_id or "")
                if not risk:
                    final_response_text = f"❌ Target risk **{session.target_risk_id}** was not found in the Enterprise Risk Register."
                    final_intent = "RISK_NOT_FOUND"
                    session.state = TreatmentWorkflowState.FAILED
                    is_success = False
                    break
                session.risk_data = risk
                session.target_risk_register_id = risk.get("risk_register_id") or risk.get("id")
                session.target_risk_name = risk.get("risk_name") or risk.get("risk_title")
                continue

            # --- D. FETCH TREATMENT DETAILS ---
            elif plan.action_type == TreatmentActionType.FETCH_TREATMENT_DETAILS:
                t = fetch_treatment_details(session, int(session.treatment_id))
                if not t:
                    final_response_text = f"❌ Treatment **#{session.treatment_id}** was not found in the database."
                    final_intent = "TREATMENT_NOT_FOUND"
                    session.state = TreatmentWorkflowState.FAILED
                    is_success = False
                    break
                session.action_plan = t.get("action_plan")
                session.target_risk_id = t.get("risk_id")
                session.target_risk_name = t.get("risk_name")
                session.action_owner_id = t.get("action_owner_id")
                session.action_owner_name = t.get("action_owner_name")
                session.target_date = t.get("target_date")
                session.api_result = t
                continue

            # --- E. FETCH ELIGIBLE OWNERS ---
            elif plan.action_type == TreatmentActionType.FETCH_ELIGIBLE_OWNERS:
                owners = fetch_eligible_action_owners(session)
                session.available_action_owners = owners
                continue

            # --- F. FETCH TREATMENTS LIST ---
            elif plan.action_type == TreatmentActionType.FETCH_TREATMENTS_LIST:
                t_list = fetch_treatments_for_risk(session, session.target_risk_id or "")
                session.available_treatments = t_list
                continue

            # --- G. REPORT POLICY BLOCK ---
            elif plan.action_type == TreatmentActionType.REPORT_POLICY_BLOCK:
                session.state = TreatmentWorkflowState.POLICY_BLOCKED
                session.policy_block_reason = plan.policy_reason
                final_response_text = format_policy_block_response(plan.policy_reason or "Governance policy violation.", session.target_risk_id)
                final_intent = "TREATMENT_POLICY_BLOCKED"
                is_success = False
                break

            # --- H. VALIDATE AND PREVIEW (AWAITING CONFIRMATION) ---
            elif plan.action_type == TreatmentActionType.VALIDATE_AND_PREVIEW:
                goal = session.goal
                if goal == TreatmentGoal.ADD_TREATMENT:
                    bind_pending_confirmation(
                        session=session,
                        action=goal.value,
                        target_id=session.target_risk_id,
                        arguments={
                            "risk_register_id": session.target_risk_register_id,
                            "action_plan": session.action_plan,
                            "action_owner_id": session.action_owner_id,
                            "target_date": session.target_date,
                            "progress": session.progress,
                            "action_status_id": session.action_status_id,
                        }
                    )
                    final_response_text = format_add_treatment_preview(session)
                    final_intent = "AWAITING_CONFIRMATION"

                elif goal == TreatmentGoal.UPDATE_PROGRESS:
                    current_prog = int((session.api_result or {}).get("progress", 0)) if session.api_result else None
                    bind_pending_confirmation(
                        session=session,
                        action=goal.value,
                        target_id=session.treatment_id,
                        arguments={
                            "treatment_id": session.treatment_id,
                            "progress": session.progress,
                            "remarks": session.remarks,
                        }
                    )
                    final_response_text = format_update_progress_preview(session, current_progress=current_prog)
                    final_intent = "AWAITING_CONFIRMATION"

                elif goal == TreatmentGoal.REASSIGN_OWNER:
                    current_ao = (session.api_result or {}).get("action_owner_name")
                    bind_pending_confirmation(
                        session=session,
                        action=goal.value,
                        target_id=session.treatment_id,
                        arguments={
                            "treatment_id": session.treatment_id,
                            "new_action_owner_id": session.new_action_owner_id,
                        }
                    )
                    final_response_text = format_reassign_owner_preview(session, current_owner=current_ao)
                    final_intent = "AWAITING_CONFIRMATION"
                break

            # --- I. EXECUTE MUTATION ---
            elif plan.action_type == TreatmentActionType.EXECUTE_MUTATION:
                success, result_dict, err = execute_confirmed_treatment_decision(session)
                session.api_result = result_dict
                if success:
                    session.state = TreatmentWorkflowState.COMPLETED
                    if session.goal == TreatmentGoal.ADD_TREATMENT:
                        final_response_text = format_add_treatment_success(result_dict)
                        final_intent = "TREATMENT_ADDED"
                    elif session.goal == TreatmentGoal.UPDATE_PROGRESS:
                        final_response_text = format_update_progress_success(result_dict)
                        final_intent = "PROGRESS_UPDATED"
                    elif session.goal == TreatmentGoal.REASSIGN_OWNER:
                        final_response_text = format_reassign_owner_success(result_dict)
                        final_intent = "OWNER_REASSIGNED"
                    self.clear_session(session_key)
                else:
                    session.state = TreatmentWorkflowState.FAILED
                    final_response_text = f"❌ **Treatment Execution Failed:** {err}"
                    final_intent = "TREATMENT_FAILED"
                    is_success = False
                break

            # --- J. RESPOND AND COMPLETE (READ-ONLY) ---
            elif plan.action_type == TreatmentActionType.RESPOND_AND_COMPLETE:
                if session.goal == TreatmentGoal.LIST_TREATMENTS:
                    final_response_text = format_list_treatments_response(
                        session.available_treatments or [],
                        session.target_risk_id,
                    )
                    final_intent = "TREATMENTS_LISTED"
                elif session.goal == TreatmentGoal.SHOW_TREATMENT_DETAILS:
                    final_response_text = format_treatment_details_response(session.api_result or {})
                    final_intent = "TREATMENT_DETAILS_SHOWN"

                session.state = TreatmentWorkflowState.COMPLETED
                self.clear_session(session_key)
                break

            # --- K. FAIL SAFELY ---
            elif plan.action_type == TreatmentActionType.FAIL_SAFELY:
                session.state = TreatmentWorkflowState.FAILED
                final_response_text = f"⚠️ {plan.policy_reason or 'Execution stopped safely.'}"
                final_intent = "EXECUTION_HALTED"
                is_success = False
                break

        # 4. PostgreSQL Checkpoint Persistence
        try:
            from ERM_Copilot.workflow import workflow_checkpointer, AgentWorkflowState, WorkflowStatus, WorkflowType
            active_wf = workflow_checkpointer.load_active_for_session(session_key)
            if session.is_terminal:
                if active_wf and not active_wf.is_terminal:
                    status = WorkflowStatus.COMPLETED if session.state == TreatmentWorkflowState.COMPLETED else WorkflowStatus.CANCELLED
                    active_wf.transition_to(status, step=session.state.value)
                    workflow_checkpointer.save(active_wf)
            else:
                if not active_wf:
                    active_wf = AgentWorkflowState(
                        session_id=session_key,
                        workflow_type=WorkflowType.TREATMENT_MANAGEMENT,
                        owner_user_id=str(auth_uid),
                        owner_role=user_role,
                        dept_id=dept_id,
                        dept_name=dept_name,
                        current_agent=self.agent_id,
                        current_step=session.state.value,
                        risk_id=session.target_risk_id,
                        collected_fields=session.to_dict(),
                    )
                else:
                    active_wf.current_step = session.state.value
                    active_wf.risk_id = session.target_risk_id or active_wf.risk_id
                    active_wf.collected_fields = session.to_dict()
                    active_wf.step_count += 1
                    if session.state == TreatmentWorkflowState.AWAITING_CONFIRMATION:
                        active_wf.transition_to(WorkflowStatus.WAITING_FOR_CONFIRMATION, step="AWAITING_CONFIRMATION")
                workflow_checkpointer.save(active_wf)
        except Exception as cp_err:
            logger.debug(f"[CHECKPOINT_SAVE_ERROR] in TreatmentManagementAgent: {cp_err}")

        return AgentResponse(
            request_id=req_id,
            agent_id=self.agent_id,
            status="success" if is_success else "error",
            success=is_success,
            response=final_response_text or "Treatment processing update.",
            metadata={
                "intent": final_intent,
                "goal": session.goal.value if isinstance(session.goal, TreatmentGoal) else str(session.goal),
                "state": session.state.value if isinstance(session.state, TreatmentWorkflowState) else str(session.state),
                "risk_id": session.target_risk_id,
                "treatment_id": session.treatment_id,
                "progress": session.progress,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )


# Singleton instance
treatment_management_agent = TreatmentManagementAgent()
