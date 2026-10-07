"""
Production ERM Copilot & Automation Master Orchestrator Agent.
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
from ERM_Copilot.agents.risk_creation import risk_creation_agent, RiskCreationAgent
from ERM_Copilot.agents.treatment import treatment_management_agent, TreatmentManagementAgent
from ERM_Copilot.agents.approval import approval_agent, ApprovalWorkflowAgent
from ERM_Copilot.agents.orchestrator.suggestions import get_role_suggestions
from ERM_Copilot.agents.orchestrator.prompts import ERM_SYSTEM_PROMPT
from ERM_Copilot.models.contracts import AgentRequest, AgentResponse, RequestContext
from ERM_Copilot.services.db_service import erm_db
from ERM_Copilot.services.api_client import erm_api_client
from ERM_Copilot.gateway.client import portkey_client
from ERM_Copilot.guardrails.manager import GuardrailManager
from ERM_Copilot.transform.query_transformer import QueryTransformer
from ERM_Copilot.cache.response_cache import erm_response_cache
from ERM_Copilot.formatters import response_formatter

logger = logging.getLogger("ERM_Copilot.agents.orchestrator.agent")


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
        raw_user_id = getattr(request, "user_id", None)
        if raw_user_id is None:
            raw_user_id = params.get("user_id")
        user_id = raw_user_id
        session_key = str(raw_user_id).strip() if raw_user_id else ""

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

        # --- 2. DELEGATION TO TREATMENT MANAGEMENT AGENT ---
        is_treatment_active = (
            treatment_management_agent.is_session_active(session_key)
            or treatment_management_agent.is_add_treatment_trigger(msg)
            or treatment_management_agent.is_update_progress_trigger(msg)
            or treatment_management_agent.is_reassign_owner_trigger(msg)
            or treatment_management_agent.is_list_treatments_trigger(msg)
            or (treatment_management_agent.is_cancellation(msg) and treatment_management_agent.is_session_active(session_key))
        )
        if is_treatment_active:
            resp = treatment_management_agent.process(request)
            if resp.metadata.get("intent") in ["TREATMENT_CREATED", "PROGRESS_UPDATED", "OWNER_REASSIGNED"]:
                erm_response_cache.invalidate_all()
            return resp

        # --- 2.1 DELEGATION TO RISK CREATION AGENT ---
        is_risk_creation_active = (
            risk_creation_agent.is_session_active(session_key)
            or risk_creation_agent.is_start_trigger(msg)
            or (risk_creation_agent.is_cancellation(msg) and risk_creation_agent.is_session_active(session_key))
        )
        if is_risk_creation_active:
            resp = risk_creation_agent.process(request)
            if resp.metadata.get("wizard_step") == "WIZARD_COMPLETED":
                erm_response_cache.invalidate_all()
            return resp

        # --- 2.2 DELEGATION TO LANGGRAPH APPROVAL AGENT ---
        is_approval_active = (
            approval_agent.is_session_active(session_key)
            or approval_agent.is_approval_trigger(msg)
            or (approval_agent.is_cancellation(msg) and approval_agent.is_session_active(session_key))
        )
        if is_approval_active:
            resp = approval_agent.process(request)
            if resp.metadata.get("intent") in ["APPROVAL_EXECUTED", "REJECTION_EXECUTED"]:
                erm_response_cache.invalidate_all()
            return resp

        # --- 3. HIGH-SPEED RESPONSE CACHE LOOKUP ---
        cached_resp = erm_response_cache.get(msg, user_role, filter_dept_id)
        if cached_resp:
            cached_text = cached_resp.response if hasattr(cached_resp, "response") else str(cached_resp)
            return self._make_response(request, cached_text, "CACHE_HIT")

        # 1. INTENT DETECTION & DIRECT QUERIES
        intent = "GENERAL_RISK_QUERY"
        raw_data = None
        db_context = ""

        # 0b. PROACTIVE MORNING BRIEFING & MY PENDING TASKS
        if any(w in lower_msg for w in ["briefing", "morning briefing", "my pending", "my tasks", "what's pending for me", "my daily update", "overview for me", "need my action", "needs my action", "need action", "show risks that need my action"]):
            intent = "DAILY_BRIEFING"
            u_num = user_id if isinstance(user_id, int) else (int(user_id) if str(user_id).isdigit() else None)
            briefing = erm_db.get_user_daily_briefing(user_id=u_num, role_name=user_role, dept_id=filter_dept_id)
            items = briefing.get("items", [])
            answer = response_formatter.format_daily_briefing(
                user_role=user_role,
                briefing_type=briefing.get('briefing_type', 'Action Queue'),
                pending_count=briefing.get('pending_count', 0),
                items=items
            )
            return self._make_response(request, answer, "DAILY_BRIEFING")

        # 0b. ROLE-SPECIFIC WELCOME GREETING & CONVERSATIONAL SMALL TALK
        clean_prompt = " ".join(re.findall(r'[a-zA-Z0-9]+', lower_msg))
        
        greeting_patterns = [
            "hi", "hii", "hello", "hey", "greetings", "good morning", "good afternoon", "good evening",
            "help", "menu", "start", "start copilot", "welcome", "how are you", "how are you doing",
            "how do you do", "how r u", "hows it going", "how is it going", "whats up", "what is up",
            "kaise ho", "kaisa hai", "namaste"
        ]
        is_greeting = any(clean_prompt == gp or clean_prompt.startswith(gp + " ") or clean_prompt.endswith(" " + gp) for gp in greeting_patterns) or clean_prompt in greeting_patterns

        # Identity & Capabilities questions
        is_identity_query = any(phrase in lower_msg for phrase in [
            "who are you", "what can you do", "what are your capabilities", "tell me about yourself",
            "what is your role", "what is erm copilot", "how can you help", "what do you do"
        ])

        # Appreciation & pleasantries
        is_appreciation = clean_prompt in [
            "thank you", "thanks", "thx", "thank u", "great", "awesome", "perfect", "good job",
            "well done", "nice", "ok", "okay", "got it", "understood", "bye", "goodbye"
        ]

        if is_identity_query or is_greeting:
            if any(q in lower_msg for q in ["how are you", "how are you doing", "how r u", "hows it going", "how is it going", "whats up"]):
                answer = (
                    f"### 👋 I'm doing great, thank you for asking!\n\n"
                    f"I am your **ERM Risk Intelligence Copilot**, actively monitoring the Enterprise Risk Register for **{dept_name or 'Operations'}**.\n\n"
                    f"Here is what I can assist you with right now:\n"
                    f"- 🛡️ **Search & Track Risks:** Look up open high-severity risks or specific plant hazards.\n"
                    f"- ✍️ **Draft Treatments:** Generate 4-tier industrial mitigation plans & assign Action Owners.\n"
                    f"- 📊 **Assess & Score:** Calculate 5×5 Likelihood × Impact matrix ratings.\n"
                    f"- 📥 **Approvals & Governance:** Review pending Stage 2 (FH), Stage 3 (RM), or Stage 4 (RH) approvals.\n\n"
                    f"👉 *Try one of the quick actions below:*\n\n"
                    f"[btn:🛡️ Show Top Open Risks|Show top open high-severity risks] "
                    f"[btn:📝 Draft Mitigation Plan|Help draft a mitigation treatment plan for my risk] "
                    f"[btn:📊 5×5 Risk Heatmap|Show 5x5 heatmap matrix]"
                )
                return self._make_response(request, answer, "CONVERSATIONAL_SMALL_TALK")
            else:
                answer = self._get_role_specific_welcome(user_role, dept_name, is_enterprise_role)
                return self._make_response(request, answer, "ROLE_WELCOME_MENU")

        elif is_appreciation:
            answer = (
                f"### 🛡️ You're very welcome!\n\n"
                f"I'm here 24/7 to help you manage and mitigate risks across **{dept_name or 'Enterprise Operations'}**.\n\n"
                f"Let me know whenever you need to search the register, draft a treatment plan, or verify approval queues."
            )
            return self._make_response(request, answer, "CONVERSATIONAL_APPRECIATION")

        # 0c. RESUBMIT RISK FOR GOVERNANCE APPROVAL (Clears prior FH, RM, RH approvals)
        is_resubmit_trigger = (
            any(w in lower_msg for w in ["resubmit", "re-submit", "send for approval", "submit risk", "submit to functional head", "submit to fh", "submit to function head"])
            and bool(re.search(r'\b(?:RSK-[A-Z0-9]+-\d{1,4}|[A-Z]{2,5}-\d{1,5}|RSK-\d+)\b', msg, re.IGNORECASE) or any(w.isdigit() for w in msg.split()))
        )
        if is_resubmit_trigger:
            risk_match = re.search(r'\b(?:RSK-[A-Z0-9]+-\d{1,4}|[A-Z]{2,5}-\d{1,5}|RSK-\d+)\b', msg, re.IGNORECASE)
            target_risk_id = risk_match.group(0).upper() if risk_match else msg.strip()
            u_num = user_id if isinstance(user_id, int) else (int(user_id) if str(user_id).isdigit() else 8)
            res = erm_db.resubmit_risk(risk_id=target_risk_id, user_id=u_num)
            if res.get("success"):
                erm_response_cache.invalidate_all()
                answer = response_formatter.format_resubmit_success(res)
                return self._make_response(request, answer, "RISK_RESUBMITTED")
            else:
                return self._make_response(request, f"⚠️ **Resubmission Notice:** {res.get('message', 'Could not resubmit risk.')}", "ERROR")

        # 0d. INTERACTIVE 5x5 RISK MATRIX HEATMAP
        elif any(w in lower_msg for w in ["heatmap", "5x5", "heat map", "risk matrix", "matrix heatmap", "distribution"]):
            dist = erm_db.get_risk_matrix_distribution(dept_id=filter_dept_id)
            scope_title = filter_dept_name or "Enterprise Fleet"
            answer = response_formatter.format_heatmap_matrix(dist, scope_title)
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
        elif any(w in lower_msg for w in ["audit", "history", "timeline", "trail", "who approved", "evidence", "traceability"]) or re.search(r'\b(?:RSK|HR)-[A-Z0-9]+-\d+\b', msg, re.IGNORECASE) or re.search(r'\bRSK-\d+\b', msg, re.IGNORECASE):
            intent = "AUDIT_TRAIL"
            risk_match = re.search(r'\b(?:RSK|HR)-[A-Z0-9]+-\d+\b', msg, re.IGNORECASE) or re.search(r'\bRSK-\d+\b', msg, re.IGNORECASE) or re.search(r'\b[A-Z]{2,5}-\d{2,5}\b', msg)
            target_risk_id = risk_match.group(0).upper() if risk_match else msg
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

        # DEPARTMENT SUMMARY & OVERALL STATUS
        elif any(w in lower_msg for w in ["department", "dept", "breakdown", "summary", "profile", "distribution", "overall risk status", "overall status", "risks by department"]):
            intent = "DEPARTMENT_SUMMARY"
            raw_data = erm_db.get_department_risk_summary(dept_id=filter_dept_id)

        # DRAFT TREATMENT
        elif any(w in lower_msg for w in ["draft", "treatment", "mitigate", "recommend", "mitigation", "controls"]):
            intent = "DRAFT_TREATMENT"
            hist_data = erm_db.get_historical_treatments(keyword=msg[:50], dept_id=filter_dept_id, limit=5)
            dept_users = erm_db.get_department_action_owners(dept_id=filter_dept_id)
            raw_data = {"historical_treatments": hist_data, "available_department_personnel": dept_users}

        # SEARCH RISKS & HIGH SEVERITY LISTINGS
        else:
            intent = "SEARCH_RISK"
            
            # Check if query is asking for high-severity or critical risks
            is_critical = any(w in lower_msg for w in ["critical risk", "critical risks", "view critical", "critical plant", "critical hazards"])
            is_high_sev = is_critical or any(w in lower_msg for w in [
                "high and critical", "high & critical", "high and critical risks", "high-severity", "high severity", "high risk", "high risks", "view high",
                "top open", "top risk", "top risks", "top high", "critical plant hazards",
                "top open high-severity risks in the plant", "top open high-severity risks"
            ])
            
            generic_fleet_triggers = [
                "active risk register", "enterprise risk fleet", "risk register", "all risks",
                "list risks", "show risks", "view risks", "risk fleet", "active risks",
                "show all risks", "list all risks", "enterprise risks", "get all risks",
                "plant hazards", "fleet", "risk list", "department risks", "department risk register",
                "show active risks in my department", "show active risk register",
                "open risks", "my open risks", "show my open risks", "show open risks",
                "my risks", "show my risks", "open risk", "my active risks", "show active risks",
                "assigned risks", "show my assigned risks"
            ]

            if is_critical:
                raw_data = erm_db.search_risks(severity_level="critical", department=filter_dept_name, limit=10)
            elif is_high_sev:
                raw_data = erm_db.search_risks(severity_level="high_severity", department=filter_dept_name, limit=10)
            elif any(trig in lower_msg for trig in generic_fleet_triggers) or len(lower_msg.strip()) <= 3:
                raw_data = erm_db.search_risks(department=filter_dept_name, limit=10)
            else:
                # Extract clean topic/keyword using intelligent QueryTransformer
                clean_kw = QueryTransformer.extract_search_keyword(msg)
                raw_data = erm_db.search_risks(keyword=clean_kw, department=filter_dept_name, limit=10)
                # If no results found in user's specific department, search across all departments
                if not raw_data and filter_dept_name and clean_kw:
                    raw_data = erm_db.search_risks(keyword=clean_kw, department=None, limit=10)

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
        if answer_text:
            erm_response_cache.set(msg, resp_obj, user_role, filter_dept_id)

        return resp_obj

    def _get_role_specific_welcome(self, user_role: str, dept_name: Optional[str], is_enterprise_role: bool) -> str:
        role_lower = (user_role or "").lower()
        dept_str = dept_name or "Plant Operations"
        
        # Get exactly 3 role-tailored suggestions from the centralized suggestion service
        suggestions = get_role_suggestions(user_role)
        btn_section = ""
        if suggestions:
            btn_list = [f"[btn:{s}|{s}]" for s in suggestions]
            btn_section = f"👉 **Quick Actions ({len(suggestions)} Suggestions):**\n\n" + " ".join(btn_list)

        # 1. RISK OWNER
        if "owner" in role_lower or role_lower in ["ro", "risk owner", "risk_owner"]:
            return (
                f"### 👋 Welcome, Risk Owner!\n"
                f"I am your **AI Risk Intelligence Copilot**. I assist frontline engineers and department teams in formulating structured operational hazards, calculating 5×5 matrix scores, and tracking action follow-ups.\n\n"
                f"🏢 **Assigned Department:** `{dept_str}`\n"
                f"🛡️ **Governance Scope:** `5-Step Risk Registration & Mitigation Planning`\n\n"
                f"{btn_section}"
            )

        # 2. FUNCTIONAL HEAD
        elif "function" in role_lower or "dept head" in role_lower or role_lower in ["fh", "functional head", "functional_head"]:
            return (
                f"### 👋 Welcome, Functional Head!\n"
                f"I am your **Stage 2 Governance AI Copilot**. I assist you with reviewing newly submitted department risks, technical mitigation adequacy assessments, and 1-click approvals.\n\n"
                f"🏢 **Governed Department:** `{dept_str}`\n"
                f"🛡️ **Governance Scope:** `Stage 2 Technical Review & Department Approval Queue`\n\n"
                f"{btn_section}"
            )

        # 3. RISK MANAGER
        elif "manager" in role_lower or role_lower in ["rm", "risk manager", "risk_manager"]:
            return (
                f"### 👋 Welcome, Risk Manager!\n"
                f"I am your **Cross-Department Risk AI Advisor**. I assist you in Stage 3 audits, 4-tier matrix validation, enterprise risk aggregation, and mitigation adequacy verification.\n\n"
                f"🏢 **Governance Scope:** `Multi-Department & Enterprise (Stage 3 Review Queue)`\n\n"
                f"{btn_section}"
            )

        # 4. RISK HEAD / CRO
        elif "head" in role_lower or "cro" in role_lower or "chief" in role_lower:
            return (
                f"### 👋 Welcome, Chief Risk Officer (Risk Head)!\n"
                f"I am your **Executive AI Risk Advisor**. I assist you in Stage 4 final executive approvals, board-level risk profile summaries, plant exposure heatmaps, and high-impact escalations.\n\n"
                f"🏛️ **Governance Scope:** `Enterprise-Wide (Stage 4 Final Executive Sign-off)`\n\n"
                f"{btn_section}"
            )

        # 5. ACTION OWNER
        elif "action" in role_lower or role_lower in ["ao", "action owner", "action_owner"]:
            return (
                f"### 👋 Welcome, Action Owner!\n"
                f"I am your **Action Tracking & Mitigation Copilot**. I assist you with tracking assigned mitigation tasks, updating progress milestones, and monitoring target completion dates.\n\n"
                f"🏢 **Assigned Department:** `{dept_str}`\n"
                f"🛡️ **Governance Scope:** `Mitigation Execution & Progress Reporting`\n\n"
                f"{btn_section}"
            )

        # 6. AUDITOR
        elif "audit" in role_lower:
            return (
                f"### 👋 Welcome, Compliance Auditor!\n"
                f"I am your **Audit & Regulatory Compliance AI Assistant**. I assist you in reconstructing immutable audit trails, verifying approval timestamps, and ensuring complete governance traceability.\n\n"
                f"📜 **Governance Scope:** `Enterprise-Wide Audit Reconstruction & Evidence Verification`\n\n"
                f"{btn_section}"
            )

        # 7. MANAGEMENT / C-SUITE
        elif any(k in role_lower for k in ["management", "executive", "c-suite", "board"]):
            return (
                f"### 👋 Welcome, Executive Management!\n"
                f"I am your **Strategic Risk Intelligence Advisor**. I provide high-level enterprise risk exposure profiles, plant hazard summaries, and regulatory compliance metrics.\n\n"
                f"📊 **Governance Scope:** `Board & Executive Governance Overview`\n\n"
                f"{btn_section}"
            )

        # 8. ADMIN
        elif "admin" in role_lower:
            return (
                f"### 👋 Welcome, ERM Administrator!\n"
                f"I am your **Enterprise Risk Management (ERM) System Copilot**. I assist you with platform health, department oversight, and enterprise risk metrics.\n\n"
                f"🏢 **System Scope:** `Global Administration`\n\n"
                f"{btn_section}"
            )

        # 9. UNKNOWN / DEFAULT
        else:
            return (
                f"### 👋 Welcome to ERM Copilot!\n"
                f"I am your **Enterprise Risk Management (ERM) AI Intelligence Agent**. I assist you with risk formulation, 5×5 matrix scoring, approval queues, audit trails, and mitigation workflows.\n\n"
                f"🏢 **Current Scope:** `{dept_str}`\n\n"
                f"{btn_section if btn_section else 'Please ask any risk management question or select an option from the navigation menu.'}"
            )

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
                "intent": step_code,
                "wizard_step": step_code,
                "timestamp": timestamp_str
            }
        )

    def _format_structured_output(self, intent: str, data: Any, scope: str, query: str, role: str) -> str:
        if intent == "CREATE_RISK" and isinstance(data, dict):
            if data.get("status") == "success":
                return response_formatter.format_risk_creation_success(data)
            else:
                return f"⚠️ **Database Save Notice:** Could not insert risk record ({data.get('message')}). Please check database connection."

        elif intent == "APPROVAL_QUEUE" and isinstance(data, list):
            return response_formatter.format_approval_queue(data, scope)

        elif intent == "AUDIT_TRAIL" and isinstance(data, dict):
            return response_formatter.format_audit_trail(data)

        elif intent == "ASSESS_RISK" and isinstance(data, dict):
            return response_formatter.format_risk_scoring(data)

        elif intent == "DEPARTMENT_SUMMARY" and isinstance(data, list):
            return response_formatter.format_department_summary(data, scope)

        elif intent == "OVERDUE_ACTIONS" and isinstance(data, list):
            return response_formatter.format_overdue_actions(data, scope)

        elif intent == "DRAFT_TREATMENT":
            return response_formatter.format_treatment_strategy(query, data)

        # Default Search Output
        if isinstance(data, list) and len(data) > 0:
            return response_formatter.format_risk_register_list(data, scope)
        else:
            suggestions = get_role_suggestions(role)
            return response_formatter.format_no_results(query, scope, suggestions)


erm_copilot_agent = ERMCopilotAgent()
