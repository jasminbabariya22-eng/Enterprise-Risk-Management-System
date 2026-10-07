"""
LangGraph StateGraph Workflow & Agent Orchestrator for Conversational Approvals.
"""
import re
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from ERM_Copilot.models.contracts import AgentRequest, AgentResponse
from ERM_Copilot.agents.approval.state import ApprovalState
from ERM_Copilot.agents.approval.nodes import (
    extract_approval_request,
    validate_required_fields,
    capture_continuation_input,
    execute_approval_tool,
    CANCEL_WORDS,
)

logger = logging.getLogger("ERM_Copilot.agents.approval.graph")


# Try importing LangGraph if installed in environment
try:
    from langgraph.graph import StateGraph, END, START
    HAS_LANGGRAPH = True
except ImportError:
    HAS_LANGGRAPH = False
    START = "__start__"
    END = "__end__"


class ApprovalWorkflowGraph:
    """
    Workflow Graph for Conversational Risk Approvals & Rejections.
    Executes the following deterministic state transitions:
    
    START
      ↓
    extract_approval_request
      ↓
    validate_required_fields
      ↓
    [All fields ready & confirmed?]
      ├── YES → execute_approval_tool → END
      └── NO (Awaiting remark / risk_id / confirmation) → return response to user
    """
    def __init__(self):
        self._compiled_graph = self._build_graph()

    def _build_graph(self):
        if HAS_LANGGRAPH:
            builder = StateGraph(ApprovalState)
            builder.add_node("extract", extract_approval_request)
            builder.add_node("validate", validate_required_fields)
            builder.add_node("continue_turn", capture_continuation_input)
            builder.add_node("execute", execute_approval_tool)

            builder.add_edge(START, "extract")
            builder.add_edge("extract", "validate")
            
            def should_execute(state: ApprovalState) -> str:
                if state.get("confirmed"):
                    return "execute"
                return END

            builder.add_conditional_edges("continue_turn", should_execute, {
                "execute": "execute",
                END: END
            })
            builder.add_edge("execute", END)

            return builder.compile()
        return None

    def run_turn(self, state: ApprovalState) -> ApprovalState:
        """Execute a conversational step through the state graph."""
        is_continuing = any([
            state.get("awaiting_risk_id"),
            state.get("awaiting_action"),
            state.get("awaiting_remark"),
            state.get("awaiting_confirmation")
        ])

        if is_continuing:
            state = capture_continuation_input(state)
        else:
            state = extract_approval_request(state)
            if not state.get("cancelled") and not state.get("is_completed"):
                state = validate_required_fields(state)

        # If user just confirmed, execute tool
        if state.get("confirmed") and not state.get("is_completed"):
            state = execute_approval_tool(state)

        return state


