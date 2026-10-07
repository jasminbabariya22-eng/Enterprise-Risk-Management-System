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
        return self.sessions.get(session_key)

    def is_session_active(self, session_key: str) -> bool:
        return session_key in self.sessions

    def clear_session(self, session_key: str) -> None:
        if session_key in self.sessions:
            del self.sessions[session_key]

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
        # If user wants to manage an action plan or treatment, do not trigger risk creation
        if any(w in lower for w in [
            "action plan", "treatment", "mitigation plan", "attach action",
            "add action", "new action", "update action", "reassign", "action to risk", "plan to risk"
        ]):
            return False
        return (
            any(w in lower for w in ["save", "create", "insert", "log", "record", "add"])
            and any(w in lower for w in ["risk", "hazard", "vulnerability", "leakage", "corrosion"])
            and not any(w in lower for w in ["queue", "audit", "trail", "timeline", "search", "show", "list", "pending", "history", "who approved", "action plan", "treatment"])
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
            r'^(?:please\s+)?(?:save|create|insert|log|record|add)\s+(?:a\s+|an\s+|the\s+)?(?:new\s+)?risk\s*(?:for|about|on|regarding|at|called|named)?\s*',
            '', msg, flags=re.IGNORECASE
        ).strip()
        
        # If user only said "Create a new risk" or "Create risk", return None so agent asks
        if not cleaned or cleaned.lower() in ["risk", "new risk", "a risk", "a new risk"]:
            return None

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
    # Validation
    # -----------------------------------------------------------------

    def validate(self, session: RiskCreationSession) -> Dict[str, Any]:
        """Validate complete risk details across Identity, Required Fields, Ownership, Assessment, Governance."""
        errors: List[str] = []
        warnings: List[str] = []

        # 1. Identity
        if not session.user_id:
            errors.append("Authenticated User ID is required.")
        if not session.dept_id:
            errors.append("Department ID could not be resolved from authenticated user context.")

        # 2. Required Risk Fields
        if not session.risk_name or len(session.risk_name.strip()) < 3:
            errors.append("Risk Name / Title is required (minimum 3 characters).")
        if not session.risk_description or len(session.risk_description.strip()) < 5:
            errors.append("Risk Description is required (minimum 5 characters).")

        # 3. Assessment
        if not session.inherent_likelihood or not (1 <= session.inherent_likelihood <= 5):
            errors.append("Inherent Likelihood must be between 1 and 5.")
        if not session.inherent_impact or not (1 <= session.inherent_impact <= 5):
            errors.append("Inherent Impact must be between 1 and 5.")
        if not session.mitigation or len(session.mitigation.strip()) < 5:
            errors.append("Mitigation Strategy is required (minimum 5 characters).")
        if not session.current_likelihood or not (1 <= session.current_likelihood <= 5):
            errors.append("Current / Residual Likelihood must be between 1 and 5.")
        if not session.current_impact or not (1 <= session.current_impact <= 5):
            errors.append("Current / Residual Impact must be between 1 and 5.")

        # 4. Action Plan & Ownership
        if not session.action_plan or len(session.action_plan.strip()) < 5:
            errors.append("Action Plan is required (minimum 5 characters).")
        if not session.action_owner_id:
            warnings.append("Action Owner is not yet assigned. Risk Owner will be designated as default.")

        # 5. Governance
        if not session.target_date:
            warnings.append("Target Date not explicitly set; defaulting to +30 days.")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }

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

            initial_title = self.extract_risk_name_from_trigger(msg)
            if initial_title:
                session.risk_name = initial_title
                answer = prompt_co_owner(session)
                return self._make_response(request, answer, "STEP_CO_OWNER")
            else:
                answer = prompt_risk_name(session)
                return self._make_response(request, answer, "STEP_RISK_NAME")

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

        # Inline editing check
        edit_target = detect_field_edits(msg)
        if edit_target and session.state in [RiskCreationState.AWAITING_CONFIRMATION, RiskCreationState.READY_FOR_PREVIEW]:
            field_name, new_val = edit_target
            updated_msg = self._apply_field_edit(session, field_name, new_val)
            val_res = self.validate(session)
            session.validation_result = val_res
            preview_text = build_preview(session)
            full_resp = f"✏️ **{updated_msg}**\n\n{preview_text}"
            return self._make_response(request, full_resp, "WIZARD_EDITED")

        # Step 1: Risk Name -> Co-Owner
        if session.state == RiskCreationState.AWAITING_RISK_NAME:
            session.risk_name = msg.strip()
            answer = prompt_co_owner(session)
            return self._make_response(request, answer, "STEP_CO_OWNER")

        # Step 2: Co-Owner -> Description
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

            answer = prompt_description(session)
            return self._make_response(request, answer, "STEP_DESCRIPTION")

        # Step 3: Description -> Inherent Assessment
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

            answer = prompt_inherent_assessment(session)
            return self._make_response(request, answer, "STEP_INHERENT_ASSESSMENT")

        # Step 4: Inherent Assessment -> Mitigation
        elif session.state == RiskCreationState.AWAITING_INHERENT_ASSESSMENT:
            parsed = RiskMatrixCalculator.parse_likelihood_impact(msg)
            if parsed:
                l_val, i_val = parsed
                session.update_inherent_assessment(l_val, i_val)
                answer = prompt_mitigation(session)
                return self._make_response(request, answer, "STEP_MITIGATION")
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
                else:
                    session.update_inherent_assessment(3, 4)
                    answer = prompt_mitigation(session)
                    return self._make_response(request, answer, "STEP_MITIGATION")

        # Step 5: Mitigation -> Current Assessment
        elif session.state == RiskCreationState.AWAITING_MITIGATION:
            opts = session.mitigation_options
            if any(w in lower_msg for w in ["option 1", "1"]) and len(opts) >= 1:
                session.mitigation = opts[0]
            elif any(w in lower_msg for w in ["option 2", "2"]) and len(opts) >= 2:
                session.mitigation = opts[1]
            elif any(w in lower_msg for w in ["option 3", "3"]) and len(opts) >= 3:
                session.mitigation = opts[2]
            else:
                session.mitigation = msg.strip()

            answer = prompt_current_assessment(session)
            return self._make_response(request, answer, "STEP_CURRENT_ASSESSMENT")

        # Step 6: Current Assessment -> Action Plan
        elif session.state == RiskCreationState.AWAITING_CURRENT_ASSESSMENT:
            parsed = RiskMatrixCalculator.parse_likelihood_impact(msg)
            if parsed:
                c_l, c_i = parsed
                session.update_current_assessment(c_l, c_i)
                answer = prompt_action_plan(session)
                return self._make_response(request, answer, "STEP_ACTION_PLAN")
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
                else:
                    session.update_current_assessment(2, 2)
                    answer = prompt_action_plan(session)
                    return self._make_response(request, answer, "STEP_ACTION_PLAN")

        # Step 7: Action Plan -> Action Owner
        elif session.state == RiskCreationState.AWAITING_ACTION_PLAN:
            opts = session.action_plan_options
            if any(w in lower_msg for w in ["option 1", "1"]) and len(opts) >= 1:
                session.action_plan = opts[0]
            elif any(w in lower_msg for w in ["option 2", "2"]) and len(opts) >= 2:
                session.action_plan = opts[1]
            elif any(w in lower_msg for w in ["option 3", "3"]) and len(opts) >= 3:
                session.action_plan = opts[2]
            else:
                session.action_plan = msg.strip()

            answer = prompt_action_owner(session)
            return self._make_response(request, answer, "STEP_ACTION_OWNER")

        # Step 8: Action Owner -> Target Date
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
                session.action_owner_id = None
                session.action_owner_name = msg.strip()
                session.action_owner_role = "Action Owner"

            answer = prompt_target_date(session)
            return self._make_response(request, answer, "STEP_TARGET_DATE")

        # Step 9: Target Date -> Status
        elif session.state == RiskCreationState.AWAITING_TARGET_DATE:
            parsed_dt = parse_target_date(msg)
            if not parsed_dt:
                parsed_dt = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")
            session.target_date = parsed_dt

            answer = prompt_status(session)
            return self._make_response(request, answer, "STEP_STATUS")

        # Step 10: Status -> Validate & Preview
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

            session.progress = 0

            # Validate
            val_res = self.validate(session)
            session.validation_result = val_res
            session.state = RiskCreationState.AWAITING_CONFIRMATION

            if not val_res["valid"]:
                err_text = "\n".join([f"- {e}" for e in val_res["errors"]])
                return self._make_response(
                    request,
                    f"⚠️ **Validation Errors Detected:**\n{err_text}\n\nPlease correct these issues before saving.",
                    "VALIDATION_FAILED"
                )

            preview_text = build_preview(session)
            return self._make_response(request, preview_text, "WIZARD_CONFIRMATION")

        # Step 13 & 14: Confirmation & Database Persistence
        elif session.state == RiskCreationState.AWAITING_CONFIRMATION:
            if any(w in lower_msg for w in ["confirm", "yes", "save", "submit", "proceed", "commit", "ok", "confirm and save"]):
                treatments = [{
                    "action_plan": session.action_plan or "Operational Risk Mitigation Action",
                    "action_owner_id": session.action_owner_id,
                    "target_date": session.target_date,
                    "progress": session.progress
                }]

                res = erm_db.create_risk(
                    risk_name=session.risk_name or "Operational Risk",
                    risk_description=session.risk_description or session.risk_name or "Operational Risk",
                    dept_id=session.dept_id,
                    dept_name=session.dept_name,
                    risk_owner_id=session.user_id,
                    risk_co_owner_id=session.risk_co_owner_id,
                    inherent_likelihood=session.inherent_likelihood or 3,
                    inherent_impact=session.inherent_impact or 4,
                    current_likelihood=session.current_likelihood or 2,
                    current_impact=session.current_impact or 2,
                    mitigation=session.mitigation or "",
                    status=session.status_id,
                    financial_year=session.financial_year,
                    treatments=treatments
                )

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
                self.clear_session(session_key)
                return self._make_response(
                    request,
                    "❌ **Risk Creation Cancelled.** Active draft session has been discarded.\n\nHow else may I assist you?",
                    "WIZARD_CANCELLED"
                )

        return self._make_response(request, "Unexpected state in Risk Creation workflow.", "WIZARD_ERROR")

    def _apply_field_edit(self, session: RiskCreationSession, field_name: str, new_val: str) -> str:
        """Apply user's requested edit to session field."""
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
            return "Updated Risk Description."

        elif field_name == "risk_name":
            session.risk_name = new_val
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
