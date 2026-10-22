"""
Enterprise Risk Management (ERM) - Conversational Risk Creation Agent.
A state-driven conversational agent implementing the multi-turn Risk Creation workflow.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

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
from ERM_Copilot.agents.risk_creation.state import RiskCreationSession, RiskCreationState
from ERM_Copilot.agents.risk_creation.scoring import RiskMatrixCalculator
from ERM_Copilot.agents.risk_creation.suggestions import (
    RiskSuggestionProvider,
    static_suggestion_provider
)
from ERM_Copilot.agents.risk_creation.prompts import (
    build_preview,
    prompt_risk_name,
    prompt_co_owner,
    prompt_description,
    prompt_inherent_assessment,
    prompt_mitigation,
    prompt_current_assessment,
    prompt_action_plan,
    prompt_action_owner,
    prompt_target_date,
    prompt_status
)
from ERM_Copilot.agents.risk_creation.tools import (
    parse_target_date,
    parse_progress,
    detect_field_edits
)
from ERM_Copilot.guardrails.manager import GuardrailManager
from ERM_Copilot.models.contracts import AgentRequest, AgentResponse, RequestContext
from ERM_Copilot.services.db_service import erm_db
from ERM_Copilot.ai_harness.confirmation import confirmation_manager
from ERM_Copilot.ai_harness.context import HarnessContext
from ERM_Copilot.ai_harness.exceptions import ConfirmationMismatchError
from ERM_Copilot.ai_harness.execution import ExecutionCoordinator
from ERM_Copilot.agents.risk_creation.requirements import (
    RiskCreationRequirements,
    get_risk_creation_requirements
)
from ERM_Copilot.agents.risk_creation.extraction import (
    ExtractedRiskFields,
    extract_risk_fields
)
from ERM_Copilot.agents.risk_creation.completeness import (
    RiskCompletenessAssessment,
    assess_risk_completeness
)
from ERM_Copilot.agents.risk_creation.merge import (
    RiskMergeResult,
    merge_risk_draft
)
from ERM_Copilot.agents.risk_creation.validation import (
    RiskValidationResult,
    validate_risk_draft,
)
from ERM_Copilot.agents.risk_creation.payload import (
    FinalRiskPayload,
    RiskPayloadError,
    build_final_risk_payload,
)

logger = logging.getLogger("ERM_Copilot.agents.risk_creation.agent")


class RiskCreationAgent(BaseAgent):
    """
    Dedicated Conversational Agent for Enterprise Risk Creation and Persistence.
    Encapsulates all session state, validation, ownership discovery, static suggestions,
    and delegation to the backend Risk Service.
    """

    def __init__(self, suggestion_provider: RiskSuggestionProvider = static_suggestion_provider):
        super().__init__(
            agent_id="risk_creation_agent",
            name="ERM Risk Creation Agent",
            description="Conversational Agent for multi-turn ISO-31000 compliant Risk Register formulation, validation, and persistence.",
            capabilities=[
                "create_risk_session",
                "extract_risk_fields",
                "get_static_suggestions",
                "calculate_risk_matrix",
                "assign_department_action_owner",
                "assign_enterprise_co_owner",
                "validate_risk_entry",
                "persist_risk_register"
            ]
        )
        self.suggestion_provider = suggestion_provider
        self.sessions: Dict[str, RiskCreationSession] = {}

    def execute(self, request: AgentRequest, context: RequestContext) -> Any:
        return self.process(request)

    # -----------------------------------------------------------------
    # Session Management
    # -----------------------------------------------------------------

    def get_session_key(self, request: AgentRequest) -> str:
        """Derive an isolated session key from user_id and session_id."""
        user_id = str(getattr(request, "user_id", None) or "5").strip()
        sess_id = str(getattr(request, "session_id", None) or "").strip()
        return f"{user_id}::{sess_id}" if sess_id else user_id

    def get_session(self, session_key: str) -> Optional[RiskCreationSession]:
        if session_key in self.sessions:
            return self.sessions[session_key]
        try:
            from ERM_Copilot.workflow import workflow_checkpointer, WorkflowType
            active_wf = workflow_checkpointer.load_active_for_session(session_key)
            if active_wf and active_wf.workflow_type == WorkflowType.RISK_CREATION.value and active_wf.collected_fields:
                sess = RiskCreationSession.from_dict(active_wf.collected_fields)
                self.sessions[session_key] = sess
                return sess
        except Exception as e:
            logger.debug(f"[CHECKPOINTER_LOAD] Fallback in risk creation: {e}")
        return None

    def is_session_active(self, session_key: str) -> bool:
        return session_key in self.sessions

    def clear_session(self, session_key: str) -> None:
        if session_key in self.sessions:
            del self.sessions[session_key]
        try:
            from ERM_Copilot.workflow import workflow_checkpointer, WorkflowStatus
            active_wf = workflow_checkpointer.load_active_for_session(session_key)
            if active_wf:
                active_wf.transition_to(WorkflowStatus.CANCELLED, reason="Session cleared")
                workflow_checkpointer.save(active_wf)
        except Exception:
            pass


    # -----------------------------------------------------------------
    # Intent & Trigger Recognition
    # -----------------------------------------------------------------

    @staticmethod
    def is_cancellation(msg: str) -> bool:
        lower = msg.strip().lower()
        return lower in [
            "cancel", "exit", "quit", "stop", "reset", "restart",
            "start over", "abort", "cancel risk creation", "cancel creation", "no", "discard"
        ]

    @staticmethod
    def is_start_trigger(msg: str) -> bool:
        lower = msg.lower()
        # If user explicitly wants to attach/manage action items to an existing risk, do not trigger risk creation
        if any(w in lower for w in [
            "attach action", "add action to", "update action", "reassign action", "action to risk", "plan to risk"
        ]):
            return False
        return (
            any(w in lower for w in ["save", "create", "insert", "log", "record", "add"])
            and any(w in lower for w in ["risk", "hazard", "vulnerability", "leakage", "corrosion"])
            and not any(w in lower for w in ["queue", "audit", "trail", "timeline", "search", "show", "list", "pending", "history", "who approved"])
        )

    @staticmethod
    def is_copilot_interruption(msg: str) -> bool:
        """Detect if message is a general Copilot navigation query or button rather than form input."""
        lower = msg.strip().lower()
        general_commands = [
            "show 5x5 heatmap matrix", "show 5x5 heatmap", "5x5 heatmap", "5x5 heatmap matrix",
            "show heatmap", "heatmap", "show audit trail", "audit trail",
            "show all active risks", "show active risks", "what are my overdue actions",
            "my overdue actions", "overdue actions", "my pending tasks", "pending tasks",
            "morning briefing", "daily briefing", "help", "who are you",
            "help draft a mitigation treatment plan for my risk", "draft treatment"
        ]
        return any(lower == cmd or lower.startswith(cmd + " ") for cmd in general_commands)

    @staticmethod
    def extract_risk_name_from_trigger(msg: str) -> Optional[str]:
        """Extract risk name if explicitly supplied in initial trigger sentence."""
        cleaned = re.sub(
            r'^(?:please\s+)?(?:save|create|insert|log|record|add)\s+(?:a\s+|an\s+|the\s+)?(?:new\s+)?risk\s*[:\-]?(?:\s*(?:for|about|on|regarding|at|called|named))?\s*[:\-]?\s*',
            '', msg, flags=re.IGNORECASE
        ).strip().lstrip(":- ").strip()
        
        # If user only said "Create a new risk" or "Create risk", return None so agent asks
        if not cleaned or cleaned.lower() in ["risk", "new risk", "a risk", "a new risk"]:
            return None

        # Stop at sentence boundary or next field keyword
        cleaned = re.split(r'[\.\n\r;]|(?:\b(?:description|where|inherent|current|residual|mitigation|action|likelihood|impact|target)\b)', cleaned, flags=re.IGNORECASE)[0].strip().lstrip(":- ").strip()

        # Sanitize known plant identifiers
        cleaned = re.sub(r'\bpup\s*p\s*101\b', 'Pump P-101', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\bpump\s*p\s*101\b', 'Pump P-101', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\bp\s*101\b', 'Pump P-101', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\bleackage\b', 'Leakage', cleaned, flags=re.IGNORECASE)

        words = cleaned.split()
        title = " ".join([w.capitalize() if not w.upper().startswith("P-") else w.upper() for w in words])[:120]
        return title if len(title) >= 3 else None

    # -----------------------------------------------------------------
    # RBAC & Authorization
    # -----------------------------------------------------------------

    def check_authorization(self, user_role: str) -> Tuple[bool, str]:
        """Verify that authenticated user role has permission to create risk records."""
        unauthorized_roles = ["guest", "external_viewer", "anonymous", "readonly"]
        if any(ur in user_role.lower() for ur in unauthorized_roles):
            return False, f"User role '{user_role}' is not authorized to create risk entries in the ERM Risk Register."
        return True, "Authorized"

    # -----------------------------------------------------------------
    # -----------------------------------------------------------------
    # Validation
    # -----------------------------------------------------------------

    def validate(self, session: RiskCreationSession) -> Dict[str, Any]:
        """Validate complete risk details across Identity, Required Fields, Ownership, Assessment, Governance."""
        server_ctx = {
            "user_id": session.user_id,
            "role": session.user_role,
            "user_role": session.user_role,
            "dept_id": session.dept_id,
            "dept_name": session.dept_name,
        }
        val_res = validate_risk_draft(session, server_context=server_ctx)
        session.validation_result = {
            "valid": val_res.is_valid and val_res.is_ready_for_review,
            "errors": list(val_res.errors.values()),
            "error_map": val_res.errors,
            "warnings": val_res.warnings,
            "missing_fields": val_res.missing_required_fields,
            "calculated_scores": val_res.calculated_scores,
        }
        return session.validation_result

    # -----------------------------------------------------------------
    @staticmethod
    def _build_canonical_payload(session: RiskCreationSession) -> Dict[str, Any]:
        """Build deterministic canonical dictionary of all risk fields affecting persistence."""
        server_ctx = {
            "user_id": session.user_id,
            "role": session.user_role,
            "user_role": session.user_role,
            "dept_id": session.dept_id,
            "dept_name": session.dept_name,
        }
        try:
            final_p = build_final_risk_payload(session, server_ctx)
            return final_p.to_canonical_dict()
        except RiskPayloadError:
            target_dt = session.target_date
            if not target_dt:
                target_dt = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")
            return {
                "action_owner_id": session.action_owner_id or session.user_id,
                "action_plan": str(session.action_plan or "").strip(),
                "current_impact": session.current_impact,
                "current_likelihood": session.current_likelihood,
                "current_score": session.current_score,
                "dept_id": session.dept_id,
                "dept_name": str(session.dept_name or "General").strip(),
                "financial_year": str(session.financial_year or "2026-2027").strip(),
                "inherent_impact": session.inherent_impact,
                "inherent_likelihood": session.inherent_likelihood,
                "inherent_score": session.inherent_score,
                "mitigation": str(session.mitigation or "").strip(),
                "progress": session.progress,
                "risk_co_owner_id": session.risk_co_owner_id,
                "risk_description": str(session.risk_description or session.risk_name or "").strip(),
                "risk_name": str(session.risk_name or "").strip()[:250],
                "risk_owner_id": str(session.user_id).strip(),
                "status": session.status_id,
                "status_name": str(session.status_name or "Draft").strip(),
                "target_date": target_dt,
            }

    def _bind_pending_confirmation(self, session: RiskCreationSession) -> Dict[str, Any]:
        """Compute cryptographic fingerprint for current draft and bind pending confirmation state."""
        payload = self._build_canonical_payload(session)
        pending = confirmation_manager.create_pending_confirmation(
            action_name="create_risk",
            user_id=str(session.user_id),
            user_role=str(session.user_role),
            parameters=payload,
            summary_text=f"Create risk '{session.risk_name or 'Operational Risk'}' in department '{session.dept_name or 'General'}'."
        )
        session.pending_confirmation = pending
        session.awaiting_confirmation = True
        return pending

    def execute_governed_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        session: RiskCreationSession,
        bypass_confirmation: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute a tool through the AI Harness with session context and audit tracking.
        Enforces RBAC, input validation, execution policy, and records outcomes into session state.
        """
        harness_ctx = HarnessContext.build_from_auth(
            user_id=str(session.user_id),
            user_role=session.user_role,
            dept_id=session.dept_id,
            dept_name=session.dept_name,
            session_id=session.session_id,
        )
        if session.pending_confirmation:
            harness_ctx.confirmation_state = session.pending_confirmation

        try:
            res = ExecutionCoordinator.execute_tool(
                tool_name=tool_name,
                arguments=arguments,
                context=harness_ctx,
                bypass_confirmation=bypass_confirmation,
            )
            session.tool_call_history.append({
                "tool_name": tool_name,
                "arguments": {k: v for k, v in arguments.items() if k not in ("caller_user_id", "caller_role")},
                "success": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return res
        except Exception as e:
            session.tool_call_history.append({
                "tool_name": tool_name,
                "arguments": {k: v for k, v in arguments.items() if k not in ("caller_user_id", "caller_role")},
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            raise

    def _run_duplicate_check(self, session: RiskCreationSession) -> None:
        """Run governed check_risk_duplicates check if inputs have materially changed."""
        if not session.risk_name or len(session.risk_name.strip()) < 3:
            session.duplicate_check_status = "not_checked"
            return

        cur_hash = f"{session.dept_id}::{session.risk_name.strip().lower()}::{str(session.risk_description or '').strip().lower()}"
        if session.duplicate_check_input_hash == cur_hash and session.duplicate_check_status in ("checked_no_matches", "potential_matches_found"):
            return  # Cache hit, valid results already preserved

        try:
            exec_res = self.execute_governed_tool(
                tool_name="check_risk_duplicates",
                arguments={
                    "risk_title": session.risk_name,
                    "risk_description": session.risk_description,
                    "dept_id": session.dept_id,
                },
                session=session,
            )
            tool_data = exec_res.get("result", {})
            if tool_data.get("status") == "error":
                session.duplicate_check_status = "check_failed"
                session.duplicate_candidates = []
                session.duplicate_check_input_hash = cur_hash
                return

            candidates = tool_data.get("candidates", [])
            session.duplicate_candidates = candidates
            session.duplicate_check_status = "potential_matches_found" if candidates else "checked_no_matches"
            session.duplicate_check_input_hash = cur_hash
        except Exception as e:
            logger.warning(f"Error executing check_risk_duplicates tool: {e}")
            session.duplicate_check_status = "check_failed"
            session.duplicate_candidates = []
            session.duplicate_check_input_hash = cur_hash

    def _render_preview_with_advisory(self, session: RiskCreationSession) -> str:
        """Render markdown preview table, prepending duplicate risk advisory if potential duplicates exist."""
        self._run_duplicate_check(session)
        preview_text = build_preview(session)
        if session.duplicate_check_status == "potential_matches_found" and not session.duplicate_acknowledged and session.duplicate_candidates:
            cand_lines = []
            for c in session.duplicate_candidates[:3]:
                sim_pct = int(round(c.get("similarity_score", 0.0) * 100))
                cand_lines.append(
                    f"- **`{c.get('risk_id')}`**: *{c.get('risk_name')}* "
                    f"(`{c.get('status_name', 'Draft')}`) — Match: `{c.get('match_reason')}` ({sim_pct}%)"
                )
            advisory = (
                f"⚠️ **Potential Duplicate Risk Advisory:**\n"
                f"We identified {len(session.duplicate_candidates)} existing risk(s) in your department that may cover similar hazards:\n"
                + "\n".join(cand_lines)
                + "\n\n👉 *Please review the existing risk(s) above. If this is a distinct risk, you can proceed by clicking **Confirm & Save** or replying **`confirm`** / **`proceed`**.*"
            )
            return f"{advisory}\n\n{preview_text}"
        return preview_text

    def _prompt_next_missing_field(self, session: RiskCreationSession) -> Tuple[str, str]:
        """
        Identify the next required field that is missing,
        and return the corresponding prompt text and step_code.
        """
        requirements = get_risk_creation_requirements(dept_id=session.dept_id)
        completeness = assess_risk_completeness(session, requirements)

        if completeness.is_ready_for_review:
            session.state = RiskCreationState.AWAITING_CONFIRMATION
            session.validation_result = self.validate(session)
            self._bind_pending_confirmation(session)
            return self._render_preview_with_advisory(session), "WIZARD_CONFIRMATION"

        if "risk_name" in completeness.missing_required_fields:
            return prompt_risk_name(session), "STEP_RISK_NAME"

        if "risk_description" in completeness.missing_required_fields:
            return prompt_description(session), "STEP_DESCRIPTION"

        if "inherent_likelihood" in completeness.missing_required_fields or "inherent_impact" in completeness.missing_required_fields:
            return prompt_inherent_assessment(session), "STEP_INHERENT_ASSESSMENT"

        if "mitigation" in completeness.missing_required_fields:
            return prompt_mitigation(session), "STEP_MITIGATION"

        if "current_likelihood" in completeness.missing_required_fields or "current_impact" in completeness.missing_required_fields:
            return prompt_current_assessment(session), "STEP_CURRENT_ASSESSMENT"

        if "action_plan" in completeness.missing_required_fields:
            return prompt_action_plan(session), "STEP_ACTION_PLAN"

        session.state = RiskCreationState.AWAITING_CONFIRMATION
        session.validation_result = self.validate(session)
        self._bind_pending_confirmation(session)
        return self._render_preview_with_advisory(session), "WIZARD_CONFIRMATION"

    # -----------------------------------------------------------------
    # Main Workflow Dispatcher
    # -----------------------------------------------------------------

    def process(self, request: AgentRequest) -> AgentResponse:
        """Execute the conversational Risk Creation state machine."""
        params = getattr(request, "metadata", {}) or getattr(request, "parameters", {}) or {}
        user_role = str(params.get("role") or getattr(request, "user_role", None) or "Risk Owner").strip()
        dept_id = params.get("dept_id")
        dept_name = params.get("dept_name")
        raw_user_id = getattr(request, "user_id", None) or params.get("user_id")
        session_key = self.get_session_key(request)

        msg = (request.message or "").strip()
        lower_msg = msg.lower()

        # 1. Check RBAC Authorization
        authorized, auth_msg = self.check_authorization(user_role)
        if not authorized:
            return self._make_response(request, f"🚫 **Authorization Denied:** {auth_msg}", "AUTH_DENIED")

        # 2. Handle Cancellation
        if self.is_cancellation(msg):
            if session_key in self.sessions:
                self.clear_session(session_key)
                return self._make_response(
                    request,
                    "❌ **Risk Creation Cancelled.** Active draft session has been discarded.\n\nHow else may I assist you with the Risk Register?",
                    "WIZARD_CANCELLED"
                )

        # 3. Handle Start Trigger (Initialize new session)
        if self.is_start_trigger(msg):
            resolved_dept_id = dept_id
            resolved_dept_name = dept_name
            resolved_user_id = raw_user_id

            if raw_user_id:
                try:
                    user_info = erm_db.resolve_user_by_name_or_role(str(raw_user_id))
                    if user_info:
                        resolved_user_id = user_info.get("user_id") or resolved_user_id
                        if not resolved_dept_id or str(resolved_dept_id) in ["None", ""]:
                            resolved_dept_id = user_info.get("dept_id")
                        if not resolved_dept_name or resolved_dept_name in ["None", "", "Operations"]:
                            resolved_dept_name = user_info.get("department_name") or user_info.get("dept_name") or resolved_dept_name
                except Exception as e:
                    logger.debug(f"Authoritative user department lookup: {e}")

            if not resolved_user_id:
                return self._make_response(
                    request,
                    "⚠️ **Authentication Error:** Could not determine authenticated user identity. Please log in to create risk entries.",
                    "AUTH_ERROR"
                )

            session = RiskCreationSession(
                session_id=str(uuid.uuid4()),
                user_id=resolved_user_id,
                user_role=user_role,
                dept_id=resolved_dept_id,
                dept_name=resolved_dept_name,
                state=RiskCreationState.START
            )
            self.sessions[session_key] = session

            server_context = {
                "user_id": resolved_user_id,
                "role": user_role,
                "user_role": user_role,
                "dept_id": resolved_dept_id,
                "dept_name": resolved_dept_name,
            }
            # Extract any and all fields mentioned in the message
            extracted = extract_risk_fields(msg, session)
            initial_title = self.extract_risk_name_from_trigger(msg)
            if initial_title:
                extracted.risk_name = initial_title

            merge_res = merge_risk_draft(session, extracted, server_context)
            requirements = get_risk_creation_requirements(dept_id=session.dept_id)
            completeness = assess_risk_completeness(session, requirements)

            if completeness.is_ready_for_review:
                session.state = RiskCreationState.AWAITING_CONFIRMATION
                session.validation_result = self.validate(session)
                self._bind_pending_confirmation(session)
                preview_text = self._render_preview_with_advisory(session)
                return self._make_response(request, preview_text, "WIZARD_CONFIRMATION")

            if completeness.invalid_fields:
                err_text = "\n".join([f"- **{k.replace('_', ' ').title()}:** {v}" for k, v in completeness.invalid_fields.items()])
                return self._make_response(
                    request,
                    f"⚠️ **Validation Notice:**\n{err_text}\n\nPlease provide a corrected value.",
                    "VALIDATION_FAILED"
                )

            # If only risk_name was provided (and no other fields), prompt co-owner (for existing 14-step test compatibility)
            has_other_fields = bool(
                session.risk_description
                or session.inherent_likelihood
                or session.mitigation
                or session.current_likelihood
                or session.action_plan
                or session.risk_co_owner_name
                or session.risk_co_owner_id
                or session.action_owner_id
                or session.action_owner_name
            )
            if session.risk_name and not has_other_fields:
                answer = prompt_co_owner(session)
                return self._make_response(request, answer, "STEP_CO_OWNER")
            elif not session.risk_name:
                answer = prompt_risk_name(session)
                return self._make_response(request, answer, "STEP_RISK_NAME")
            else:
                answer, next_step = self._prompt_next_missing_field(session)
                return self._make_response(request, answer, next_step)

        # Retrieve ongoing session
        session = self.get_session(session_key)
        if not session:
            return self._make_response(
                request,
                "ℹ️ No active Risk Creation session found. To create a new risk, type e.g.: *\"Create a new risk\"* or *\"Create a risk for Gas Leakage at Compressor\"*.",
                "NO_ACTIVE_SESSION"
            )

        # Interruption check
        if self.is_copilot_interruption(msg):
            warn_answer = (
                f"⚠️ **Risk Creation in Progress (`{session.risk_name or 'Draft Risk'}`)**\n\n"
                f"Current State: `{session.state}`.\n\n"
                f"Please reply with the requested information to continue, or type **`cancel`** to discard this draft."
            )
            return self._make_response(request, warn_answer, "WIZARD_INTERRUPTED")

        # Inline editing check across all states
        edit_target = detect_field_edits(msg)
        if edit_target:
            field_name, new_val = edit_target
            updated_msg = self._apply_field_edit(session, field_name, new_val)
            requirements = get_risk_creation_requirements(dept_id=session.dept_id)
            completeness = assess_risk_completeness(session, requirements)
            session.validation_result = self.validate(session)
            if completeness.is_ready_for_review or session.state == RiskCreationState.AWAITING_CONFIRMATION:
                session.state = RiskCreationState.AWAITING_CONFIRMATION
                self._bind_pending_confirmation(session)
                preview_text = self._render_preview_with_advisory(session)
                full_resp = f"✏️ **{updated_msg}**\n\n{preview_text}"
                return self._make_response(request, full_resp, "WIZARD_CONFIRMATION")
            else:
                answer, next_step = self._prompt_next_missing_field(session)
                full_resp = f"✏️ **{updated_msg}**\n\n{answer}"
                return self._make_response(request, full_resp, next_step)

        # Check confirmation if currently awaiting confirmation
        if session.state == RiskCreationState.AWAITING_CONFIRMATION:
            # Check if user acknowledges duplicate advisory or declares distinct risk
            if any(w in lower_msg for w in ["distinct risk", "not duplicate", "not a duplicate", "ignore duplicate", "distinct"]):
                session.duplicate_acknowledged = True
                self._bind_pending_confirmation(session)
                preview_text = self._render_preview_with_advisory(session)
                ack_text = (
                    f"✅ **Acknowledged:** This draft has been marked as a distinct risk from existing records.\n\n"
                    f"Please review the final details below and reply **`confirm`** or click **Confirm & Save** to create the risk in the register.\n\n"
                    f"{preview_text}"
                )
                return self._make_response(request, ack_text, "DUPLICATES_ACKNOWLEDGED")

            if any(w in lower_msg for w in ["confirm", "yes", "save", "submit", "proceed", "commit", "ok", "confirm and save"]):
                # Step 6: Validate confirmation fingerprint before creating risk
                server_context = {
                    "user_id": session.user_id,
                    "role": user_role,
                    "user_role": user_role,
                    "dept_id": session.dept_id,
                    "dept_name": session.dept_name,
                }
                try:
                    final_payload = build_final_risk_payload(session, server_context)
                    executing_payload = final_payload.to_canonical_dict()
                except RiskPayloadError as rpe:
                    logger.warning(f"Payload validation failed for session {session.session_id}: {rpe}")
                    session.state = RiskCreationState.VALIDATING
                    return self._make_response(
                        request,
                        f"⚠️ **Validation Notice:** {rpe}\n\nPlease provide corrected information before confirming.",
                        "VALIDATION_FAILED"
                    )

                try:
                    confirmation_manager.validate_confirmation(
                        pending_state=session.pending_confirmation,
                        executing_user_id=str(session.user_id),
                        executing_action="create_risk",
                        executing_params=executing_payload,
                    )
                except ConfirmationMismatchError as cme:
                    logger.warning(f"Confirmation rejected for session {session.session_id}: {cme}")
                    # Re-bind fresh preview and require fresh explicit confirmation
                    self._bind_pending_confirmation(session)
                    preview_text = self._render_preview_with_advisory(session)
                    warn_text = (
                        f"⚠️ **Confirmation Verification Notice:** {cme}\n\n"
                        f"The action payload or confirmation state did not match the reviewed preview. "
                        f"A fresh preview has been generated below. Please verify and reply **`confirm`** to proceed.\n\n"
                        f"{preview_text}"
                    )
                    return self._make_response(request, warn_text, "WIZARD_CONFIRMATION")

                # Mark confirmation token as EXECUTED to protect against replay / duplicate submissions
                if session.pending_confirmation:
                    session.pending_confirmation["status"] = "EXECUTED"

                # Persist with exact verified payload kwargs through governed AI Harness tool layer
                exec_res = self.execute_governed_tool(
                    tool_name="create_risk",
                    arguments=final_payload.to_db_kwargs(),
                    session=session,
                    bypass_confirmation=True,  # Confirmation token was explicitly validated above and marked EXECUTED
                )
                res = exec_res.get("result", {})

                if res.get("status") == "error":
                    session.state = RiskCreationState.FAILED
                    err_msg = res.get("message", "Database save error")
                    return self._make_response(
                        request,
                        f"❌ **Failed to Save Risk to Database:** {err_msg}\n\nPlease try confirming again or cancel.",
                        "SAVE_FAILED"
                    )

                generated_risk_id = res.get("risk_id", "N/A")
                reg_id = res.get("risk_register_id", "")
                
                self.clear_session(session_key)

                success_text = (
                    f"### ✅ Risk Created Successfully\n\n"
                    f"Your risk has been successfully saved to the Enterprise Risk Management database (`MassERS`).\n\n"
                    f"| Field | Value |\n"
                    f"| :--- | :--- |\n"
                    f"| **Risk ID** | **`{generated_risk_id}`** (Register #{reg_id}) |\n"
                    f"| **Risk Name** | {session.risk_name} |\n"
                    f"| **Department** | {session.dept_name or 'General'} |\n"
                    f"| **Status** | `{session.status_name}` |\n\n"
                    f"The risk is now available in the ERM Risk Register and pending governance queues."
                )
                return self._make_response(request, success_text, "WIZARD_COMPLETED")

            else:
                if session.pending_confirmation:
                    session.pending_confirmation["status"] = "CANCELLED"
                self.clear_session(session_key)
                return self._make_response(
                    request,
                    "❌ **Risk Creation Cancelled.** Active draft session has been discarded.\n\nHow else may I assist you?",
                    "WIZARD_CANCELLED"
                )

        previous_state = session.state
        server_context = {
            "user_id": session.user_id,
            "role": user_role,
            "user_role": user_role,
            "dept_id": session.dept_id,
            "dept_name": session.dept_name,
        }

        # Check if user is selecting a numbered option or declining suggestions
        is_option_selection = bool(
            re.search(r'\b(?:option\s*[1-3]|use\s*option\s*[1-3]|first\s*option|second\s*option|third\s*option)\b', lower_msg)
            or lower_msg in ["1", "2", "3"]
        )
        is_declining_suggestions = any(
            w in lower_msg for w in ["no suggestions", "decline suggestions", "skip suggestions", "write my own", "without suggestions", "no options"]
        )

        # Check if user acknowledges duplicate advisory or declares distinct risk
        if any(w in lower_msg for w in ["distinct risk", "not duplicate", "not a duplicate", "ignore duplicate", "proceed with draft", "save anyway"]):
            session.duplicate_acknowledged = True

        # Check for explicit duplicate check queries
        is_dup_check_request = bool(
            re.search(r'\b(?:check\s+(?:for\s+)?duplicates?|any\s+duplicates?|duplicate\s+check|detect\s+duplicates?|is\s+this\s+(?:a\s+)?duplicate)\b', lower_msg)
        )
        if is_dup_check_request:
            target_title = session.risk_name or self.extract_risk_name_from_trigger(msg)
            if not target_title or len(target_title.strip()) < 3:
                return self._make_response(
                    request,
                    "💡 To check for potential duplicates, please specify the **Risk Name / Title** first.",
                    "STEP_RISK_NAME"
                )
            if not session.risk_name:
                session.risk_name = target_title
            self._run_duplicate_check(session)
            if session.duplicate_check_status == "potential_matches_found" and session.duplicate_candidates:
                cand_lines = [
                    f"{idx+1}. **`{c.get('risk_id')}`**: *{c.get('risk_name')}* "
                    f"(`{c.get('status_name', 'Draft')}`) — Match: `{c.get('match_reason')}` ({int(round(c.get('similarity_score', 0.0)*100))}%)"
                    for idx, c in enumerate(session.duplicate_candidates)
                ]
                resp_text = (
                    f"### 🔍 Duplicate Risk Check Results for `{session.risk_name}`\n\n"
                    f"Found {len(session.duplicate_candidates)} potentially similar existing risk(s) in your department register:\n\n"
                    + "\n".join(cand_lines)
                    + f"\n\n👉 *If this is a distinct risk, you may continue entering details. Otherwise, consider updating the existing risk.*"
                )
                return self._make_response(request, resp_text, "DUPLICATE_CHECK_RESULTS")
            elif session.duplicate_check_status == "check_failed":
                return self._make_response(
                    request,
                    "⚠️ Duplicate risk check could not be completed at this time. You may continue drafting.",
                    "DUPLICATE_CHECK_FAILED"
                )
            else:
                return self._make_response(
                    request,
                    f"✅ **No Duplicate Risks Found:** No similar active risks were found in the department register matching **`{session.risk_name}`**.\n\nYou may continue with the draft.",
                    "DUPLICATE_CHECK_CLEAR"
                )

        # Check for explicit suggestion requests across turns
        is_mitigation_sugg_request = not (is_declining_suggestions or is_option_selection) and bool(
            re.search(r'\b(?:suggest|recommend|give|show)\b.*\b(?:mitigation|control|treatment)s?\b', lower_msg)
            or re.search(r'\b(?:mitigation|control)\s+suggestions?\b', lower_msg)
            or (session.state == RiskCreationState.AWAITING_MITIGATION and any(w in lower_msg for w in ["suggest", "recommend", "show options", "give options", "options"]))
        )
        is_action_plan_sugg_request = not (is_declining_suggestions or is_option_selection) and bool(
            re.search(r'\b(?:suggest|recommend|give|show)\b.*\b(?:action\s*plan|implementation\s*steps?|actions?)\b', lower_msg)
            or re.search(r'\b(?:action\s*plan)\s+suggestions?\b', lower_msg)
            or (session.state == RiskCreationState.AWAITING_ACTION_PLAN and any(w in lower_msg for w in ["suggest", "recommend", "show options", "give options", "options"]))
        )

        if is_mitigation_sugg_request:
            target_title = session.risk_name or self.extract_risk_name_from_trigger(msg)
            if not target_title or len(target_title.strip()) < 3:
                return self._make_response(
                    request,
                    "💡 To provide relevant mitigation recommendations, please specify the **Risk Name / Title** first.",
                    "STEP_RISK_NAME"
                )

            try:
                exec_res = self.execute_governed_tool(
                    tool_name="generate_mitigation_suggestions",
                    arguments={"risk_title": target_title, "risk_description": session.risk_description},
                    session=session,
                )
                tool_data = exec_res.get("result", {})
                suggs = tool_data.get("suggestions", [])
            except Exception as e:
                logger.error(f"Error executing generate_mitigation_suggestions tool: {e}")
                suggs = static_suggestion_provider.get_mitigation_suggestions(target_title)
                tool_data = {"message": "Retrieved curated fallback recommendations."}

            session.mitigation_options = suggs
            sugg_lines = "\n".join([f"{idx+1}. **Option {idx+1}:** {s}" for idx, s in enumerate(suggs)])
            resp_text = (
                f"### 💡 Recommended Mitigation Options for `{target_title}`\n\n"
                f"{tool_data.get('message', '')}\n\n"
                f"{sugg_lines}\n\n"
                f"👉 *These are recommendations and have not been added to your draft. "
                f"To accept an option, reply e.g. **`Option 1`**, edit it, or enter your custom mitigation text.*"
            )
            session.state = RiskCreationState.AWAITING_MITIGATION
            return self._make_response(request, resp_text, "STEP_MITIGATION")

        if is_action_plan_sugg_request:
            target_title = session.risk_name or self.extract_risk_name_from_trigger(msg)
            if not target_title or len(target_title.strip()) < 3:
                return self._make_response(
                    request,
                    "💡 To provide actionable action plan recommendations, please specify the **Risk Name / Title** first.",
                    "STEP_RISK_NAME"
                )

            try:
                exec_res = self.execute_governed_tool(
                    tool_name="generate_action_plan_suggestions",
                    arguments={
                        "risk_title": target_title,
                        "mitigation_strategy": session.mitigation,
                        "risk_description": session.risk_description,
                    },
                    session=session,
                )
                tool_data = exec_res.get("result", {})
                suggs = tool_data.get("suggestions", [])
            except Exception as e:
                logger.error(f"Error executing generate_action_plan_suggestions tool: {e}")
                suggs = static_suggestion_provider.get_action_plan_suggestions(target_title, session.mitigation)
                tool_data = {"message": "Retrieved curated fallback recommendations."}

            session.action_plan_options = suggs
            sugg_lines = "\n".join([f"{idx+1}. **Option {idx+1}:** {s}" for idx, s in enumerate(suggs)])
            resp_text = (
                f"### 💡 Recommended Action Plan Options for `{target_title}`\n\n"
                f"{tool_data.get('message', '')}\n\n"
                f"{sugg_lines}\n\n"
                f"👉 *These are recommendations and have not been added to your draft. "
                f"To accept an option, reply e.g. **`Option 1`**, edit it, or enter your custom action plan.*"
            )
            session.state = RiskCreationState.AWAITING_ACTION_PLAN
            return self._make_response(request, resp_text, "STEP_ACTION_PLAN")

        is_desc_sugg_request = not (is_declining_suggestions or is_option_selection) and bool(
            re.search(r'\b(?:suggest|recommend|give|show)\b.*\b(?:description|hazard)s?\b', lower_msg)
            or re.search(r'\b(?:risk\s*)?description\s+suggestions?\b', lower_msg)
            or (session.state == RiskCreationState.AWAITING_DESCRIPTION and any(w in lower_msg for w in ["suggest", "recommend", "show options", "give options", "options"]))
        )
        if is_desc_sugg_request:
            target_title = session.risk_name or self.extract_risk_name_from_trigger(msg)
            if not target_title or len(target_title.strip()) < 3:
                return self._make_response(
                    request,
                    "💡 To provide relevant description recommendations, please specify the **Risk Name / Title** first.",
                    "STEP_RISK_NAME"
                )
            try:
                exec_res = self.execute_governed_tool(
                    tool_name="generate_risk_description_suggestions",
                    arguments={"risk_title": target_title},
                    session=session,
                )
                tool_data = exec_res.get("result", {})
                suggs = tool_data.get("suggestions", [])
            except Exception as e:
                logger.error(f"Error executing generate_risk_description_suggestions tool: {e}")
                suggs = static_suggestion_provider.get_description_suggestions(target_title)
                tool_data = {"message": "Retrieved curated fallback recommendations."}

            session.desc_options = suggs
            sugg_lines = "\n".join([f"{idx+1}. **Option {idx+1}:** {s}" for idx, s in enumerate(suggs)])
            resp_text = (
                f"### 💡 Recommended Risk Description Options for `{target_title}`\n\n"
                f"{tool_data.get('message', '')}\n\n"
                f"{sugg_lines}\n\n"
                f"👉 *These are recommendations and have not been added to your draft. "
                f"To accept an option, reply e.g. **`Option 1`**, edit it, or enter your custom description text.*"
            )
            session.state = RiskCreationState.AWAITING_DESCRIPTION
            return self._make_response(request, resp_text, "STEP_DESCRIPTION")

        # Check for owner lookup queries across turns
        is_owner_lookup_request = bool(
            re.search(r'\b(?:who\s+can\s+be|eligible|lookup|list|find|search|available)\s+(?:action\s*owner|co[\s\-_]?owner)s?\b', lower_msg)
            or re.search(r'\b(?:action\s*owner|co[\s\-_]?owner)\s+(?:options|candidates|list)\b', lower_msg)
        )
        if is_owner_lookup_request:
            is_co = "co" in lower_msg
            owner_type = "co_owner" if is_co else "action_owner"
            search_term = None
            term_match = re.search(r'(?:named|for|like|called|matching)\s+([A-Za-z0-9_\-\s]+)', msg, flags=re.IGNORECASE)
            if term_match:
                search_term = term_match.group(1).strip()
            try:
                exec_res = self.execute_governed_tool(
                    tool_name="get_eligible_risk_owners",
                    arguments={
                        "owner_type": owner_type,
                        "search_term": search_term,
                        "dept_id": session.dept_id,
                    },
                    session=session,
                )
                tool_data = exec_res.get("result", {})
                owners = tool_data.get("owners", [])
                guidance = tool_data.get("guidance", "")
                if owners:
                    owner_lines = "\n".join([
                        f"- **{o.get('full_name')}** (`{o.get('log_id')}`) — *{o.get('role_name')}* ({o.get('dept_name', 'Enterprise')})"
                        for o in owners[:5]
                    ])
                    resp_text = (
                        f"### 👥 Eligible {owner_type.replace('_', ' ').title()} Candidates\n\n"
                        f"{guidance}\n\n"
                        f"{owner_lines}\n\n"
                        f"👉 *To assign one, reply e.g. **`Assign {owner_type.replace('_', ' ')} {owners[0].get('full_name')}`** or specify their name.*"
                    )
                else:
                    resp_text = f"ℹ️ {guidance}"
                return self._make_response(request, resp_text, "STEP_ACTION_OWNER" if not is_co else "STEP_CO_OWNER")
            except Exception as e:
                logger.error(f"Error executing get_eligible_risk_owners tool: {e}")

        # Step-specific input handling for guided workflow
        if session.state == RiskCreationState.AWAITING_RISK_NAME:
            session.risk_name = msg.strip()
            extracted = extract_risk_fields(msg, session)
            has_other_fields = bool(
                extracted.risk_description
                or extracted.inherent_likelihood
                or extracted.mitigation
                or extracted.current_likelihood
                or extracted.action_plan
                or extracted.risk_co_owner_name
                or extracted.action_owner_name
                or session.risk_co_owner_name
                or session.action_owner_id
            )
            if not has_other_fields:
                answer = prompt_co_owner(session)
                return self._make_response(request, answer, "STEP_CO_OWNER")

        elif session.state == RiskCreationState.AWAITING_CO_OWNER:
            if any(w in lower_msg for w in ["skip", "none", "no co-owner", "no co owner", "pass", "without"]):
                session.risk_co_owner_id = None
                session.risk_co_owner_name = None
                session.risk_co_owner_role = None
            else:
                matched_co = None
                for u in session.available_co_owners:
                    uname = (u.get("full_name") or "").lower()
                    ulog = (u.get("log_id") or "").lower()
                    uid = str(u.get("user_id") or "")
                    if uname in lower_msg or ulog in lower_msg or f"id {uid}" in lower_msg or uid == lower_msg:
                        matched_co = u
                        break

                if not matched_co:
                    cleaned_term = lower_msg.replace("assign co-owner", "").replace("assign co owner", "").replace("co-owner", "").replace("co owner", "").strip()
                    if cleaned_term:
                        resolved = erm_db.resolve_user_by_name_or_role(cleaned_term)
                        if resolved:
                            matched_co = {
                                "user_id": resolved.get("user_id"),
                                "full_name": resolved.get("full_name") or resolved.get("log_id"),
                                "role_name": resolved.get("role_name", "Team Member")
                            }

                if matched_co:
                    session.risk_co_owner_id = matched_co.get("user_id")
                    session.risk_co_owner_name = matched_co.get("full_name")
                    session.risk_co_owner_role = matched_co.get("role_name")
                else:
                    session.risk_co_owner_id = None
                    session.risk_co_owner_name = msg.strip()
                    session.risk_co_owner_role = "Co-Owner"

        elif session.state == RiskCreationState.AWAITING_DESCRIPTION:
            opts = session.desc_options
            if any(w in lower_msg for w in ["option 1", "1"]) and len(opts) >= 1:
                session.risk_description = opts[0]
            elif any(w in lower_msg for w in ["option 2", "2"]) and len(opts) >= 2:
                session.risk_description = opts[1]
            elif any(w in lower_msg for w in ["option 3", "3"]) and len(opts) >= 3:
                session.risk_description = opts[2]
            else:
                session.risk_description = msg.strip()

        elif session.state == RiskCreationState.AWAITING_INHERENT_ASSESSMENT:
            raw_digits = [int(s) for s in re.findall(r'\b\d+\b', msg)]
            if any(d < 1 or d > 5 for d in raw_digits):
                return self._make_response(
                    request,
                    f"⚠️ **Validation Notice:** Likelihood and Impact ratings must be integers between 1 and 5. Out-of-bounds rating {raw_digits} was rejected.\n\nPlease select valid ratings (1–5):\n\n[assessment-matrix:inherent]",
                    "VALIDATION_FAILED"
                )
            parsed = RiskMatrixCalculator.parse_likelihood_impact(msg)
            if parsed and RiskMatrixCalculator.is_valid_rating(parsed[0]) and RiskMatrixCalculator.is_valid_rating(parsed[1]):
                session.update_inherent_assessment(parsed[0], parsed[1])
            else:
                only_l = RiskMatrixCalculator.parse_single_likelihood(msg)
                only_i = RiskMatrixCalculator.parse_single_impact(msg)
                if only_l and not session.inherent_impact:
                    session.inherent_likelihood = only_l
                    l_name = RiskMatrixCalculator.LIKELIHOOD_LABELS.get(only_l, "Selected")
                    return self._make_response(
                        request,
                        f"📊 Inherent Likelihood set to **{only_l} ({l_name})**.\n\nPlease select the mandatory **Impact (1–5)** rating:\n\n[assessment-matrix:inherent]",
                        "STEP_INHERENT_ASSESSMENT"
                    )
                elif only_i and not session.inherent_likelihood:
                    session.inherent_impact = only_i
                    i_name = RiskMatrixCalculator.IMPACT_LABELS.get(only_i, "Selected")
                    return self._make_response(
                        request,
                        f"💥 Inherent Impact set to **{only_i} ({i_name})**.\n\nPlease select the mandatory **Likelihood (1–5)** rating:\n\n[assessment-matrix:inherent]",
                        "STEP_INHERENT_ASSESSMENT"
                    )

        elif session.state == RiskCreationState.AWAITING_MITIGATION:
            if any(w in lower_msg for w in ["no suggestions", "decline suggestions", "skip suggestions", "write my own"]):
                return self._make_response(
                    request,
                    "Understood. Please enter your custom **Mitigation Strategy** text:",
                    "STEP_MITIGATION"
                )
            opts = session.mitigation_options
            if any(w in lower_msg for w in ["option 1", "use option 1", "first option"]) and len(opts) >= 1:
                session.mitigation = opts[0]
                session.field_provenance["mitigation"] = "user_selected_suggestion"
            elif any(w in lower_msg for w in ["option 2", "use option 2", "second option"]) and len(opts) >= 2:
                session.mitigation = opts[1]
                session.field_provenance["mitigation"] = "user_selected_suggestion"
            elif any(w in lower_msg for w in ["option 3", "use option 3", "third option"]) and len(opts) >= 3:
                session.mitigation = opts[2]
                session.field_provenance["mitigation"] = "user_selected_suggestion"
            elif lower_msg == "1" and len(opts) >= 1:
                session.mitigation = opts[0]
                session.field_provenance["mitigation"] = "user_selected_suggestion"
            elif lower_msg == "2" and len(opts) >= 2:
                session.mitigation = opts[1]
                session.field_provenance["mitigation"] = "user_selected_suggestion"
            elif lower_msg == "3" and len(opts) >= 3:
                session.mitigation = opts[2]
                session.field_provenance["mitigation"] = "user_selected_suggestion"
            else:
                session.mitigation = msg.strip()
                session.field_provenance["mitigation"] = "user_stated"

        elif session.state == RiskCreationState.AWAITING_CURRENT_ASSESSMENT:
            raw_digits = [int(s) for s in re.findall(r'\b\d+\b', msg)]
            if any(d < 1 or d > 5 for d in raw_digits):
                return self._make_response(
                    request,
                    f"⚠️ **Validation Notice:** Current Likelihood and Impact ratings must be integers between 1 and 5. Out-of-bounds rating {raw_digits} was rejected.\n\nPlease select valid ratings (1–5):\n\n[assessment-matrix:current]",
                    "VALIDATION_FAILED"
                )
            parsed = RiskMatrixCalculator.parse_likelihood_impact(msg)
            if parsed and RiskMatrixCalculator.is_valid_rating(parsed[0]) and RiskMatrixCalculator.is_valid_rating(parsed[1]):
                session.update_current_assessment(parsed[0], parsed[1])
            else:
                only_l = RiskMatrixCalculator.parse_single_likelihood(msg)
                only_i = RiskMatrixCalculator.parse_single_impact(msg)
                if only_l and not session.current_impact:
                    session.current_likelihood = only_l
                    l_name = RiskMatrixCalculator.LIKELIHOOD_LABELS.get(only_l, "Selected")
                    return self._make_response(
                        request,
                        f"📊 Current Likelihood set to **{only_l} ({l_name})**.\n\nPlease select the mandatory **Impact (1–5)** rating:\n\n[assessment-matrix:current]",
                        "STEP_CURRENT_ASSESSMENT"
                    )
                elif only_i and not session.current_likelihood:
                    session.current_impact = only_i
                    i_name = RiskMatrixCalculator.IMPACT_LABELS.get(only_i, "Selected")
                    return self._make_response(
                        request,
                        f"💥 Current Impact set to **{only_i} ({i_name})**.\n\nPlease select the mandatory **Likelihood (1–5)** rating:\n\n[assessment-matrix:current]",
                        "STEP_CURRENT_ASSESSMENT"
                    )

        elif session.state == RiskCreationState.AWAITING_ACTION_PLAN:
            if any(w in lower_msg for w in ["no suggestions", "decline suggestions", "skip suggestions", "write my own"]):
                return self._make_response(
                    request,
                    "Understood. Please enter your custom **Action Plan** text:",
                    "STEP_ACTION_PLAN"
                )
            opts = session.action_plan_options
            if any(w in lower_msg for w in ["option 1", "use option 1", "first option"]) and len(opts) >= 1:
                session.action_plan = opts[0]
                session.field_provenance["action_plan"] = "user_selected_suggestion"
            elif any(w in lower_msg for w in ["option 2", "use option 2", "second option"]) and len(opts) >= 2:
                session.action_plan = opts[1]
                session.field_provenance["action_plan"] = "user_selected_suggestion"
            elif any(w in lower_msg for w in ["option 3", "use option 3", "third option"]) and len(opts) >= 3:
                session.action_plan = opts[2]
                session.field_provenance["action_plan"] = "user_selected_suggestion"
            elif lower_msg == "1" and len(opts) >= 1:
                session.action_plan = opts[0]
                session.field_provenance["action_plan"] = "user_selected_suggestion"
            elif lower_msg == "2" and len(opts) >= 2:
                session.action_plan = opts[1]
                session.field_provenance["action_plan"] = "user_selected_suggestion"
            elif lower_msg == "3" and len(opts) >= 3:
                session.action_plan = opts[2]
                session.field_provenance["action_plan"] = "user_selected_suggestion"
            else:
                session.action_plan = msg.strip()
                session.field_provenance["action_plan"] = "user_stated"

        elif session.state == RiskCreationState.AWAITING_ACTION_OWNER:
            avail_aos = session.available_action_owners
            matched_ao = None

            for u in avail_aos:
                uname = (u.get("full_name") or "").lower()
                ulog = (u.get("log_id") or "").lower()
                uid = str(u.get("user_id") or "")
                if uname in lower_msg or ulog in lower_msg or f"id {uid}" in lower_msg or uid == lower_msg:
                    matched_ao = u
                    break

            if not matched_ao:
                cleaned_term = lower_msg.replace("assign action owner", "").replace("action owner", "").strip()
                if cleaned_term:
                    resolved = erm_db.resolve_user_by_name_or_role(cleaned_term, dept_id=session.dept_id)
                    if resolved:
                        matched_ao = {
                            "user_id": resolved.get("user_id"),
                            "full_name": resolved.get("full_name") or resolved.get("log_id"),
                            "role_name": resolved.get("role_name", "Action Owner")
                        }

            if matched_ao:
                session.action_owner_id = matched_ao.get("user_id")
                session.action_owner_name = matched_ao.get("full_name", "Action Owner")
                session.action_owner_role = matched_ao.get("role_name", "Action Owner")
            else:
                return self._make_response(
                    request,
                    f"🚫 **Ineligible Action Owner:** '{msg.strip()}' was not found among authorized Action Owners in department '{session.dept_name or 'General'}'.\n\nPlease select an eligible Action Owner from the department register.",
                    "STEP_ACTION_OWNER"
                )

        elif session.state == RiskCreationState.AWAITING_TARGET_DATE:
            parsed_dt = parse_target_date(msg)
            if not parsed_dt:
                parsed_dt = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")
            session.target_date = parsed_dt

        elif session.state == RiskCreationState.AWAITING_STATUS:
            resolved_st = erm_db.resolve_status_by_name(msg)
            if resolved_st:
                session.status_id = resolved_st.get("id", 1)
                session.status_name = resolved_st.get("status_name", "Draft")
            else:
                if any(w in lower_msg for w in ["submit", "functional head", "fh", "2"]):
                    session.status_id = 2
                    session.status_name = "Submitted to Functional Head"
                else:
                    session.status_id = 1
                    session.status_name = "Draft"

        # Also extract and merge any additional fields present in this message
        extracted = extract_risk_fields(msg, session)
        merge_res = merge_risk_draft(session, extracted, server_context)
        requirements = get_risk_creation_requirements(dept_id=session.dept_id)
        completeness = assess_risk_completeness(session, requirements)

        if completeness.invalid_fields:
            err_text = "\n".join([f"- **{k.replace('_', ' ').title()}:** {v}" for k, v in completeness.invalid_fields.items()])
            return self._make_response(
                request,
                f"⚠️ **Validation Notice:**\n{err_text}\n\nPlease provide a corrected value.",
                "VALIDATION_FAILED"
            )

        if completeness.is_ready_for_review:
            # If user was walking through wizard steps, continue the natural sequence
            is_single_step_advance = (
                previous_state in [
                    RiskCreationState.AWAITING_ACTION_PLAN,
                    RiskCreationState.AWAITING_ACTION_OWNER,
                    RiskCreationState.AWAITING_TARGET_DATE
                ]
                and not bool(extracted.action_plan and (extracted.mitigation or extracted.inherent_likelihood))
            )
            if is_single_step_advance:
                if previous_state == RiskCreationState.AWAITING_ACTION_PLAN and not session.action_owner_id:
                    answer = prompt_action_owner(session)
                    return self._make_response(request, answer, "STEP_ACTION_OWNER")
                elif previous_state == RiskCreationState.AWAITING_ACTION_OWNER and not session.target_date:
                    answer = prompt_target_date(session)
                    return self._make_response(request, answer, "STEP_TARGET_DATE")
                elif previous_state == RiskCreationState.AWAITING_TARGET_DATE:
                    answer = prompt_status(session)
                    return self._make_response(request, answer, "STEP_STATUS")

            session.state = RiskCreationState.AWAITING_CONFIRMATION
            session.validation_result = self.validate(session)
            self._bind_pending_confirmation(session)
            preview_text = self._render_preview_with_advisory(session)
            return self._make_response(request, preview_text, "WIZARD_CONFIRMATION")

        # Determine and prompt the next missing required field
        answer, next_step = self._prompt_next_missing_field(session)
        return self._make_response(request, answer, next_step)

    def _apply_field_edit(self, session: RiskCreationSession, field_name: str, new_val: str) -> str:
        """Apply user's requested edit to session field."""
        session.pending_confirmation = None
        session.awaiting_confirmation = False
        session.duplicate_check_input_hash = None
        session.duplicate_acknowledged = False
        if field_name == "target_date":
            parsed_dt = parse_target_date(new_val)
            session.target_date = parsed_dt or new_val
            return f"Updated Target Date to `{session.target_date}`."

        elif field_name == "progress":
            prog = parse_progress(new_val)
            if prog is not None:
                session.progress = prog
                return f"Updated Progress to `{session.progress}%`."
            return "Could not parse progress percentage. Please provide a number between 0 and 100."

        elif field_name == "mitigation":
            session.mitigation = new_val
            return "Updated Mitigation Strategy."

        elif field_name == "action_plan":
            session.action_plan = new_val
            return "Updated Action Plan."

        elif field_name == "risk_description":
            session.risk_description = new_val
            session.duplicate_check_input_hash = None
            session.duplicate_acknowledged = False
            return "Updated Risk Description."

        elif field_name == "risk_name":
            session.risk_name = new_val
            session.duplicate_check_input_hash = None
            session.duplicate_acknowledged = False
            return f"Updated Risk Name to `{session.risk_name}`."

        elif field_name == "co_owner":
            if any(w in new_val.lower() for w in ["none", "skip", "remove"]):
                session.risk_co_owner_id = None
                session.risk_co_owner_name = None
                session.risk_co_owner_role = None
                return "Cleared Co-Owner."
            else:
                resolved = erm_db.resolve_user_by_name_or_role(new_val)
                if resolved:
                    session.risk_co_owner_id = resolved.get("user_id")
                    session.risk_co_owner_name = resolved.get("full_name") or resolved.get("log_id")
                    session.risk_co_owner_role = resolved.get("role_name")
                else:
                    session.risk_co_owner_name = new_val
                return f"Updated Co-Owner to `{session.risk_co_owner_name}`."

        elif field_name == "action_owner":
            resolved = erm_db.resolve_user_by_name_or_role(new_val, dept_id=session.dept_id)
            if resolved:
                session.action_owner_id = resolved.get("user_id")
                session.action_owner_name = resolved.get("full_name") or resolved.get("log_id")
                session.action_owner_role = resolved.get("role_name")
            else:
                session.action_owner_name = new_val
            return f"Updated Action Owner to `{session.action_owner_name}`."

        elif field_name == "inherent_assessment":
            parsed = RiskMatrixCalculator.parse_likelihood_impact(new_val)
            if parsed:
                session.update_inherent_assessment(parsed[0], parsed[1])
                return f"Updated Inherent Assessment to Likelihood {parsed[0]} × Impact {parsed[1]} = {session.inherent_score} {session.inherent_badge}."
            return "Could not parse Inherent Likelihood and Impact."

        elif field_name == "current_assessment":
            parsed = RiskMatrixCalculator.parse_likelihood_impact(new_val)
            if parsed:
                session.update_current_assessment(parsed[0], parsed[1])
                return f"Updated Current Assessment to Likelihood {parsed[0]} × Impact {parsed[1]} = {session.current_score} {session.current_badge}."
            return "Could not parse Current Likelihood and Impact."

        elif field_name == "status":
            resolved_st = erm_db.resolve_status_by_name(new_val)
            if resolved_st:
                session.status_id = resolved_st.get("id", 1)
                session.status_name = resolved_st.get("status_name", "Draft")
                return f"Updated Status to `{session.status_name}`."
            return "Could not resolve status."

        return "Field updated."

    def _make_response(self, request: AgentRequest, answer_text: str, step_code: str) -> AgentResponse:
        """Sanitize output and wrap in standard AgentResponse contract."""
        req_id = getattr(request, "request_id", None) or str(uuid.uuid4())
        created_dt = getattr(request, "created_at", None)
        timestamp_str = created_dt.isoformat() if created_dt else datetime.now(timezone.utc).isoformat()

        # Persist checkpoint to PostgreSQL / workflow checkpointer
        try:
            from ERM_Copilot.workflow import workflow_checkpointer, AgentWorkflowState, WorkflowStatus, WorkflowType
            session_key = self.get_session_key(request)
            sess = self.get_session(session_key)
            if sess:
                active_wf = workflow_checkpointer.load_active_for_session(session_key)
                if not active_wf:
                    active_wf = AgentWorkflowState(
                        session_id=session_key,
                        workflow_type=WorkflowType.RISK_CREATION,
                        owner_user_id=str(sess.user_id),
                        owner_role=str(sess.user_role),
                        dept_id=sess.dept_id,
                        dept_name=sess.dept_name,
                        current_agent=self.agent_id,
                        current_step=step_code,
                        collected_fields=sess.to_dict(),
                    )
                else:
                    active_wf.current_step = step_code
                    active_wf.collected_fields = sess.to_dict()
                    active_wf.step_count += 1
                    if step_code in ["SAVED", "SUBMITTED", "WIZARD_COMPLETED"]:
                        active_wf.transition_to(WorkflowStatus.COMPLETED, step=step_code)
                    elif step_code == "AWAITING_CONFIRMATION":
                        active_wf.transition_to(WorkflowStatus.WAITING_FOR_CONFIRMATION, step=step_code)
                workflow_checkpointer.save(active_wf)
        except Exception as e:
            logger.debug(f"[CHECKPOINT_SAVE_ERROR] in RiskCreationAgent: {e}")

        sanitized_output = GuardrailManager.process_output(answer_text)

        return AgentResponse(
            request_id=req_id,
            agent_id=self.agent_id,
            status="success",
            success=True,
            response=sanitized_output.strip(),
            metadata={
                "intent": "CREATE_RISK",
                "workflow_state": step_code,
                "wizard_step": step_code,
                "timestamp": timestamp_str
            }
        )



# Global singleton instance
risk_creation_agent = RiskCreationAgent()
