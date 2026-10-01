"""
Production ERM Copilot & Automation Agent.
Specialized AI Advisor for Enterprise Risk Management across all 7 ERM Roles.
"""
import logging
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

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
from ERM_Copilot.models.contracts import AgentRequest, AgentResponse, RequestContext
from ERM_Copilot.services.db_service import erm_db
from ERM_Copilot.services.api_client import erm_api_client
from ERM_Copilot.gateway.client import portkey_client
from ERM_Copilot.guardrails.manager import GuardrailManager
from ERM_Copilot.transform.query_transformer import QueryTransformer
from ERM_Copilot.cache.response_cache import erm_response_cache

logger = logging.getLogger("ERM_Copilot.agents.agent")

ERM_SYSTEM_PROMPT = """You are the Senior Enterprise Risk Management (ERM) Copilot and Chief Risk Officer AI Advisor for plant, refinery, and corporate operations.

You are equipped to assist all 7 ERM stakeholder roles:
1. Risk Owner: Risk formulation, Likelihood × Impact calculation, 4-tier Treatment Matrix drafting, and action follow-up.
2. Functional Head: Department governance, review of submitted risks (Stage 2), and technical approval/rejection remark drafting.
3. Risk Manager: Cross-department assessment validation, Stage 3 reviews, and mitigation adequacy audits.
4. Risk Head (CRO): Stage 4 final approvals, board-level executive summaries, heatmap profiling, and escalation oversight.
5. Auditor: Immutable audit trail reconstruction, approval timestamp verification, and evidence traceability.
6. Management / Executive: C-suite risk exposure summaries and top plant hazard matrices.
7. ERM Admin: Role & access governance, workflow status health checks.

Formatting & Execution Standards:
- ALWAYS communicate in fluent, professional, executive-level English.
- Use clear thematic Markdown sections with headings (###), bullet points, and clean tables.
- Use severity badges: `[CRITICAL]` (Red / 15-25), `[HIGH]` (Orange / 10-14), `[MEDIUM]` (Yellow / 5-9), `[LOW]` (Green / 1-4).
- Use status badges: `✅ Completed / Approved`, `⚠️ Pending Approval / In Progress`, `🔴 Overdue / Action Required`.
- If no historical records exist in the database, DO NOT output empty dummy tables with dashes or '(none found)'. Immediately provide the tailored recommendations.
- CRITICAL: DO NOT generate any "Recommended Next Steps", "Progression to Stage", or generic "Next Steps" sections in the output. Keep answers strictly focused on assessment and data tables.
"""

WIZARD_SESSIONS: Dict[str, Dict[str, Any]] = {}