class ApprovalWorkflowAgent:
    """
    Conversational Agent coordinating the LangGraph approval workflow.
    Preserves multi-turn state sessions per user/conversation.
    """
    def __init__(self):
        self.agent_id = "agent_approval_langgraph_v1"
        self.name = "LangGraph Risk Governance Approval Agent"
        self.workflow = ApprovalWorkflowGraph()
        self._sessions: Dict[str, ApprovalState] = {}

    def get_session_key(self, request: AgentRequest) -> str:
        """Resolve consistent session key for user/conversation session."""
        raw_uid = getattr(request, "session_id", None) or getattr(request, "user_id", None) or (request.metadata or {}).get("session_id") or (request.metadata or {}).get("user_id") or ""
        return str(raw_uid).strip()

    def is_approval_trigger(self, msg: str) -> bool:
        """Detect if message intends to start or confirm an approval or rejection decision."""
        if not msg:
            return False
        lower = msg.lower().strip()

        # Pure read-only queue request check
        pure_queue_triggers = [
            "approval queue", "approvals queue", "show approval queue", "view approval queue",
            "show pending approvals", "list pending approvals", "what are my pending approvals",
            "show approvals", "list approvals", "view approvals", "pending approvals", "pending approval"
        ]
        has_specific_risk = bool(re.search(r'\b(?:RSK-[A-Z0-9_-]+-\d+|[A-Z]{2,5}-\d{2,5}|RSK-\d+)\b', msg, re.IGNORECASE)) or bool(re.search(r'\brisk\s+\d+\b', lower))

        if any(lower == q or lower.startswith(q + " ") for q in pure_queue_triggers):
            if not has_specific_risk:
                return False

        # If user mentions approve/reject action along with a specific risk ID
        has_action_verb = any(w in lower for w in [
            "approve", "approval", "reject", "rejection", "sign off", "signoff", "sign-off",
            "return risk", "return for revision", "don't approve", "dont approve"
        ])

        if has_action_verb and has_specific_risk:
            return True

        # Conversational starts
        if any(lower.startswith(w) for w in [
            "approve", "reject", "sign off", "signoff", "sign-off",
            "please approve", "please reject", "i approve", "i reject",
            "i want to approve", "i want to reject", "i would like to approve", "i would like to reject",
            "i don't approve", "i dont approve", "return risk", "return for revision",
            "confirm approve", "confirm approval", "confirm reject", "confirm rejection"
        ]):
            return True

        if any(w in lower for w in [
            "approve risk", "reject risk", "signoff risk", "sign-off risk",
            "approve hr-", "reject hr-", "approve rsk-", "reject rsk-",
            "confirm approve", "confirm approval", "confirm reject", "confirm rejection"
        ]):
            return True

        return False

    def is_cancellation(self, msg: str) -> bool:
        """Detect if message is a cancellation command."""
        lower = msg.lower().strip()
        return lower in CANCEL_WORDS or lower.startswith("cancel")

    def is_session_active(self, session_key: str) -> bool:
        """Check if an active multi-turn approval session exists."""
        key = str(session_key).strip()
        if not key:
            return False
        if key in self._sessions:
            sess = self._sessions[key]
            return not sess.get("is_completed", False) and not sess.get("cancelled", False)
        return False

    def get_session(self, session_key: str) -> Optional[ApprovalState]:
        return self._sessions.get(str(session_key).strip())

    def clear_session(self, session_key: str) -> None:
        key = str(session_key).strip()
        if key in self._sessions:
            del self._sessions[key]

    def process(self, request: AgentRequest) -> AgentResponse:
        """
        Process a conversational approval turn.
        """
        req_id = getattr(request, "request_id", None) or str(uuid.uuid4())
        session_key = self.get_session_key(request)
        msg = (request.message or "").strip()

        # Strict authentication check
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
        
        # Check if user is starting a brand new risk command with a specific risk ID
        from ERM_Copilot.agents.approval.nodes import RISK_ID_PATTERN
        has_new_risk_id = bool(RISK_ID_PATTERN.search(msg))

        # Load or initialize session state
        state = self._sessions.get(session_key)
        if not state or state.get("is_completed") or state.get("cancelled") or has_new_risk_id:
            state = ApprovalState(
                session_id=session_key,
                user_id=str(auth_uid),
                user_role=request.user_role,
                dept_id=request.metadata.get("dept_id") if request.metadata else None,
                dept_name=request.metadata.get("dept_name") if request.metadata else None,
                risk_id=None,
                action=None,
                remark=None,
                awaiting_risk_id=False,
                awaiting_action=False,
                awaiting_remark=False,
                awaiting_confirmation=False,
                confirmed=False,
                cancelled=False,
                is_completed=False,
                api_result=None,
                error=None,
                response_message=None,
                step_code=None,
                last_user_message=msg,
                messages=[]
            )
        else:
            state["last_user_message"] = msg
            state["user_id"] = str(auth_uid)
            if request.user_role:
                state["user_role"] = request.user_role

        # Run through workflow graph
        updated_state = self.workflow.run_turn(state)
        self._sessions[session_key] = updated_state

        resp_text = updated_state.get("response_message") or "Decision processing update."
        step_code = updated_state.get("step_code") or "APPROVAL_PROCESSING"
        
        # If completed or cancelled, cleanup session
        if updated_state.get("is_completed") or updated_state.get("cancelled"):
            self.clear_session(session_key)

        return AgentResponse(
            request_id=req_id,
            agent_id=self.agent_id,
            status="success" if not updated_state.get("error") else "error",
            success=not bool(updated_state.get("error")),
            response=resp_text,
            metadata={
                "intent": step_code,
                "risk_id": updated_state.get("risk_id"),
                "action": updated_state.get("action"),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )


# Global singleton instance
approval_agent = ApprovalWorkflowAgent()
