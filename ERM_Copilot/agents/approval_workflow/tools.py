"""
Approval Tool Adapters for the Governed AI Harness.
Dispatches tool requests through ExecutionCoordinator enforcing RBAC,
parameter schemas, confirmation tokens, and audit recording.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ERM_Copilot.ai_harness.context import HarnessContext
from ERM_Copilot.ai_harness.execution import ExecutionCoordinator
from ERM_Copilot.agents.approval_workflow.state import ApprovalWorkflowSession

logger = logging.getLogger("ERM_Copilot.agents.approval_workflow.tools")


def execute_harness_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    session: ApprovalWorkflowSession,
    bypass_confirmation: bool = False,
) -> Dict[str, Any]:
    """
    Execute a registered AI harness tool under strict session context governance.
    Appends execution audit records to the session's tool call history.
    """
    context = HarnessContext.build_from_auth(
        user_id=str(session.user_id),
        user_role=session.user_role,
        dept_id=session.dept_id,
        dept_name=session.dept_name,
        session_id=session.session_id,
    )
    if session.pending_confirmation:
        context.confirmation_state = session.pending_confirmation

    try:
        result = ExecutionCoordinator.execute_tool(
            tool_name=tool_name,
            arguments=arguments,
            context=context,
            bypass_confirmation=bypass_confirmation,
        )
        session.tool_call_history.append({
            "tool_name": tool_name,
            "arguments": {k: v for k, v in arguments.items() if k not in ("approver_id", "user_id")},
            "success": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return result
    except Exception as e:
        session.tool_call_history.append({
            "tool_name": tool_name,
            "arguments": {k: v for k, v in arguments.items() if k not in ("approver_id", "user_id")},
            "success": False,
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        raise


def fetch_pending_approvals(session: ApprovalWorkflowSession, limit: int = 50) -> List[Dict[str, Any]]:
    """Fetch pending approvals for the caller's role and department scope."""
    role = session.user_role
    if not role:
        raise PermissionError("Authenticated role is missing from session context.")
    res = execute_harness_tool(
        tool_name="get_pending_approvals",
        arguments={
            "approver_role": role,
            "dept_id": session.dept_id,
            "limit": limit,
        },
        session=session,
    )
    if isinstance(res, list):
        return res
    return res.get("result", []) if isinstance(res, dict) else []


def fetch_risk_details(session: ApprovalWorkflowSession, risk_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve full risk details by identifier or code."""
    res = execute_harness_tool(
        tool_name="get_risk_details",
        arguments={
            "risk_id": risk_id,
            "dept_id": session.dept_id,
        },
        session=session,
    )
    if isinstance(res, dict):
        # Could be directly the risk dict or a wrapped result
        if "risk_id" in res or "risk_name" in res:
            return res
        return res.get("result")
    elif isinstance(res, list) and res:
        return res[0]
    return None


def fetch_risk_audit_trail(session: ApprovalWorkflowSession, risk_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve sequential approval audit trail and historical transitions."""
    res = execute_harness_tool(
        tool_name="get_risk_audit_trail",
        arguments={
            "risk_identifier": risk_id,
        },
        session=session,
    )
    if isinstance(res, dict):
        if "risk_id" in res or "fh_status" in res:
            return res
        return res.get("result")
    return None


def execute_governed_approval_decision(
    session: ApprovalWorkflowSession,
    risk_id: str,
    action: str,
    remark: str,
    bypass_confirmation: bool = False,
) -> Dict[str, Any]:
    """Execute approval or rejection mutation with verified identity and confirmation."""
    return execute_harness_tool(
        tool_name="approve_or_reject_risk",
        arguments={
            "risk_id": risk_id,
            "action": action,
            "remark": remark,
            "approver_id": int(session.user_id),
        },
        session=session,
        bypass_confirmation=bypass_confirmation,
    )