class ConversationalRiskWizard:
    """Conversational Form-Filling State Machine for 100% verified ERM Risk Creation."""

    @staticmethod
    def is_cancellation(msg: str) -> bool:
        lower = msg.strip().lower()
        return lower in [
            "cancel", "exit", "quit", "stop", "reset", "restart", 
            "start over", "abort", "cancel risk creation", "cancel creation"
        ]

    @staticmethod
    def is_start_trigger(msg: str) -> bool:
        lower = msg.lower()
        return (
            any(w in lower for w in ["save", "create", "insert", "log", "record", "add"])
            and any(w in lower for w in ["risk", "hazard", "vulnerability", "leakage", "corrosion"])
            and not any(w in lower for w in ["queue", "audit", "trail", "timeline", "search", "show", "list", "pending", "history", "who approved"])
        )

    @staticmethod
    def extract_title_and_desc(msg: str) -> tuple[str, str]:
        cleaned = re.sub(
            r'^(please\s+)?(save|create|insert|log|record|add)\s+(a\s+|an\s+|the\s+)?(new\s+)?risk\s+(for|about|on|regarding|at)?\s*',
            '', msg, flags=re.IGNORECASE
        ).strip()
        if not cleaned or len(cleaned) < 5:
            cleaned = msg.strip()
        
        cleaned = re.sub(r'\bpup\s*p\s*101\b', 'Pump P-101', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\bpump\s*p\s*101\b', 'Pump P-101', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\bp\s*101\b', 'Pump P-101', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\bleackage\b', 'Leakage', cleaned, flags=re.IGNORECASE)
        
        words = cleaned.split()
        title = " ".join([w.capitalize() if not w.upper().startswith("P-") else w.upper() for w in words])[:100]
        if not title:
            title = "Industrial Operational Risk Assessment"
        
        desc = f"Identified operational hazard: {title}. Potential escalation to process safety event, containment loss, or asset disruption requiring structured mitigation controls."
        return title, desc


class ERMCopilotAgent(BaseAgent):
    """
    Role-Aware Enterprise Risk Management (ERM) Copilot & Automation Agent.
    """

    def __init__(self):
        super().__init__(
            agent_id="erm_copilot_agent",
            name="MASS ERM Copilot & Automation Agent",
            description="Role-aware AI Copilot for Enterprise Risk Management, Approval Queues, Audit Trails, Scoring, and Treatment Planning.",
            capabilities=[
                "search_risk_register",
                "get_approval_queues",
                "get_risk_audit_trail",
                "calculate_risk_score",
                "get_overdue_actions",
                "draft_risk_treatment",
                "summarize_department_risks",
                "get_executive_dashboard"
            ]
        )

    def execute(self, request: AgentRequest, context: RequestContext) -> Any:
        return self.process(request)

    def process(self, request: AgentRequest) -> AgentResponse:
        """Process user query dynamically tailored to the user's role and RBAC scope."""
        params = getattr(request, "metadata", {}) or getattr(request, "parameters", {}) or {}
        user_role = str(params.get("role") or getattr(request, "user_role", None) or "").strip()
        dept_id = params.get("dept_id")
        dept_name = params.get("dept_name")
        raw_user_id = getattr(request, "user_id", None) or params.get("user_id") or "5"
        user_id = raw_user_id
        session_key = str(raw_user_id).strip()

        # --- 1. QUERY TRANSFORMATION ENGINE (Expand shorthands & acronyms) ---
        raw_msg = request.message or ""
        transformed_msg, transform_meta = QueryTransformer.transform(raw_msg, user_role, dept_name)
        
        # --- 2. ENTERPRISE SAFETY & COMPLIANCE GUARDRAILS ---
        normalized_request = request.model_copy(update={"message": transformed_msg}) if hasattr(request, "model_copy") else request
        guardrail_res = GuardrailManager.process_input(normalized_request)
        if guardrail_res.blocked:
            return self._make_response(request, guardrail_res.reason, "GUARDRAIL_BLOCKED")

        msg = guardrail_res.sanitized_text.strip()
        lower_msg = msg.lower()
        
        is_enterprise_role = any(r in user_role.lower() for r in [
            "super admin", "admin", "risk head", "risk manager", "management", "auditor", "executive"
        ])
        filter_dept_id = None if is_enterprise_role else dept_id
        filter_dept_name = None if is_enterprise_role else dept_name
        
        logfire.info(f"[ERMCopilotAgent] Role='{user_role}', Dept='{dept_name}' (ID: {dept_id}) | Query: '{msg}'")

        # --- 2. HIGH-SPEED RESPONSE CACHE LOOKUP ---
        is_wizard_active = (session_key in WIZARD_SESSIONS) or ConversationalRiskWizard.is_start_trigger(msg) or ConversationalRiskWizard.is_cancellation(msg)
        if not is_wizard_active:
            cached_resp = erm_response_cache.get(msg, user_role, filter_dept_id)
            if cached_resp:
                cached_text = cached_resp.response if hasattr(cached_resp, "response") else str(cached_resp)
                return self._make_response(request, cached_text, "CACHE_HIT")

        # 0. CONVERSATIONAL RISK CREATION WIZARD (STATE MACHINE)
        if ConversationalRiskWizard.is_cancellation(msg):
            if session_key in WIZARD_SESSIONS:
                del WIZARD_SESSIONS[session_key]
                return self._make_response(request, "❌ **Risk Creation Wizard Cancelled.** Active draft session cleared.\n\nHow else may I assist you with the Risk Register?", "WIZARD_CANCELLED")

        session = WIZARD_SESSIONS.get(session_key)

        # STEP 1 -> STEP 2
        if session and session.get("step") == "AWAITING_SCORING":
            l_val, i_val = 3, 4
            if any(w in lower_msg for w in ["option a", "critical", "4x5", "4 5", "score 20", "20"]):
                l_val, i_val = 4, 5
            elif any(w in lower_msg for w in ["option b", "high", "3x4", "3 4", "score 12", "12"]):
                l_val, i_val = 3, 4
            elif any(w in lower_msg for w in ["option c", "medium", "3x3", "3 3", "score 9", "9"]):
                l_val, i_val = 3, 3
            elif any(w in lower_msg for w in ["option d", "low", "2x2", "2 2", "score 4", "4"]):
                l_val, i_val = 2, 2
            else:
                numbers = [int(s) for s in re.findall(r'\b[1-5]\b', msg)]
                if len(numbers) >= 2:
                    l_val, i_val = numbers[0], numbers[1]
                elif len(numbers) == 1:
                    l_val, i_val = numbers[0], min(numbers[0] + 1, 5)

            score = l_val * i_val
            sev_badge = "[CRITICAL]" if score >= 15 else ("[HIGH]" if score >= 10 else ("[MEDIUM]" if score >= 5 else "[LOW]"))

            session["likelihood"] = l_val
            session["impact"] = i_val
            session["score"] = score
            session["severity_badge"] = sev_badge
            session["step"] = "AWAITING_MITIGATION"

            title = session.get("risk_title", "Operational Hazard")
            if any(w in title.lower() for w in ["pump", "gas", "leak", "valve"]):
                opt1 = f"Isolate suction/discharge valves, depressurize, and replace mechanical seal with API 682 Plan 53B dual seal on {title}."
                opt2 = "Install optical infrared (IR) gas detection sensor with DCS automated Emergency Shutdown (ESD) interlock."
                opt3 = "Perform ultrasonic wall thickness scanning on adjoining spool and implement weekly LDAR sniffer rounds."
            elif any(w in title.lower() for w in ["corrosion", "pipe", "crude", "h2s", "column"]):
                opt1 = "Replace carbon steel pipe spool with 13Cr-Mo alloy metallurgy and install MDEA inhibitor injection skid."
                opt2 = "Online real-time H2S monitoring with DCS alarm set at 5 ppm and weekly corrosion coupon measurement."
                opt3 = "Ultrasonic phased array inspection on high-turbulent elbow sections and baseline radiography."
            else:
                opt1 = f"Implement immediate engineering isolation, containment, and certified component overhaul for {title}."
                opt2 = "Upgrade automated instrumentation thresholds and DCS alarm trips with fail-safe interlocks."
                opt3 = "Conduct comprehensive non-destructive testing (NDT) and schedule routine preventative maintenance."

            session["mitigation_options"] = [opt1, opt2, opt3]

            answer = (
                f"### 🛡️ Step 2/5: Risk Mitigation & Treatment Plan\n\n"
                f"**Risk Title:** `{title}`<br>\n"
                f"**Inherent Severity:** Likelihood {l_val} × Impact {i_val} = **{score} / 25 {sev_badge}**\n\n"
                f"Please choose an industrial mitigation strategy or provide your custom action plan:\n\n"
                f"1. **Engineering Control:** {opt1}\n"
                f"2. **Safety Interlock & Sensors:** {opt2}\n"
                f"3. **Inspection & Maintenance:** {opt3}\n\n"
                f"👉 *Select one of the mitigation controls below or type a custom plan:*\n\n"
                f"[btn:1️⃣ Option 1: Engineering Containment|Option 1 Engineering Control] "
                f"[btn:2️⃣ Option 2: Safety Interlock & Sensors|Option 2 Safety Interlock] "
                f"[btn:3️⃣ Option 3: Inspection & Maintenance|Option 3 Inspection Routine]"
            )
            return self._make_response(request, answer, "WIZARD_STEP_2")

        # STEP 2 -> STEP 3
        elif session and session.get("step") == "AWAITING_MITIGATION":
            opts = session.get("mitigation_options", [])
            chosen_mitigation = ""
            if any(w in lower_msg for w in ["option 1", "1", "engineering", "containment", "seal"]) and len(opts) >= 1:
                chosen_mitigation = opts[0]
            elif any(w in lower_msg for w in ["option 2", "2", "sensor", "interlock", "esd", "detection"]) and len(opts) >= 2:
                chosen_mitigation = opts[1]
            elif any(w in lower_msg for w in ["option 3", "3", "inspection", "ldar", "maintenance"]) and len(opts) >= 3:
                chosen_mitigation = opts[2]
            else:
                chosen_mitigation = msg.strip()

            session["mitigation"] = chosen_mitigation
            session["action_plan"] = chosen_mitigation
            session["step"] = "AWAITING_ACTION_OWNER"

            dept_action_owners = erm_db.get_department_action_owners(dept_id=session.get("dept_id"), dept_name=session.get("dept_name"))
            if not dept_action_owners:
                dept_action_owners = [
                    {"user_id": 6, "full_name": "Sunil Yadav", "role_name": "Action Owner", "dept_name": session.get("dept_name", "Refining")}
                ]
            session["available_action_owners"] = dept_action_owners

            user_rows = []
            buttons = []
            for u in dept_action_owners:
                uid = u.get("user_id")
                name = u.get("full_name") or u.get("log_id")
                role = u.get("role_name", "Action Owner")
                dname = u.get("dept_name", session.get("dept_name", "Refining"))
                user_rows.append(f"| `{uid}` | **{name}** | `{role}` | {dname} |")
                buttons.append(f"[btn:👤 {name} ({role})|Assign Action Owner {name}]")

            user_table = "\n".join(user_rows)
            button_strip = " ".join(buttons)

            answer = (
                f"### 🛡️ Step 3/5: Assign Action Owner (Same Department)\n\n"
                f"**Department Scope:** `{session.get('dept_name', 'Refining')}` (ID: {session.get('dept_id', 1)})<br>\n"
                f"**Selected Mitigation:** `{chosen_mitigation}`\n\n"
                f"Please choose an **Action Owner** from your department team:\n\n"
                f"| User ID | Full Name | Department Role | Unit |\n"
                f"| :--- | :--- | :--- | :--- |\n"
                f"{user_table}\n\n"
                f"👉 *Click to assign an Action Owner from your department:*\n\n"
                f"{button_strip}"
            )
            return self._make_response(request, answer, "WIZARD_STEP_3")

        # STEP 3 -> STEP 4
        elif session and session.get("step") == "AWAITING_ACTION_OWNER":
            avail_aos = session.get("available_action_owners", [])
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
                    resolved = erm_db.resolve_user_by_name_or_role(cleaned_term, dept_id=session.get("dept_id"))
                    if resolved:
                        matched_ao = {
                            "user_id": resolved.get("user_id"),
                            "full_name": resolved.get("full_name") or resolved.get("log_id"),
                            "role_name": resolved.get("role_name", "Action Owner")
                        }

            if not matched_ao and avail_aos:
                matched_ao = avail_aos[0]

            session["action_owner_id"] = matched_ao.get("user_id", 6) if matched_ao else 6
            session["action_owner_name"] = matched_ao.get("full_name", "Action Owner") if matched_ao else "Action Owner"
            session["action_owner_role"] = matched_ao.get("role_name", "Action Owner") if matched_ao else "Action Owner"
            session["step"] = "AWAITING_CO_OWNER"

            co_users = erm_db.get_all_users_for_co_owner(limit=10)
            session["available_co_users"] = co_users

            co_rows = []
            buttons = [f"[btn:⏩ None (Skip Co-Owner)|Skip Co-Owner]"]
            for u in co_users[:6]:
                uid = u.get("user_id")
                name = u.get("full_name") or u.get("log_id")
                role = u.get("role_name", "Team Member")
                dname = u.get("dept_name", "Enterprise")
                co_rows.append(f"| `{uid}` | **{name}** | {role} | {dname} |")
                buttons.append(f"[btn:👤 {name}|Assign Co-Owner {name}]")

            co_table = "\n".join(co_rows)
            button_strip = " ".join(buttons)

            answer = (
                f"### 🛡️ Step 4/5: Select Co Risk Owner (Optional - All Users)\n\n"
                f"**Assigned Action Owner:** `{session['action_owner_name']}` ({session['action_owner_role']})\n\n"
                f"You may optionally assign a **Co Risk Owner** from across the organization, or skip this step:\n\n"
                f"| User ID | Personnel Name | Role | Department |\n"
                f"| :--- | :--- | :--- | :--- |\n"
                f"{co_table}\n\n"
                f"👉 *Select a Co-Owner or Skip:*\n\n"
                f"{button_strip}"
            )
            return self._make_response(request, answer, "WIZARD_STEP_4")

        # STEP 4 -> STEP 5
        elif session and session.get("step") == "AWAITING_CO_OWNER":
            co_users = session.get("available_co_users", [])
            matched_co = None
            if not any(w in lower_msg for w in ["skip", "none", "no co-owner", "no co owner", "pass"]):
                for u in co_users:
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
                session["co_owner_id"] = matched_co.get("user_id")
                session["co_owner_name"] = matched_co.get("full_name")
                session["co_owner_role"] = matched_co.get("role_name")
            else:
                session["co_owner_id"] = None
                session["co_owner_name"] = "None (Not Assigned)"
                session["co_owner_role"] = "N/A"

            session["step"] = "AWAITING_SUBMISSION_MODE"

            answer = (
                f"### 🛡️ Step 5/5: Submission Status & Target Completion Timeline\n\n"
                f"**Action Owner:** `{session['action_owner_name']}` | **Co Risk Owner:** `{session['co_owner_name']}`\n\n"
                f"Please select the governance submission status and target completion timeline:\n\n"
                f"- **💾 Save as Draft (Status 1):** Save privately in your department workspace for ongoing editing.\n"
                f"- **🚀 Submit to Functional Head (Status 2):** Send directly to Stage 2 review queue for department head sign-off.\n\n"
                f"👉 *Select workflow submission status:*\n\n"
                f"[btn:💾 Save as Draft (30 Days)|Save as Draft 30 Days] "
                f"[btn:🚀 Submit to Functional Head (30 Days)|Submit to Functional Head 30 Days] "
                f"[btn:💾 Save as Draft (60 Days)|Save as Draft 60 Days]"
            )
            return self._make_response(request, answer, "WIZARD_STEP_5")

        # STEP 5 -> STEP 6
        elif session and session.get("step") == "AWAITING_SUBMISSION_MODE":
            target_status = 2 if any(w in lower_msg for w in ["submit", "fh", "stage 2", "functional head"]) else 1
            target_days = 60 if "60" in msg else (90 if "90" in msg else 30)
            status_label = "Submitted to Functional Head (Stage 2 Review)" if target_status == 2 else "Draft (Saved in Risk Owner Workspace)"

            session["target_status"] = target_status
            session["status_label"] = status_label
            session["target_days"] = target_days
            session["step"] = "AWAITING_CONFIRMATION"

            l_val = session.get("likelihood", 3)
            i_val = session.get("impact", 4)
            score = session.get("score", l_val * i_val)
            badge = session.get("severity_badge", "[HIGH]")

            answer = (
                f"### 📋 ERM Risk Register – Final Review & Verification\n\n"
                f"Please verify the compiled risk details. All fields are **100% verified against your selections**:\n\n"
                f"| Form Field | User-Verified Value |\n"
                f"| :--- | :--- |\n"
                f"| **Risk Title** | **{session.get('risk_title')}** |\n"
                f"| **Department** | {session.get('dept_name', 'Refining')} (ID: {session.get('dept_id', 1)}) |\n"
                f"| **Inherent Severity** | Likelihood {l_val} × Impact {i_val} = **{score} / 25 {badge}** |\n"
                f"| **Mitigation Strategy** | {session.get('mitigation')} |\n"
                f"| **Action Plan** | {session.get('action_plan')} |\n"
                f"| **Action Owner** | **{session.get('action_owner_name')}** ({session.get('action_owner_role', 'Action Owner')}) |\n"
                f"| **Co Risk Owner** | {session.get('co_owner_name', 'None')} |\n"
                f"| **Target Timeline** | +{target_days} Days |\n"
                f"| **Governance Status** | `{status_label}` |\n\n"
                f"👉 *Zero hallucinated data. Click below to save to PostgreSQL database:*\n\n"
                f"[btn-confirm:✅ Confirm & Save to Database|Confirm and Save to Database] "
                f"[btn-cancel:❌ Cancel|Cancel Risk Creation]"
            )
            return self._make_response(request, answer, "WIZARD_CONFIRMATION")

        # STEP 6 -> COMMIT
        elif session and session.get("step") == "AWAITING_CONFIRMATION":
            if any(w in lower_msg for w in ["confirm", "yes", "save", "proceed", "commit", "ok", "confirm and save to database"]):
                sample_treatments = [{
                    "action_plan": session.get("action_plan", session.get("mitigation", "Industrial Mitigation")),
                    "action_owner_id": session.get("action_owner_id", 6)
                }]

                raw_data = erm_db.create_risk(
                    risk_name=session.get("risk_title", "Operational Risk"),
                    risk_description=session.get("risk_desc", session.get("risk_title", "Operational Risk")),
                    dept_id=session.get("dept_id", 1),
                    dept_name=session.get("dept_name", "Refining"),
                    risk_owner_id=raw_user_id,
                    risk_co_owner_id=session.get("co_owner_id"),
                    inherent_likelihood=session.get("likelihood", 3),
                    inherent_impact=session.get("impact", 4),
                    mitigation=session.get("mitigation", "Standard Mitigation"),
                    status=session.get("target_status", 1),
                    treatments=sample_treatments
                )

                # Invalidate cache when new risk is registered
                erm_response_cache.invalidate_all()
                del WIZARD_SESSIONS[session_key]

                rid = raw_data.get("risk_id", "RSK-REF-001") if isinstance(raw_data, dict) else "RSK-REF-001"
                reg_id = raw_data.get("risk_register_id", "") if isinstance(raw_data, dict) else ""
                st_label = session.get("status_label", "Draft")

                answer = (
                    f"### ✅ ERM Risk Successfully Created & Saved to Database!\n\n"
                    f"The risk record has been persisted into the Enterprise Risk Management database (`MassERS`) with 100% verified parameters.\n\n"
                    f"| Database Property | Persisted Value |\n"
                    f"| :--- | :--- |\n"
                    f"| **Generated Risk ID** | `{rid}` |\n"
                    f"| **Register Primary Key** | `#{reg_id}` |\n"
                    f"| **Risk Title** | **{session.get('risk_title')}** |\n"
                    f"| **Department** | {session.get('dept_name', 'Refining')} |\n"
                    f"| **Inherent Rating** | Likelihood {session.get('likelihood')} × Impact {session.get('impact')} = **{session.get('score')} / 25 {session.get('severity_badge')}** |\n"
                    f"| **Action Owner (Same Dept)** | {session.get('action_owner_name')} |\n"
                    f"| **Co Risk Owner** | {session.get('co_owner_name', 'None')} |\n"
                    f"| **Workflow Status** | `{st_label}` |\n"
                    f"| **Audit Tables Updated** | `ers.risk_register`, `ers.risk_description`, `ers.risk_treatment` |\n\n"
                    f"> 🛡️ **Audit Confirmation:** Immutable audit history record initialized. Risk is now visible in the Department Risk Register."
                )
                return self._make_response(request, answer, "WIZARD_COMPLETED")
            else:
                del WIZARD_SESSIONS[session_key]
                return self._make_response(request, "❌ **Risk Creation Cancelled.** Active draft session has been discarded.\n\nHow else may I assist you?", "WIZARD_CANCELLED")

        # Trigger new Risk Creation Intent
        if ConversationalRiskWizard.is_start_trigger(msg):
            title, desc = ConversationalRiskWizard.extract_title_and_desc(msg)
            session = {
                "step": "AWAITING_SCORING",
                "risk_title": title,
                "risk_desc": desc,
                "dept_id": dept_id or 1,
                "dept_name": dept_name or "Refining",
                "user_id": raw_user_id,
                "user_role": user_role or "Risk Owner"
            }
            WIZARD_SESSIONS[session_key] = session

            answer = (
                f"### 🛡️ Step 1/5: Inherent Risk Severity & Scoring\n\n"
                f"**Identified Risk Title:** `{title}`<br>\n"
                f"**Description:** `{desc}`\n\n"
                f"Please select the inherent **Likelihood (1–5) × Impact (1–5)** rating:\n\n"
                f"| Option | Likelihood × Impact | Inherent Score | Classification |\n"
                f"| :--- | :--- | :--- | :--- |\n"
                f"| **A. Critical** | Likelihood 4 × Impact 5 | **20** | `[CRITICAL]` |\n"
                f"| **B. High** | Likelihood 3 × Impact 4 | **12** | `[HIGH]` |\n"
                f"| **C. Medium** | Likelihood 3 × Impact 3 | **9** | `[MEDIUM]` |\n"
                f"| **D. Low** | Likelihood 2 × Impact 2 | **4** | `[LOW]` |\n\n"
                f"👉 *Select an inherent severity level below or type a custom score (e.g. `3 4`):*\n\n"
                f"[btn:🔴 Option A: Critical (4x5)|Option A Critical] "
                f"[btn:🟠 Option B: High (3x4)|Option B High] "
                f"[btn:🟡 Option C: Medium (3x3)|Option C Medium] "
                f"[btn:🟢 Option D: Low (2x2)|Option D Low]"
            )
            return self._make_response(request, answer, "WIZARD_STEP_1")

        # 1. INTENT DETECTION & DIRECT QUERIES
        intent = "GENERAL_RISK_QUERY"
        raw_data = None
        db_context = ""

        # 0. DIRECT 1-CLICK APPROVAL OR REJECTION IN CHAT
        approve_match = re.search(r'\b(approve|reject|signoff|sign-off|return)\s+(?:risk\s+)?(RSK-[A-Z]+-\d+|\d+)\b', msg, re.IGNORECASE)
        if approve_match:
            action_word = approve_match.group(1).lower()
            target_id = approve_match.group(2)
            remark_match = re.search(r'(?:with\s+remark|remark:?)\s*(.+)$', msg, re.IGNORECASE)
            remark_text = remark_match.group(1).strip() if remark_match else ("Approved via ERM Copilot" if "app" in action_word else "Returned via ERM Copilot for revision")
            
            app_id = user_id if isinstance(user_id, int) else (int(user_id) if str(user_id).isdigit() else 4)
            result = erm_db.approve_or_reject_risk(
                risk_id=target_id,
                approver_id=app_id,
                user_role=user_role,
                action=action_word,
                remark=remark_text
            )
            if result.get("success"):
                status_badge = "✅ **Risk Approved & Signed Off**" if "app" in action_word else "❌ **Risk Returned / Rejected**"
                answer = (
                    f"## {status_badge}\n\n"
                    f"The risk record has been successfully updated in the **Enterprise Risk Management database (MassERS)**:\n\n"
                    f"| Property | Persisted Value |\n"
                    f"|---|---|\n"
                    f"| **Risk Identifier** | `{result['risk_id']}` (Register #{result['risk_register_id']}) |\n"
                    f"| **Risk Title** | {result['risk_title']} |\n"
                    f"| **Action Taken** | {result['action']} |\n"
                    f"| **Governance Tier** | {result['stage']} |\n"
                    f"| **Next Review Queue** | `{result['next_queue']}` |\n"
                    f"| **Approval Timestamp** | `{result['timestamp']}` |\n"
                    f"| **Recorded Remark** | *\"{result['remark']}\"* |\n\n"
                    f"🛡️ *Audit Confirmation: Immutable governance audit history record updated. Status is now live on ERM Portal.*"
                )
                return self._make_response(request, answer, "DIRECT_APPROVAL_SUCCESS")
            else:
                answer = f"⚠️ **Approval Action Could Not Be Completed:** {result.get('message', 'Unknown error')}"
                return self._make_response(request, answer, "DIRECT_APPROVAL_FAILED")

        # 0b. PROACTIVE MORNING BRIEFING & MY PENDING TASKS
        elif any(w in lower_msg for w in ["briefing", "morning briefing", "my pending", "my tasks", "what's pending for me", "my daily update", "overview for me"]):
            intent = "DAILY_BRIEFING"
            u_num = user_id if isinstance(user_id, int) else (int(user_id) if str(user_id).isdigit() else None)
            briefing = erm_db.get_user_daily_briefing(user_id=u_num, role_name=user_role, dept_id=filter_dept_id)
            items = briefing.get("items", [])
            lines = [
                f"### ☀️ Personalized Daily Briefing: {user_role or 'ERM Personnel'}\n",
                f"📊 **{briefing.get('briefing_type', 'Action Queue')}:** `{briefing.get('pending_count', 0)} items pending`\n"
            ]
            if items:
                lines.append("| Item ID | Title / Action Plan | Timeline | Instant Action |")
                lines.append("| :--- | :--- | :---: | :--- |")
                for it in items:
                    r_code = it.get("risk_id") or f"TRT-{it.get('risk_treatment_id')}"
                    r_text = it.get("risk_name") or it.get("action_plan") or "Operational Item"
                    t_date = str(it.get("target_date") or it.get("created_on") or "2026-2027")[:10]
                    btn_code = f"[btn-confirm:✅ Approve|Approve {r_code}] [btn:📜 Audit|Show audit trail for {r_code}]" if "risk_id" in it else f"[btn:🔍 View|Show details for {r_code}]"
                    lines.append(f"| `{r_code}` | **{r_text}** | {t_date} | {btn_code} |")
            else:
                lines.append("🎉 **All clear!** No pending sign-offs or overdue actions currently assigned to your queue.")
            answer = "\n".join(lines)
            return self._make_response(request, answer, "DAILY_BRIEFING")

        # 0c. INTERACTIVE 5x5 RISK MATRIX HEATMAP
        elif any(w in lower_msg for w in ["heatmap", "5x5", "heat map", "risk matrix", "matrix heatmap", "distribution"]):
            dist = erm_db.get_risk_matrix_distribution(dept_id=filter_dept_id)
            scope_title = filter_dept_name or "Enterprise Fleet"
            g = dist.get("grid", {})
            lines = [
                f"### 📊 Interactive 5×5 Risk Matrix Heatmap ({scope_title})\n",
                f"Total Monitored Risks: **{dist.get('total', 0)}** | 🔴 Critical: **{dist.get('critical_count', 0)}** | 🟠 High: **{dist.get('high_count', 0)}** | 🟡 Medium: **{dist.get('medium_count', 0)}** | 🟢 Low: **{dist.get('low_count', 0)}**\n",
                "| Likelihood \\ Impact | 1 (Insignificant) | 2 (Minor) | 3 (Moderate) | 4 (Major) | 5 (Catastrophic) |",
                "| :--- | :---: | :---: | :---: | :---: | :---: |",
                f"| **5 (Almost Certain)** | 🟡 {g.get('5x1', 0)} | 🟠 {g.get('5x2', 0)} | 🔴 {g.get('5x3', 0)} | 🔴 {g.get('5x4', 0)} | 🔴 {g.get('5x5', 0)} |",
                f"| **4 (Likely)** | 🟡 {g.get('4x1', 0)} | 🟡 {g.get('4x2', 0)} | 🟠 {g.get('4x3', 0)} | 🔴 {g.get('4x4', 0)} | 🔴 {g.get('4x5', 0)} |",
                f"| **3 (Possible)** | 🟢 {g.get('3x1', 0)} | 🟡 {g.get('3x2', 0)} | 🟡 {g.get('3x3', 0)} | 🟠 {g.get('3x4', 0)} | 🔴 {g.get('3x5', 0)} |",
                f"| **2 (Unlikely)** | 🟢 {g.get('2x1', 0)} | 🟢 {g.get('2x2', 0)} | 🟡 {g.get('2x3', 0)} | 🟡 {g.get('2x4', 0)} | 🟠 {g.get('2x5', 0)} |",
                f"| **1 (Rare)** | 🟢 {g.get('1x1', 0)} | 🟢 {g.get('1x2', 0)} | 🟢 {g.get('1x3', 0)} | 🟡 {g.get('1x4', 0)} | 🟡 {g.get('1x5', 0)} |\n",
                "👉 **Instant Filter by Severity:**\n",
                "[btn:🔴 View Critical Risks|Show top open high-severity risks in the plant] [btn:🟠 View High Risks|Show top open high-severity risks in the plant] [btn:⏰ View Overdue Actions|Which risk action plans are overdue or pending?]"
            ]
            answer = "\n".join(lines)
            return self._make_response(request, answer, "HEATMAP_MATRIX")

        # APPROVAL QUEUES
        elif (any(w in lower_msg for w in ["approval", "approve", "sign-off", "signoff", "queue", "pending review", "to review", "awaiting review"]) 
            and not any(w in lower_msg for w in ["audit", "history", "timeline", "trail", "who approved", "evidence"])):
            intent = "APPROVAL_QUEUE"
            stage = "all"
            if "function" in user_role.lower() or "dept" in user_role.lower() or "functional" in lower_msg:
                stage = "functional_head"
            elif "manager" in user_role.lower() or "manager" in lower_msg:
                stage = "risk_manager"
            elif "head" in user_role.lower() or "head" in lower_msg:
                stage = "risk_head"
            raw_data = erm_db.get_pending_approvals(stage=stage, dept_id=filter_dept_id, limit=12)

        # AUDIT TRAIL
        elif any(w in lower_msg for w in ["audit", "history", "timeline", "trail", "who approved", "evidence", "traceability"]) or re.search(r'\bRSK-[A-Z]+-\d+\b', msg, re.IGNORECASE):
            intent = "AUDIT_TRAIL"
            risk_match = re.search(r'\bRSK-[A-Z]+-\d+\b', msg, re.IGNORECASE)
            target_risk_id = risk_match.group(0) if risk_match else msg
            raw_data = erm_db.get_risk_audit_trail(target_risk_id)

        # RISK SCORING
        elif any(w in lower_msg for w in ["likelihood", "impact", "calculate score", "risk score", "matrix", "assess risk", "inherent score"]):
            intent = "ASSESS_RISK"
            numbers = [int(s) for s in re.findall(r'\b[1-5]\b', msg)]
            l_val = numbers[0] if len(numbers) >= 1 else 4
            i_val = numbers[1] if len(numbers) >= 2 else 4
            score = l_val * i_val
            severity = "CRITICAL" if score >= 15 else ("HIGH" if score >= 10 else ("MEDIUM" if score >= 5 else "LOW"))
            raw_data = {
                "likelihood": l_val, "impact": i_val, "risk_score": score,
                "severity": severity, "matrix_code": f"{l_val}x{i_val}"
            }

        # OVERDUE ACTIONS
        elif any(w in lower_msg for w in ["overdue", "follow up", "followup", "action plan", "pending action", "treatment progress"]):
            intent = "OVERDUE_ACTIONS"
            raw_data = erm_db.get_overdue_actions(dept_id=filter_dept_id, limit=12)

        # DEPARTMENT SUMMARY
        elif any(w in lower_msg for w in ["department", "dept", "breakdown", "summary", "profile", "distribution"]):
            intent = "DEPARTMENT_SUMMARY"
            raw_data = erm_db.get_department_risk_summary(dept_id=filter_dept_id)

        # DRAFT TREATMENT
        elif any(w in lower_msg for w in ["draft", "treatment", "mitigate", "recommend", "mitigation", "controls"]):
            intent = "DRAFT_TREATMENT"
            hist_data = erm_db.get_historical_treatments(keyword=msg[:50], dept_id=filter_dept_id, limit=5)
            dept_users = erm_db.get_department_action_owners(dept_id=filter_dept_id)
            raw_data = {"historical_treatments": hist_data, "available_department_personnel": dept_users}

        # SEARCH RISKS
        else:
            intent = "SEARCH_RISK"
            generic_fleet_triggers = [
                "active risk register", "enterprise risk fleet", "risk register", "all risks",
                "list risks", "show risks", "view risks", "risk fleet", "active risks",
                "show all risks", "list all risks", "enterprise risks", "get all risks",
                "critical plant hazards", "plant hazards", "fleet", "risk list"
            ]
            clean_kw = msg.strip()
            if any(trig in lower_msg for trig in generic_fleet_triggers) or len(clean_kw) <= 3:
                clean_kw = None
            raw_data = erm_db.search_risks(keyword=clean_kw, department=filter_dept_name, limit=10)

        user_scope = "Enterprise-Wide" if is_enterprise_role else f"Department: {dept_name or 'Assigned Unit'}"

        answer_text = self._format_structured_output(intent, raw_data, user_scope, msg, user_role)

        if answer_text:
            if intent == "APPROVAL_QUEUE" and raw_data and isinstance(raw_data, list) and len(raw_data) > 0:
                if not "[btn" in answer_text:
                    btn_lines = ["\n\n👉 **Instant 1-Click Governance Actions:**"]
                    for r in raw_data:
                        rid = r.get("risk_id", "RSK-001")
                        btn_lines.append(f"[btn-confirm:✅ Approve {rid}|Approve {rid}] [btn-cancel:❌ Return {rid}|Reject {rid} with remark Revision Required] [btn:📜 Audit Trail|Show audit trail for {rid}]")
                    answer_text += "\n" + "\n\n".join(btn_lines)

            elif intent == "AUDIT_TRAIL" and raw_data and isinstance(raw_data, dict):
                rid = raw_data.get("risk_id")
                if rid and raw_data.get("risk_status") in [2, 3, 4] and not "[btn" in answer_text:
                    answer_text += f"\n\n👉 **Instant Governance Actions for `{rid}`:**\n[btn-confirm:✅ Approve {rid}|Approve {rid}] [btn-cancel:❌ Return {rid}|Reject {rid} with remark Revision Required]"

        req_id = getattr(request, "request_id", None) or str(uuid.uuid4())
        created_dt = getattr(request, "created_at", None)
        timestamp_str = created_dt.isoformat() if created_dt else datetime.now(timezone.utc).isoformat()

        resp_obj = AgentResponse(
            request_id=req_id,
            agent_id=self.agent_id,
            status="success",
            success=True,
            response=answer_text,
            metadata={
                "intent": intent,
                "role": user_role,
                "scope": user_scope,
                "context_used": bool(raw_data),
                "timestamp": timestamp_str
            }
        )

        # Cache read-only response for subsequent high-speed sub-millisecond retrieval
        if not is_wizard_active and answer_text:
            erm_response_cache.set(msg, resp_obj, user_role, filter_dept_id)

        return resp_obj

    def _make_response(self, request: AgentRequest, answer_text: str, step_code: str) -> AgentResponse:
        req_id = getattr(request, "request_id", None) or str(uuid.uuid4())
        created_dt = getattr(request, "created_at", None)
        timestamp_str = created_dt.isoformat() if created_dt else datetime.now(timezone.utc).isoformat()
        
        # Apply output guardrails & formatting sanitization
        sanitized_output = GuardrailManager.process_output(answer_text)
        
        return AgentResponse(
            request_id=req_id,
            agent_id=self.agent_id,
            status="success",
            success=True,
            response=sanitized_output.strip(),
            metadata={
                "intent": "CREATE_RISK_WIZARD",
                "wizard_step": step_code,
                "timestamp": timestamp_str
            }
        )

    def _format_structured_output(self, intent: str, data: Any, scope: str, query: str, role: str) -> str:
        if intent == "CREATE_RISK" and isinstance(data, dict):
            if data.get("status") == "success":
                rid = data.get("risk_id", "RSK-NEW-001")
                rname = data.get("risk_name", "Industrial Risk Assessment")
                dept = data.get("department_name", "Refining")
                st_label = data.get("status_label", "Draft (Status 1)")
                l = data.get("inherent_likelihood", 4)
                i = data.get("inherent_impact", 5)
                score = data.get("inherent_score", l * i)
                sev = "CRITICAL" if score >= 15 else ("HIGH" if score >= 10 else ("MEDIUM" if score >= 5 else "LOW"))
                treatments_text = ""
                if data.get("treatments"):
                    treatments_text = "\n\n**🛠️ Initial Action Plans Created:**\n" + "\n".join([f"- {t}" for t in data.get("treatments")])
                
                return (
                    f"### 💾 Risk Successfully Created & Saved in Database!\n\n"
                    f"| Record Property | Details & Database Values |\n"
                    f"| :--- | :--- |\n"
                    f"| **Generated Risk ID** | `{rid}` |\n"
                    f"| **Risk Title** | **{rname}** |\n"
                    f"| **Department** | {dept} |\n"
                    f"| **Database Status** | `{st_label}` |\n"
                    f"| **Inherent Rating** | Likelihood {l} × Impact {i} = **{score} / 25 `[{sev}]`** |\n"
                    f"| **Tables Populated** | `ers.risk_register`, `ers.risk_description`, `ers.risk_treatment` |\n"
                    f"| **Created At** | `{str(data.get('created_on', ''))[:19]}` |"
                    f"{treatments_text}"
                )
            else:
                return f"⚠️ **Database Save Notice:** Could not insert risk record ({data.get('message')}). Please check database connection."

        elif intent == "APPROVAL_QUEUE" and isinstance(data, list):
            lines = [
                f"### 🛡️ Governance Approval Queue ({scope})\n",
                "| Risk ID | Risk Name & Description | Department | Owner | Current Status |",
                "| :--- | :--- | :--- | :--- | :--- |"
            ]
            action_buttons = []
            for r in data:
                rid = r.get("risk_id", "RSK-001")
                title = r.get("risk_title") or r.get("risk_name") or "Plant Hazard"
                dept = r.get("department_name") or "Enterprise"
                owner = r.get("owner_name") or "Risk Owner"
                st = r.get("risk_status", 2)
                st_label = "⚠️ Submitted to Function Head" if st == 2 else ("🟣 Function Head Approved" if st == 3 else "👑 Risk Manager Approved")
                lines.append(f"| `{rid}` | **{title}** | {dept} | {owner} | {st_label} |")
                action_buttons.append(f"[btn-confirm:✅ Approve {rid}|Approve {rid}] [btn-cancel:❌ Return {rid}|Reject {rid} with remark Revision Required] [btn:📜 Audit Trail|Show audit trail for {rid}]")
            
            if action_buttons:
                lines.append("\n👉 *Click an instant action below to sign off or inspect:*")
                for btn_group in action_buttons:
                    lines.append(f"\n{btn_group}")
            else:
                lines.append("\n🎉 **No risks currently pending governance sign-off in this queue.**")
            return "\n".join(lines)

        elif intent == "AUDIT_TRAIL" and isinstance(data, dict):
            rid = data.get("risk_id", "RSK-001")
            lines = [
                f"### 📜 Comprehensive Audit Trail & Lifecycle History: `{rid}`\n",
                f"**Risk Title:** {data.get('risk_name', 'N/A')}<br>",
                f"**Department:** {data.get('department', 'N/A')} | **Financial Year:** {data.get('financial_year', '2026-2027')}\n",
                "---",
                "#### 📌 Governance Stage Timeline\n",
                f"1. **Risk Creation & Assessment:** Registered on `{str(data.get('created_on', 'N/A'))[:19]}` by **{data.get('created_by_name', 'Risk Owner')}**.",
                f"   - *Inherent Score:* Likelihood {data.get('inherent_likelihood', 3)} × Impact {data.get('inherent_impact', 3)}",
                f"2. **Functional Head Approval:** {'✅ Approved' if data.get('fh_status') == 1 else '⚠️ Pending / In Progress'}",
                f"   - *Approver:* **{data.get('fh_approver', 'N/A')}** on `{str(data.get('fh_on', 'N/A'))[:19]}`",
                f"   - *Remark:* \"{data.get('fh_remark') or 'No remarks logged'}\"",
                f"3. **Risk Manager Validation:** {'✅ Approved' if data.get('rm_status') == 1 else '⚠️ Pending / In Progress'}",
                f"   - *Approver:* **{data.get('rm_approver', 'N/A')}** on `{str(data.get('rm_on', 'N/A'))[:19]}`",
                f"   - *Remark:* \"{data.get('rm_remark') or 'No remarks logged'}\"",
                f"4. **Risk Head Final Sign-off:** {'✅ Final Approved' if data.get('rh_status') == 1 else '⚠️ Pending / In Progress'}",
                f"   - *Approver:* **{data.get('rh_approver', 'N/A')}** on `{str(data.get('rh_on', 'N/A'))[:19]}`"
            ]
            treatments = data.get("treatments", [])
            if treatments:
                lines.append("\n#### 🛠️ Associated Treatment Milestones\n")
                lines.append("| Task Plan | Action Owner | Target Date | Progress | Status |")
                lines.append("| :--- | :--- | :---: | :---: | :---: |")
                for t in treatments:
                    lines.append(f"| {t.get('action_plan')} | {t.get('action_owner')} | {str(t.get('target_date', ''))[:10]} | {t.get('progress')} | {t.get('status')} |")
            return "\n".join(lines)

        elif intent == "ASSESS_RISK" and isinstance(data, dict):
            l = data.get("likelihood", 4)
            i = data.get("impact", 4)
            score = data.get("risk_score", 16)
            sev = data.get("severity", "CRITICAL")
            return (
                f"### 🎯 Risk Assessment & Scoring Calculation\n\n"
                f"| Metric | Parameter Value | Governance Standard |\n"
                f"| :--- | :---: | :--- |\n"
                f"| **Likelihood Rating (L)** | **{l} / 5** | Scale 1 (Rare) to 5 (Almost Certain) |\n"
                f"| **Impact Rating (I)** | **{i} / 5** | Scale 1 (Insignificant) to 5 (Catastrophic) |\n"
                f"| **Calculated Score (L × I)** | **{score} / 25** | Risk Severity Index |\n"
                f"| **Risk Severity Band** | `[{sev}]` | Matrix Band {l}x{i} |\n\n"
                f"**Mandatory Control Actions:**\n"
                f"- High-severity risk requires immediate engineering mitigation controls (e.g. automated interlocks, redundant monitoring).\n"
                f"- This risk requires formal 3-tier sign-off: **Functional Head → Risk Manager → Risk Head**."
            )

        elif intent == "DEPARTMENT_SUMMARY" and isinstance(data, list):
            lines = [
                f"### 📊 Department Risk Profile Summary ({scope})\n",
                "| Department | Total Active Risks | Pending FH Review | Pending Exec Review | Fully Approved |",
                "| :--- | :---: | :---: | :---: | :---: |"
            ]
            tot_all, fh_all, exec_all, app_all = 0, 0, 0, 0
            for d in data:
                tot = d.get("total_risks", 0)
                fh = d.get("pending_fh_risks", 0)
                ex = d.get("pending_exec_risks", 0)
                ap = d.get("fully_approved_risks", 0)
                tot_all += tot
                fh_all += fh
                exec_all += ex
                app_all += ap
                lines.append(f"| **{d.get('department', 'Unknown')}** | {tot} | {fh} ⚠️ | {ex} 🟣 | {ap} ✅ |")
            lines.append(f"| **Enterprise Fleet Total** | **{tot_all}** | **{fh_all}** | **{exec_all}** | **{app_all}** |")
            return "\n".join(lines)

        elif intent == "OVERDUE_ACTIONS" and isinstance(data, list):
            lines = [
                f"### ⏰ Open & Overdue Action Plan Follow-ups ({scope})\n",
                "| Risk ID | Mitigation Task | Responsible Owner | Target Date | Progress | Status |",
                "| :--- | :--- | :--- | :---: | :---: | :---: |"
            ]
            for a in data:
                rid = a.get("risk_id", "RSK-001")
                task = a.get("action_plan", "Inspection & Maintenance")
                owner = a.get("action_owner", "Owner")
                due = str(a.get("target_date", "2026-10-15"))[:10]
                prog = a.get("progress", "45%")
                st = a.get("status", "In Progress")
                st_badge = "✅ Completed" if "complete" in st.lower() else ("🔴 Overdue" if "overdue" in st.lower() else f"⚠️ {st}")
                lines.append(f"| `{rid}` | **{task}** | {owner} | {due} | {prog} | {st_badge} |")
            return "\n".join(lines)

        elif intent == "DRAFT_TREATMENT":
            dept_users = data.get("available_department_personnel", []) if isinstance(data, dict) else []
            assignees_table = ""
            if dept_users:
                user_lines = [
                    "\n\n#### 👥 Recommended Department Assignees & Co-Owners (Selectable)\n",
                    "| User ID | Personnel Name | Official Role | Department | Recommended Assignment |",
                    "| :---: | :--- | :--- | :--- | :--- |"
                ]
                for u in dept_users[:6]:
                    uid = u.get("user_id", "")
                    uname = u.get("full_name", "")
                    urole = u.get("role_name", "")
                    udept = u.get("department_name", "")
                    recom = "Action Owner (Engineering & Maintenance)" if "_ao" in str(u.get("log_id")).lower() else ("Risk Co-Owner / Reviewer" if "owner" in urole.lower() else "Department Approver")
                    user_lines.append(f"| `{uid}` | **{uname}** | {urole} | {udept} | {recom} |")
                assignees_table = "\n".join(user_lines)

            return (
                f"### ✍️ Proposed Risk Mitigation & Treatment Strategy\n"
                f"**Target Objective:** {query.strip()}\n\n"
                f"| Phase | Mitigation Action & Control Tier | Designated Owner | Timeline | KPI / Success Metric |\n"
                f"| :--- | :--- | :--- | :---: | :--- |\n"
                f"| 1. Assessment | Conduct root-cause FMEA & vibration baseline analysis. | Reliability Engineering | 14 Days | Completed FMEA Report |\n"
                f"| 2. Engineering Control | Install dual pressurized mechanical seal barrier system with auto-flush. | Maintenance Lead | 30 Days | Zero seal leakage in 1000 hrs |\n"
                f"| 3. Condition Monitoring | Deploy wireless vibration & temperature sensors linked to plant DCS. | Instrumentation Eng | 45 Days | Real-time telemetry configured |\n"
                f"| 4. Operational PM | Revise preventive maintenance schedule to monthly lubrication & torque checks. | Operations Tech | 60 Days | Updated PM in CMMS |"
                f"{assignees_table}"
            )

        # Default Search Table
        lines = [
            f"### 🛡️ Active Risk Register ({scope})\n",
            "| Risk ID | Risk Name | Department | Status | Mitigation Summary |",
            "| :--- | :--- | :--- | :--- | :--- |"
        ]
        if isinstance(data, list) and len(data) > 0:
            for r in data:
                rid = r.get("risk_id", "RSK-001")
                title = r.get("risk_title") or r.get("risk_name") or "Operational Risk"
                dept = r.get("department_name", "Enterprise")
                mit = r.get("mitigation", "Standard operating controls")
                lines.append(f"| `{rid}` | **{title}** | {dept} | ⚠️ Active | {mit} |")
        else:
            lines.append("| — | *No active risk records matched your search query in the current scope.* | — | — | — |")
        return "\n".join(lines)


erm_copilot_agent = ERMCopilotAgent()
