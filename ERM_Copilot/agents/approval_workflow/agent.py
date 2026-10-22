"""
Enterprise Risk Management (ERM) - Goal-Driven Approval Workflow Agent.
A state-driven, tool-using conversational agent coordinating governance sign-offs,
status checks, queue queries, and audit trails.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ERM_Copilot.agents.base import BaseAgent
from ERM_Copilot.models.contracts import AgentRequest, AgentResponse, RequestContext
from ERM_Copilot.agents.approval_workflow.state import (
    ApprovalGoal,
    ApprovalWorkflowSession,
    ApprovalWorkflowState,
)
from ERM_Copilot.agents.approval_workflow.extraction import (
    extract_goal_and_inputs,
    is_user_cancelling,
    is_user_confirming,
)
from ERM_Copilot.agents.approval_workflow.planner import (
    ApprovalActionType,
    ApprovalWorkflowPlanner,
)
from ERM_Copilot.agents.approval_workflow.tools import (
    fetch_pending_approvals,
    fetch_risk_details,
    fetch_risk_audit_trail,
)
from ERM_Copilot.agents.approval_workflow.execution import (
    bind_pending_confirmation,
    execute_confirmed_decision,
)
from ERM_Copilot.agents.approval_workflow.prompts import (
    format_pending_approvals_response,
    format_risk_details_response,
    format_audit_trail_response,
    format_status_check_response,
    format_missing_risk_id_prompt,
    format_missing_action_prompt,
    format_missing_remark_prompt,
    format_confirmation_prompt,
    format_policy_block_response,
    format_success_response,
    format_cancellation_response,
)

logger = logging.getLogger("ERM_Copilot.agents.approval_workflow.agent")


class ApprovalWorkflowAgent(BaseAgent):
    """
    Goal-driven, tool-using agent for ERM Governance Approvals, Rejections,
    Status Inquiries, Queue Lookups, and Audit History.
    """

    def __init__(self):
        super().__init__(
            agent_id="agent_approval_workflow",
            name="ERM Governance Approval Agent",
            description="Goal-driven agent managing multi-tier governance sign-offs, queues, and audit trails.",
            capabilities=[
                "get_pending_approvals",
                "get_risk_details",
                "get_risk_audit_trail",
                "check_approval_status",
                "approve_or_reject_risk",
            ]
        )
        self.sessions: Dict[str, ApprovalWorkflowSession] = {}

    def execute(self, request: AgentRequest, context: RequestContext) -> Any:
        return self.process(request)

    # -----------------------------------------------------------------
    # Session Lifecycle Management
    # -----------------------------------------------------------------

    def get_session_key(self, request: AgentRequest) -> str:
        """Resolve isolated session key from user_id and session_id."""
        user_id = str(getattr(request, "user_id", None) or (request.metadata or {}).get("user_id") or "").strip()
        sess_id = str(getattr(request, "session_id", None) or (request.metadata or {}).get("session_id") or "").strip()
        if user_id and sess_id:
            return f"{user_id}::{sess_id}"
        return user_id or sess_id or "anonymous"

    def get_session(self, session_key: str) -> Optional[ApprovalWorkflowSession]:
        """Load session from memory or PostgreSQL checkpointer."""
        key = str(session_key).strip()
        if key in self.sessions:
            return self.sessions[key]
        for k, s in self.sessions.items():
            if k.startswith(f"{key}::") or k.endswith(f"::{key}") or str(s.user_id) == str(key):
                return s
        try:
            from ERM_Copilot.workflow import workflow_checkpointer, WorkflowType
            active_wf = workflow_checkpointer.load_active_for_session(key)
            if active_wf and active_wf.workflow_type == WorkflowType.APPROVAL_GOVERNANCE.value and active_wf.collected_fields:
                sess = ApprovalWorkflowSession.from_dict(active_wf.collected_fields)
                self.sessions[key] = sess
                return sess
        except Exception as e:
            logger.debug(f"[CHECKPOINTER_LOAD] Fallback in approval agent: {e}")
        return None

    def is_session_active(self, session_key: str) -> bool:
        """Verify whether an active non-terminal session exists."""
        key = str(session_key).strip()
        if not key:
            return False
        if key in self.sessions:
            return not self.sessions[key].is_terminal
        for k, s in self.sessions.items():
            if (k.startswith(f"{key}::") or k.endswith(f"::{key}")) and not s.is_terminal:
                return True
        try:
            from ERM_Copilot.workflow import workflow_checkpointer, WorkflowType
            active_wf = workflow_checkpointer.load_active_for_session(key)
            if active_wf and active_wf.workflow_type == WorkflowType.APPROVAL_GOVERNANCE.value:
                return not active_wf.is_terminal
        except Exception:
            pass
        return False

    def clear_session(self, session_key: str) -> None:
        """Clean up active session and update checkpoint to CANCELLED/COMPLETED."""
        key = str(session_key).strip()
        to_del = [k for k in self.sessions if k == key or k.startswith(f"{key}::") or k.endswith(f"::{key}")]
        for k in to_del:
            del self.sessions[k]
        try:
            from ERM_Copilot.workflow import workflow_checkpointer, WorkflowStatus
            active_wf = workflow_checkpointer.load_active_for_session(key)
            if active_wf and not active_wf.is_terminal:
                active_wf.transition_to(WorkflowStatus.CANCELLED, reason="Session cleared")
                workflow_checkpointer.save(active_wf)
        except Exception:
            pass

    # -----------------------------------------------------------------
    # Trigger Recognition
    # -----------------------------------------------------------------

    def is_approval_trigger(self, msg: str) -> bool:
        """Detect if message intends to view approvals, check status, or execute an approval."""
        if not msg:
            return False
        lower = msg.lower().strip()

        # Pure read-only queue request check
        pure_queue_triggers = [
            "approval queue", "approvals queue", "show approval queue", "view approval queue",
            "show pending approvals", "list pending approvals", "what are my pending approvals",
            "show approvals", "list approvals", "view approvals", "pending approvals", "pending approval",
            "find the pending approvals for my department", "find the pending approvals"
        ]
        if any(lower == q or lower.startswith(q + " ") or q in lower for q in pure_queue_triggers):
            return True

        # Check status or why can't I approve
        if any(w in lower for w in [
            "why can't i approve", "why cant i approve", "check whether", "has already been approved",
            "has been approved", "is already approved", "approval history", "who approved"
        ]):
            return True

        has_specific_risk = bool(re.search(r'\b(?:RSK-[A-Z0-9_-]+-\d+|[A-Z]{2,5}-\d{2,5}|RSK-\d+)\b', msg, re.IGNORECASE)) or bool(re.search(r'\brisk\s+\d+\b', lower))

        has_action_verb = any(w in lower for w in [
            "approve", "approval", "reject", "rejection", "sign off", "signoff", "sign-off",
            "return risk", "return for revision", "don't approve", "dont approve"
        ])

        if has_action_verb and has_specific_risk:
            return True

        if any(lower.startswith(w) for w in [
            "approve", "reject", "sign off", "signoff", "sign-off",
            "please approve", "please reject", "i approve", "i reject",
            "i want to approve", "i want to reject", "i would like to approve", "i would like to reject",
            "confirm approve", "confirm approval", "confirm reject", "confirm rejection"
        ]):
            return True

        return False

    def is_cancellation(self, msg: str) -> bool:
        """Detect cancellation intent."""
        return is_user_cancelling(msg)

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
                response="❌ **Authentication Failure:** No authenticated user detected. Governance sign-off requires user identity.",
                metadata={"intent": "AUTH_FAILURE"}
            )

        raw_role = getattr(request, "user_role", None) or (request.metadata or {}).get("role")
        if not raw_role or not str(raw_role).strip():
            return AgentResponse(
                request_id=req_id,
                agent_id=self.agent_id,
                status="error",
                success=False,
                response="❌ **Authorization Failure:** No authenticated role detected. Governance actions require a valid assigned role.",
                metadata={"intent": "ROLE_MISSING"}
            )
        user_role = str(raw_role).strip()
        dept_id = (request.metadata or {}).get("dept_id")
        dept_name = (request.metadata or {}).get("dept_name")

        # 2. Session Loading or Initialization
        session = self.get_session(session_key)
        extracted = extract_goal_and_inputs(msg, current_goal=session.goal if session else None)

        # Check if user is starting a brand new command with a new risk_id, new action, or while previous was terminal
        if not session or session.is_terminal or (extracted.risk_id and session.risk_id and extracted.risk_id != session.risk_id) or (extracted.action and session.action and extracted.action != session.action):
            session = ApprovalWorkflowSession(
                session_id=session_key,
                user_id=str(auth_uid),
                user_role=user_role,
                dept_id=dept_id,
                dept_name=dept_name,
                goal=extracted.goal or ApprovalGoal.UNKNOWN,
                state=ApprovalWorkflowState.INITIATION,
                risk_id=extracted.risk_id,
                action=extracted.action,
                remark=extracted.remark,
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

            # Update extracted values if present
            if extracted.goal and session.state not in (ApprovalWorkflowState.AWAITING_CONFIRMATION, ApprovalWorkflowState.AWAITING_REMARK):
                session.goal = extracted.goal
            if extracted.risk_id:
                session.risk_id = extracted.risk_id
            if extracted.action:
                session.action = extracted.action
            if extracted.remark:
                session.remark = extracted.remark

            # Special case: multi-turn input while waiting for remark
            if session.state == ApprovalWorkflowState.AWAITING_REMARK and not extracted.is_cancellation:
                chosen_remark = extracted.remark or msg
                chosen_remark = re.sub(r'\[btn.*?\]', '', chosen_remark).strip()
                if len(chosen_remark) >= 2:
                    session.remark = chosen_remark

        session.step_count += 1

        # 3. Dynamic Bounded Execution Loop (max 4 tool/decision iterations per turn)
        iterations = 0
        final_response_text = ""
        final_intent = "APPROVAL_PROCESSING"
        is_success = True

        while iterations < 4:
            iterations += 1
            plan = ApprovalWorkflowPlanner.plan_next_action(
                session=session,
                is_confirmation=extracted.is_confirmation,
                is_cancellation=extracted.is_cancellation,
            )

            # --- A. CANCELLATION ---
            if plan.action_type == ApprovalActionType.CANCEL_SESSION:
                if session.pending_confirmation:
                    session.pending_confirmation["status"] = "CANCELLED"
                session.state = ApprovalWorkflowState.CANCELLED
                final_response_text = format_cancellation_response(session.risk_id)
                final_intent = "APPROVAL_CANCELLED"
                self.clear_session(session_key)
                break

            # --- B. REQUEST MISSING INPUT ---
            elif plan.action_type == ApprovalActionType.REQUEST_MISSING_INPUT:
                if plan.missing_field == "risk_id":
                    session.state = ApprovalWorkflowState.AWAITING_RISK_ID
                    final_response_text = format_missing_risk_id_prompt(session.action)
                    final_intent = "AWAITING_RISK_ID"
                elif plan.missing_field == "remark":
                    session.state = ApprovalWorkflowState.AWAITING_REMARK
                    final_response_text = format_missing_remark_prompt(session.risk_id or "Risk", session.action or "reject")
                    final_intent = "AWAITING_REMARK"
                elif plan.missing_field == "action":
                    session.state = ApprovalWorkflowState.AWAITING_ACTION
                    final_response_text = format_missing_action_prompt(session.risk_id or "Risk")
                    final_intent = "AWAITING_ACTION"
                else:
                    final_response_text = "How can I assist with your risk governance approvals today?"
                    final_intent = "APPROVAL_HELP"
                break

            # --- C. FETCH PENDING APPROVALS TOOL ---
            elif plan.action_type == ApprovalActionType.FETCH_PENDING_APPROVALS:
                try:
                    queue_items = fetch_pending_approvals(session)
                    session.pending_queue_data = queue_items
                    # Continue loop to format and complete
                    continue
                except Exception as e:
                    logger.error(f"Error fetching pending approvals: {e}")
                    final_response_text = f"⚠️ Could not retrieve pending approvals: {e}"
                    final_intent = "QUEUE_FETCH_ERROR"
                    is_success = False
                    break

            # --- D. FETCH RISK DETAILS TOOL ---
            elif plan.action_type == ApprovalActionType.FETCH_RISK_DETAILS:
                try:
                    risk = fetch_risk_details(session, session.risk_id)
                    if not risk:
                        final_response_text = f"❌ Risk record **{session.risk_id}** was not found in the Enterprise Risk Register."
                        final_intent = "RISK_NOT_FOUND"
                        session.state = ApprovalWorkflowState.FAILED
                        break
                    session.risk_data = risk
                    session.risk_register_id = risk.get("risk_register_id")
                    # Continue loop to evaluate next step
                    continue
                except Exception as e:
                    logger.error(f"Error fetching risk details: {e}")
                    final_response_text = f"⚠️ Could not load details for risk **{session.risk_id}**: {e}"
                    final_intent = "DETAILS_FETCH_ERROR"
                    is_success = False
                    break

            # --- E. FETCH AUDIT TRAIL TOOL ---
            elif plan.action_type == ApprovalActionType.FETCH_AUDIT_TRAIL:
                try:
                    trail = fetch_risk_audit_trail(session, session.risk_id)
                    if not trail:
                        final_response_text = f"❌ No audit history found for risk **{session.risk_id}**."
                        final_intent = "AUDIT_NOT_FOUND"
                        session.state = ApprovalWorkflowState.FAILED
                        break
                    session.audit_trail_data = trail
                    # Continue loop to format and complete
                    continue
                except Exception as e:
                    logger.error(f"Error fetching audit trail: {e}")
                    final_response_text = f"⚠️ Could not load audit history for **{session.risk_id}**: {e}"
                    final_intent = "AUDIT_FETCH_ERROR"
                    is_success = False
                    break

            # --- F. REPORT POLICY BLOCK ---
            elif plan.action_type == ApprovalActionType.REPORT_POLICY_BLOCK:
                session.state = ApprovalWorkflowState.POLICY_BLOCKED
                session.policy_block_reason = plan.policy_reason
                final_response_text = format_policy_block_response(plan.policy_reason or "Policy block.", session.risk_id)
                final_intent = "APPROVAL_POLICY_BLOCKED"
                is_success = False
                break

            # --- G. VALIDATE AND PREVIEW (AWAITING CONFIRMATION) ---
            elif plan.action_type == ApprovalActionType.VALIDATE_AND_PREVIEW:
                # Preconditions validated; prepare confirmation preview
                action_name = session.action or ("approve" if session.goal == ApprovalGoal.APPROVE_RISK else "reject")
                remark_val = session.remark or ("Approved via ERM Copilot" if action_name == "approve" else "")
                stage_name = plan.validation_result.stage_name if plan.validation_result else None
                risk_title = session.risk_data.get("risk_name") if session.risk_data else None

                bind_pending_confirmation(
                    session=session,
                    action=action_name,
                    risk_id=session.risk_id,
                    remark=remark_val
                )
                final_response_text = format_confirmation_prompt(
                    risk_id=session.risk_id,
                    action=action_name,
                    remark=session.remark,
                    stage_name=stage_name,
                    risk_title=risk_title
                )
                final_intent = "AWAITING_CONFIRMATION"
                break

            # --- H. EXECUTE MUTATION ---
            elif plan.action_type == ApprovalActionType.EXECUTE_MUTATION:
                success, result_dict, err = execute_confirmed_decision(session)
                session.api_result = result_dict
                if success:
                    session.state = ApprovalWorkflowState.COMPLETED
                    final_response_text = format_success_response(result_dict)
                    final_intent = "APPROVAL_EXECUTED" if session.action == "approve" else "REJECTION_EXECUTED"
                    self.clear_session(session_key)
                else:
                    session.state = ApprovalWorkflowState.FAILED
                    final_response_text = f"❌ **Approval Execution Failed:** {err}"
                    final_intent = "APPROVAL_FAILED"
                    is_success = False
                break

            # --- I. RESPOND AND COMPLETE ---
            elif plan.action_type == ApprovalActionType.RESPOND_AND_COMPLETE:
                goal = session.goal
                if goal == ApprovalGoal.SHOW_PENDING_APPROVALS:
                    final_response_text = format_pending_approvals_response(
                        items=session.pending_queue_data or [],
                        user_role=session.user_role,
                        dept_name=session.dept_name,
                    )
                    final_intent = "PENDING_APPROVALS_SHOWN"
                elif goal == ApprovalGoal.SHOW_RISK_DETAILS:
                    final_response_text = format_risk_details_response(session.risk_data or {})
                    final_intent = "RISK_DETAILS_SHOWN"
                elif goal == ApprovalGoal.SHOW_AUDIT_TRAIL:
                    final_response_text = format_audit_trail_response(session.audit_trail_data or {})
                    final_intent = "AUDIT_TRAIL_SHOWN"
                elif goal == ApprovalGoal.CHECK_STATUS:
                    final_response_text = format_status_check_response(
                        risk=session.risk_data or {},
                        val_res=plan.validation_result,
                        user_role=session.user_role,
                    )
                    final_intent = "STATUS_EVALUATED"

                session.state = ApprovalWorkflowState.COMPLETED
                self.clear_session(session_key)
                break

            # --- J. FAIL SAFELY ---
            elif plan.action_type == ApprovalActionType.FAIL_SAFELY:
                session.state = ApprovalWorkflowState.FAILED
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
                    status = WorkflowStatus.COMPLETED if session.state == ApprovalWorkflowState.COMPLETED else WorkflowStatus.CANCELLED
                    active_wf.transition_to(status, step=session.state.value)
                    workflow_checkpointer.save(active_wf)
            else:
                if not active_wf:
                    active_wf = AgentWorkflowState(
                        session_id=session_key,
                        workflow_type=WorkflowType.APPROVAL_GOVERNANCE,
                        owner_user_id=str(auth_uid),
                        owner_role=user_role,
                        dept_id=dept_id,
                        dept_name=dept_name,
                        current_agent=self.agent_id,
                        current_step=session.state.value,
                        risk_id=session.risk_id,
                        collected_fields=session.to_dict(),
                    )
                else:
                    active_wf.current_step = session.state.value
                    active_wf.risk_id = session.risk_id or active_wf.risk_id
                    active_wf.collected_fields = session.to_dict()
                    active_wf.step_count += 1
                    if session.state == ApprovalWorkflowState.AWAITING_CONFIRMATION:
                        active_wf.transition_to(WorkflowStatus.WAITING_FOR_CONFIRMATION, step="AWAITING_CONFIRMATION")
                workflow_checkpointer.save(active_wf)
        except Exception as cp_err:
            logger.debug(f"[CHECKPOINT_SAVE_ERROR] in ApprovalWorkflowAgent: {cp_err}")

        return AgentResponse(
            request_id=req_id,
            agent_id=self.agent_id,
            status="success" if is_success else "error",
            success=is_success,
            response=final_response_text or "Approval processing update.",
            metadata={
                "intent": final_intent,
                "risk_id": session.risk_id,
                "action": session.action,
                "goal": session.goal.value if session.goal else None,
                "state": session.state.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )


# Singleton instance
approval_workflow_agent = ApprovalWorkflowAgent()
