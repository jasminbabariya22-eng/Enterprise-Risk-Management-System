"""
Enterprise Risk Management (ERM) - Conversational Treatment & Action Plan Management Agent.

Dedicated agent for multi-turn ISO-31000 compliant Risk Treatment / Action Plan lifecycle:
1. Add Treatment / Action Plan to existing risk
2. Update Progress Percentage & Status (0-100%, Draft / In Progress / Completed)
3. Reassign Department Action Owner
4. List & View Action Plans for any Risk or Department
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
from ERM_Copilot.agents.treatment.state import (
    TreatmentSession,
    TreatmentState,
    parse_date_string,
    parse_progress_percentage,
    extract_risk_identifier,
    extract_treatment_id
)
from ERM_Copilot.agents.treatment.prompts import (
    prompt_risk_selection,
    prompt_action_plan_step,
    prompt_action_owner_step,
    prompt_target_date_step,
    prompt_progress_step,
    build_treatment_preview
)
from ERM_Copilot.agents.treatment.tools import (
    update_treatment_progress_tool,
    reassign_treatment_owner_tool,
    add_risk_treatment_tool,
    get_treatments_for_risk_tool
)
from ERM_Copilot.models.contracts import AgentRequest, AgentResponse, RequestContext
from ERM_Copilot.services.db_service import erm_db

logger = logging.getLogger("ERM_Copilot.agents.treatment.agent")


class TreatmentManagementAgent(BaseAgent):
    """
    Dedicated Conversational Agent for Enterprise Risk Treatment / Action Plan Management.
    Handles multi-turn addition of action plans, progress updates, owner reassignment, and listings.
    """

    def __init__(self):
        super().__init__(
            agent_id="treatment_management_agent",
            name="ERM Treatment Management Agent",
            description="Agent for multi-turn ISO-31000 Risk Treatment & Action Plan formulation, tracking, and reassignment.",
            capabilities=[
                "add_action_plan",
                "update_treatment_progress",
                "reassign_action_owner",
                "list_risk_treatments"
            ]
        )
        self.sessions: Dict[str, TreatmentSession] = {}

    def execute(self, request: AgentRequest, context: RequestContext) -> Any:
        return self.process(request)

    # -----------------------------------------------------------------
    # Session Management
    # -----------------------------------------------------------------

    def get_session_key(self, request: AgentRequest) -> str:
        user_id = str(getattr(request, "user_id", None) or "5").strip()
        sess_id = str(getattr(request, "session_id", None) or "").strip()
        return f"{user_id}::{sess_id}" if sess_id else user_id

    def get_session(self, session_key: str) -> Optional[TreatmentSession]:
        return self.sessions.get(session_key)

    def is_session_active(self, session_key: str) -> bool:
        return session_key in self.sessions

    def clear_session(self, session_key: str) -> None:
        if session_key in self.sessions:
            del self.sessions[session_key]

    # -----------------------------------------------------------------
    # Intent Detection
    # -----------------------------------------------------------------

    @staticmethod
    def is_cancellation(msg: str) -> bool:
        lower = msg.strip().lower()
        return lower in ["cancel", "exit", "quit", "stop", "abort", "discard", "cancel action", "cancel treatment"]

    @staticmethod
    def is_add_treatment_trigger(msg: str) -> bool:
        lower = msg.lower()
        return (
            any(w in lower for w in [
                "add action", "new action", "add treatment", "new treatment", "create action",
                "attach action", "add plan", "create treatment", "action plan to risk",
                "action plan for risk", "add action plan", "attach plan", "add mitigation to risk"
            ])
            and not any(w in lower for w in ["show", "list", "view", "audit", "search"])
        )

    @staticmethod
    def is_update_progress_trigger(msg: str) -> bool:
        lower = msg.lower()
        return (
            any(w in lower for w in ["update progress", "change progress", "set progress", "progress to", "progress of", "mark progress", "update action progress"])
            or (any(w in lower for w in ["progress", "completed", "complete"]) and any(w in lower for w in ["treatment", "action plan", "action"]) and any(w in lower for w in ["to", "set", "%", "update"]))
        )

    @staticmethod
    def is_reassign_owner_trigger(msg: str) -> bool:
        lower = msg.lower()
        return (
            any(w in lower for w in ["reassign action", "change action owner", "reassign owner", "reassign treatment", "assign action owner to"])
        )

    @staticmethod
    def is_list_treatments_trigger(msg: str) -> bool:
        lower = msg.lower()
        return (
            any(w in lower for w in ["show treatment", "list treatment", "show action plan", "list action plan", "view treatment", "view action plan", "what are the treatments", "what are the action plans"])
        )

    # -----------------------------------------------------------------
    # Main Workflow Processor
    # -----------------------------------------------------------------

    def process(self, request: AgentRequest) -> AgentResponse:
        params = getattr(request, "metadata", {}) or getattr(request, "parameters", {}) or {}
        user_role = str(params.get("role") or getattr(request, "user_role", None) or "Risk Owner").strip()
        dept_id = params.get("dept_id")
        dept_name = params.get("dept_name")
        raw_user_id = getattr(request, "user_id", None) or params.get("user_id") or 8
        session_key = self.get_session_key(request)

        msg = (request.message or "").strip()
        lower_msg = msg.lower()

        # Handle Cancellation
        if self.is_cancellation(msg):
            if session_key in self.sessions:
                self.clear_session(session_key)
                return self._make_response(request, "❌ **Treatment Workflow Cancelled.** Draft action plan discarded.\n\nHow else may I assist you?", "TREATMENT_CANCELLED")

        # Intent 1: LIST / SHOW TREATMENTS
        if self.is_list_treatments_trigger(msg) and not self.is_session_active(session_key):
            target_risk_ident = extract_risk_identifier(msg)
            return self._handle_list_treatments(request, target_risk_ident, dept_id, dept_name)

        # Intent 2: UPDATE PROGRESS QUICK-PATH
        if self.is_update_progress_trigger(msg) and not self.is_session_active(session_key):
            t_id = extract_treatment_id(msg)
            target_risk_ident = extract_risk_identifier(msg)
            if not t_id and target_risk_ident:
                # Find treatments for this risk
                found_treatments = get_treatments_for_risk_tool(target_risk_ident, dept_id=dept_id)
                if found_treatments:
                    t_id = found_treatments[-1].get("risk_treatment_id") or found_treatments[-1].get("id")

            new_pct = parse_progress_percentage(msg)
            if t_id and new_pct is not None:
                res = update_treatment_progress_tool(treatment_id=t_id, progress=new_pct, modified_by=int(raw_user_id or 1))
                if res.get("status") == "success":
                    status_lbl = res.get("status_label", "In Progress")
                    r_code = res.get('risk_id') or target_risk_ident or 'risk'
                    return self._make_response(
                        request,
                        f"### ✅ Action Plan Progress Updated\n\n"
                        f"| Field | Updated Value |\n"
                        f"| :--- | :--- |\n"
                        f"| **Treatment ID** | `#{res['risk_treatment_id']}` |\n"
                        f"| **Risk Identifier** | `{r_code}` |\n"
                        f"| **Action Plan** | {res['action_plan']} |\n"
                        f"| **Progress** | **`{new_pct}%`** |\n"
                        f"| **Status** | `{status_lbl}` |\n\n"
                        f"The action plan progress has been recorded in the database.\n\n"
                        f"👉 **Next Action:**\n\n"
                        f"[btn-confirm:🚀 Resubmit to FH|Resubmit risk {r_code}] [btn:➕ Add Action Plan|Add action plan to risk {r_code}] [btn:📜 Audit Trail|Show audit trail for {r_code}]",
                        "PROGRESS_UPDATED"
                    )
                else:
                    return self._make_response(request, f"⚠️ Failed to update progress: {res.get('message')}", "ERROR")

        # Intent 3: REASSIGN OWNER QUICK-PATH
        if self.is_reassign_owner_trigger(msg) and not self.is_session_active(session_key):
            t_id = extract_treatment_id(msg)
            target_risk_ident = extract_risk_identifier(msg)
            if not t_id and target_risk_ident:
                found_treatments = get_treatments_for_risk_tool(target_risk_ident, dept_id=dept_id)
                if found_treatments:
                    t_id = found_treatments[-1].get("risk_treatment_id") or found_treatments[-1].get("id")

            name_term = re.sub(r'^(?:reassign|change|set)?\s*(?:action\s*owner|owner|treatment)?\s*(?:#?\d+)?\s*(?:to|for|is)?\s*', '', msg, flags=re.IGNORECASE).strip()
            if t_id and name_term:
                resolved_user = erm_db.resolve_user_by_name_or_role(name_term, dept_id=dept_id)
                if resolved_user:
                    res = reassign_treatment_owner_tool(treatment_id=t_id, new_action_owner_id=resolved_user["user_id"], modified_by=int(raw_user_id or 1))
                    if res.get("status") == "success":
                        r_code = res.get('risk_id') or target_risk_ident or 'risk'
                        return self._make_response(
                            request,
                            f"### ✅ Action Owner Reassigned\n\n"
                            f"| Field | Updated Value |\n"
                            f"| :--- | :--- |\n"
                            f"| **Treatment ID** | `#{res['risk_treatment_id']}` |\n"
                            f"| **Risk Identifier** | `{r_code}` |\n"
                            f"| **Action Plan** | {res['action_plan']} |\n"
                            f"| **New Action Owner** | **{res['action_owner_name']}** (ID: `{resolved_user['user_id']}`) |\n\n"
                            f"The responsibility has been reassigned in the database.\n\n"
                            f"👉 **Next Action:**\n\n"
                            f"[btn-confirm:🚀 Resubmit to FH|Resubmit risk {r_code}] [btn:📜 Audit Trail|Show audit trail for {r_code}]",
                            "OWNER_REASSIGNED"
                        )

        # Intent 4: START ADD TREATMENT CONVERSATIONAL WIZARD
        if self.is_add_treatment_trigger(msg) and not self.is_session_active(session_key):
            session = TreatmentSession(
                session_id=str(uuid.uuid4()),
                user_id=raw_user_id or 8,
                user_role=user_role,
                dept_id=dept_id,
                dept_name=dept_name,
                mode="ADD"
            )
            self.sessions[session_key] = session

            target_risk_ident = extract_risk_identifier(msg)
            if target_risk_ident:
                risk_rows = erm_db.search_risks(keyword=target_risk_ident, department=dept_name, limit=1)
                if risk_rows:
                    r_match = risk_rows[0]
                    session.target_risk_register_id = r_match["id"]
                    session.target_risk_id = r_match.get("risk_id")
                    session.target_risk_name = r_match.get("risk_title")
                    answer = prompt_action_plan_step(session)
                    return self._make_response(request, answer, "STEP_ACTION_PLAN")

            answer = prompt_risk_selection(session)
            return self._make_response(request, answer, "STEP_SELECT_RISK")

        # Multi-turn State Machine
        session = self.get_session(session_key)
        if not session:
            return self._make_response(
                request,
                "ℹ️ **Action Plan & Treatment Management**\n\nYou can perform any of the following actions:\n"
                "- ➕ *\"Add action plan to risk RSK-GAS-049\"*\n"
                "- 📊 *\"Update progress of treatment #12 to 75%\"*\n"
                "- 👤 *\"Reassign treatment #12 to Deepak Chauhan\"*\n"
                "- 📋 *\"Show action plans for RSK-GAS-049\"*",
                "TREATMENT_HELP"
            )

        # Step 1: Select Risk
        if session.state == TreatmentState.AWAITING_RISK_SELECTION:
            target_risk_ident = extract_risk_identifier(msg) or msg.strip()
            risk_rows = erm_db.search_risks(keyword=target_risk_ident, department=session.dept_name, limit=3)
            if not risk_rows and target_risk_ident.isdigit():
                risk_rows = erm_db.search_risks(keyword=target_risk_ident, limit=1)

            if risk_rows:
                r_match = risk_rows[0]
                session.target_risk_register_id = r_match["id"]
                session.target_risk_id = r_match.get("risk_id")
                session.target_risk_name = r_match.get("risk_title")
                answer = prompt_action_plan_step(session)
                return self._make_response(request, answer, "STEP_ACTION_PLAN")
            else:
                return self._make_response(
                    request,
                    f"⚠️ Could not locate a risk matching **`{target_risk_ident}`** in your department. Please select from the dropdown or type the Risk ID (e.g. `RSK-GAS-049`):",
                    "RISK_NOT_FOUND"
                )

        # Step 2: Action Plan Text / Suggestion
        elif session.state == TreatmentState.AWAITING_ACTION_PLAN:
            opts = session.action_plan_suggestions
            if any(w in lower_msg for w in ["option 1", "1"]) and len(opts) >= 1:
                session.action_plan = opts[0]
            elif any(w in lower_msg for w in ["option 2", "2"]) and len(opts) >= 2:
                session.action_plan = opts[1]
            elif any(w in lower_msg for w in ["option 3", "3"]) and len(opts) >= 3:
                session.action_plan = opts[2]
            else:
                session.action_plan = msg.strip()

            answer = prompt_action_owner_step(session)
            return self._make_response(request, answer, "STEP_ACTION_OWNER")

        # Step 3: Action Owner
        elif session.state == TreatmentState.AWAITING_ACTION_OWNER:
            matched_ao = None
            for u in session.available_action_owners:
                uname = (u.get("full_name") or "").lower()
                ulog = (u.get("log_id") or "").lower()
                uid = str(u.get("user_id") or "")
                if uname in lower_msg or ulog in lower_msg or f"id {uid}" in lower_msg or uid == lower_msg:
                    matched_ao = u
                    break

            if not matched_ao:
                cleaned_name = lower_msg.replace("assign action owner", "").replace("action owner", "").strip()
                if cleaned_name:
                    resolved = erm_db.resolve_user_by_name_or_role(cleaned_name, dept_id=session.dept_id)
                    if resolved:
                        matched_ao = {
                            "user_id": resolved.get("user_id"),
                            "full_name": resolved.get("full_name") or resolved.get("log_id")
                        }

            if matched_ao:
                session.action_owner_id = matched_ao.get("user_id")
                session.action_owner_name = matched_ao.get("full_name", "Action Owner")
            else:
                session.action_owner_id = session.user_id
                session.action_owner_name = msg.strip()

            answer = prompt_target_date_step(session)
            return self._make_response(request, answer, "STEP_TARGET_DATE")

        # Step 4: Target Date
        elif session.state == TreatmentState.AWAITING_TARGET_DATE:
            parsed_dt = parse_date_string(msg)
            if not parsed_dt:
                parsed_dt = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")
            session.target_date = parsed_dt

            answer = prompt_progress_step(session)
            return self._make_response(request, answer, "STEP_PROGRESS")

        # Step 5: Progress & Initial Status -> Preview
        elif session.state == TreatmentState.AWAITING_PROGRESS:
            pct = parse_progress_percentage(msg)
            session.progress = pct if pct is not None else 0
            session.action_status_id = 8 if session.progress >= 100 else (7 if session.progress > 0 else 1)

            session.state = TreatmentState.AWAITING_CONFIRMATION
            preview_text = build_treatment_preview(session)
            return self._make_response(request, preview_text, "AWAITING_CONFIRMATION")

        # Step 6: Confirmation -> Persist to Database
        elif session.state == TreatmentState.AWAITING_CONFIRMATION:
            if any(w in lower_msg for w in ["confirm", "yes", "save", "submit", "proceed", "ok", "confirm and save"]):
                res = add_risk_treatment_tool(
                    risk_register_id=session.target_risk_register_id or 1,
                    action_plan=session.action_plan or "Operational Risk Mitigation Treatment",
                    action_owner_id=session.action_owner_id or session.user_id,
                    target_date=session.target_date,
                    progress=session.progress,
                    action_status_id=session.action_status_id,
                    created_by=session.user_id
                )

                if res.get("status") == "error":
                    return self._make_response(request, f"❌ **Failed to Save Treatment:** {res.get('message')}\n\nPlease try confirming again or cancel.", "SAVE_FAILED")

                t_id = res.get("risk_treatment_id")
                r_id = res.get("risk_id")
                self.clear_session(session_key)

                success_msg = (
                    f"### ✅ Action Plan Added Successfully\n\n"
                    f"New treatment record **`#{t_id}`** has been attached to risk **`{r_id}`** in the database.\n\n"
                    f"| Field | Value |\n"
                    f"| :--- | :--- |\n"
                    f"| **Treatment ID** | `#{t_id}` |\n"
                    f"| **Target Risk** | `{session.target_risk_name}` (`{r_id}`) |\n"
                    f"| **Action Plan** | {session.action_plan} |\n"
                    f"| **Action Owner** | **{session.action_owner_name}** |\n"
                    f"| **Target Date** | `{session.target_date}` |\n"
                    f"| **Initial Progress** | `{session.progress}%` |\n\n"
                    f"The action owner will receive tasks in their department queue.\n\n"
                    f"👉 **Next Action:**\n\n"
                    f"[btn-confirm:🚀 Resubmit to FH|Resubmit risk {r_id}] [btn:➕ Add Another Action Plan|Add action plan to risk {r_id}] [btn:📜 Audit Trail|Show audit trail for {r_id}]"
                )
                return self._make_response(request, success_msg, "TREATMENT_CREATED")
            else:
                self.clear_session(session_key)
                return self._make_response(request, "❌ **Treatment Addition Cancelled.** Draft discarded.", "TREATMENT_CANCELLED")

        return self._make_response(request, "Unexpected state in Treatment Management workflow.", "ERROR")

    def _handle_list_treatments(self, request: AgentRequest, target_risk_ident: Optional[str], dept_id: Optional[int], dept_name: Optional[str]) -> AgentResponse:
        treatments = get_treatments_for_risk_tool(target_risk_ident or "", dept_id=dept_id) if target_risk_ident else []
        if not treatments and dept_id:
            treatments = erm_db.get_historical_treatments(dept_id=dept_id, limit=8)

        if not treatments:
            return self._make_response(
                request,
                f"ℹ️ No active action plans found for **`{target_risk_ident or dept_name or 'Department'}`**.\n\n"
                f"Would you like to add one? Type: *\"Add action plan to {target_risk_ident or 'risk'}\"*.",
                "TREATMENTS_EMPTY"
            )

        rows = []
        for idx, t in enumerate(treatments, 1):
            t_id = t.get("risk_treatment_id") or t.get("id")
            r_id = t.get("risk_id", "N/A")
            r_name = t.get("risk_name", "Risk")
            act = t.get("action_plan", "Action Plan")
            ao = t.get("action_owner_name") or t.get("action_owner", "Unassigned")
            t_dt = str(t.get("target_date") or "N/A")[:10]
            prog = t.get("progress", "0")
            st = t.get("action_status_name") or t.get("status", "In Progress")
            rows.append(f"| `#{t_id}` | `{r_id}` | **{act}** | {ao} | `{t_dt}` | **{prog}%** | `{st}` |")

        table_str = "\n".join(rows)

        resp_text = (
            f"### 📋 Action Plans & Risk Treatments\n\n"
            f"| # ID | Risk Code | Action Plan Description | Action Owner | Target Date | Progress | Status |\n"
            f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
            f"{table_str}\n\n"
            f"💡 *To update progress, type e.g. `Update progress of treatment #{treatments[0].get('risk_treatment_id') or 1} to 80%`.*"
        )
        return self._make_response(request, resp_text, "TREATMENTS_LISTED")

    def _make_response(self, request: AgentRequest, answer_text: str, intent_code: str) -> AgentResponse:
        req_id = getattr(request, "request_id", None) or str(uuid.uuid4())
        created_dt = getattr(request, "created_at", None)
        timestamp_str = created_dt.isoformat() if created_dt else datetime.now(timezone.utc).isoformat()

        return AgentResponse(
            request_id=req_id,
            agent_id=self.agent_id,
            status="success",
            success=True,
            response=answer_text.strip(),
            metadata={
                "intent": intent_code,
                "timestamp": timestamp_str
            }
        )


treatment_management_agent = TreatmentManagementAgent()
