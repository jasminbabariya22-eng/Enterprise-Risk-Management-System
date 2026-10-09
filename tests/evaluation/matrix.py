"""
Role × Intent × Task Matrix for ERM Copilot.
Defines explicit authorization, expected agent, expected tool, and behavioral outcomes for all role-intent pairs.
"""
from typing import Dict, Any, List, Optional
from tests.evaluation.taxonomy import ERMRole, ERMIntent, OperationType


ROLE_INTENT_MATRIX: Dict[str, Dict[str, Any]] = {
    # -------------------------------------------------------------
    # 1. RISK OWNER
    # -------------------------------------------------------------
    f"{ERMRole.RISK_OWNER.value}::{ERMIntent.GET_MY_RISKS.value}": {
        "role": ERMRole.RISK_OWNER.value,
        "intent": ERMIntent.GET_MY_RISKS.value,
        "task": "View own assigned and open risks",
        "operation": OperationType.READ.value,
        "allowed": True,
        "expected_agent": "orchestrator",
        "expected_tool": "get_my_risks",
        "expected_behavior": "Return only risks authored or owned by user",
    },
    f"{ERMRole.RISK_OWNER.value}::{ERMIntent.SEARCH_RISKS.value}": {
        "role": ERMRole.RISK_OWNER.value,
        "intent": ERMIntent.SEARCH_RISKS.value,
        "task": "Search risks within own department",
        "operation": OperationType.SEARCH.value,
        "allowed": True,
        "expected_agent": "orchestrator",
        "expected_tool": "search_risks",
        "expected_behavior": "Return matching risks scoped to department permissions",
    },
    f"{ERMRole.RISK_OWNER.value}::{ERMIntent.CREATE_RISK.value}": {
        "role": ERMRole.RISK_OWNER.value,
        "intent": ERMIntent.CREATE_RISK.value,
        "task": "Formulate and persist a new risk entry",
        "operation": OperationType.STATE_CHANGE.value,
        "allowed": True,
        "expected_agent": "risk_creation_agent",
        "expected_tool": "save_risk",
        "expected_behavior": "Engage multi-turn ISO-31000 risk creation workflow",
    },
    f"{ERMRole.RISK_OWNER.value}::{ERMIntent.CREATE_TREATMENT.value}": {
        "role": ERMRole.RISK_OWNER.value,
        "intent": ERMIntent.CREATE_TREATMENT.value,
        "task": "Add mitigation treatment action plan to risk",
        "operation": OperationType.STATE_CHANGE.value,
        "allowed": True,
        "expected_agent": "treatment_management_agent",
        "expected_tool": "save_treatment",
        "expected_behavior": "Engage treatment formulation workflow",
    },
    f"{ERMRole.RISK_OWNER.value}::{ERMIntent.APPROVE_RISK.value}": {
        "role": ERMRole.RISK_OWNER.value,
        "intent": ERMIntent.APPROVE_RISK.value,
        "task": "Attempt approval signoff",
        "operation": OperationType.APPROVAL.value,
        "allowed": False,
        "expected_agent": "approval_workflow",
        "expected_tool": "approve_or_reject_risk",
        "expected_behavior": "Deny execution and alert user that role is not authorized to sign off approvals",
    },
    f"{ERMRole.RISK_OWNER.value}::{ERMIntent.REJECT_RISK.value}": {
        "role": ERMRole.RISK_OWNER.value,
        "intent": ERMIntent.REJECT_RISK.value,
        "task": "Attempt risk rejection",
        "operation": OperationType.REJECTION.value,
        "allowed": False,
        "expected_agent": "approval_workflow",
        "expected_tool": "approve_or_reject_risk",
        "expected_behavior": "Deny execution with authorization error",
    },

    # -------------------------------------------------------------
    # 2. FUNCTIONAL HEAD
    # -------------------------------------------------------------
    f"{ERMRole.FUNCTIONAL_HEAD.value}::{ERMIntent.GET_PENDING_APPROVALS.value}": {
        "role": ERMRole.FUNCTIONAL_HEAD.value,
        "intent": ERMIntent.GET_PENDING_APPROVALS.value,
        "task": "View Stage 2 approval queue",
        "operation": OperationType.READ.value,
        "allowed": True,
        "expected_agent": "orchestrator",
        "expected_tool": "get_pending_approvals",
        "expected_behavior": "Return Stage 2 risks pending Functional Head signoff",
    },
    f"{ERMRole.FUNCTIONAL_HEAD.value}::{ERMIntent.APPROVE_RISK.value}": {
        "role": ERMRole.FUNCTIONAL_HEAD.value,
        "intent": ERMIntent.APPROVE_RISK.value,
        "task": "Approve Stage 2 risk to advance to Stage 3 RM",
        "operation": OperationType.APPROVAL.value,
        "allowed": True,
        "expected_agent": "approval_workflow",
        "expected_tool": "approve_or_reject_risk",
        "expected_behavior": "Request confirmation token, advance risk_status to 3 upon confirmation",
    },
    f"{ERMRole.FUNCTIONAL_HEAD.value}::{ERMIntent.REJECT_RISK.value}": {
        "role": ERMRole.FUNCTIONAL_HEAD.value,
        "intent": ERMIntent.REJECT_RISK.value,
        "task": "Return Stage 2 risk with mandatory remark",
        "operation": OperationType.REJECTION.value,
        "allowed": True,
        "expected_agent": "approval_workflow",
        "expected_tool": "approve_or_reject_risk",
        "expected_behavior": "Mandate return remark, transition status to 5 (Returned), queue notification",
    },

    # -------------------------------------------------------------
    # 3. RISK MANAGER
    # -------------------------------------------------------------
    f"{ERMRole.RISK_MANAGER.value}::{ERMIntent.GET_PENDING_APPROVALS.value}": {
        "role": ERMRole.RISK_MANAGER.value,
        "intent": ERMIntent.GET_PENDING_APPROVALS.value,
        "task": "View Stage 3 approval queue",
        "operation": OperationType.READ.value,
        "allowed": True,
        "expected_agent": "orchestrator",
        "expected_tool": "get_pending_approvals",
        "expected_behavior": "Return Stage 3 risks pending Risk Manager review",
    },
    f"{ERMRole.RISK_MANAGER.value}::{ERMIntent.APPROVE_RISK.value}": {
        "role": ERMRole.RISK_MANAGER.value,
        "intent": ERMIntent.APPROVE_RISK.value,
        "task": "Approve Stage 3 risk to advance to Stage 4 RH",
        "operation": OperationType.APPROVAL.value,
        "allowed": True,
        "expected_agent": "approval_workflow",
        "expected_tool": "approve_or_reject_risk",
        "expected_behavior": "Validate FH approval passed, transition risk_status to 4 upon confirmation",
    },

    # -------------------------------------------------------------
    # 4. RISK HEAD / RISK CHAMPION
    # -------------------------------------------------------------
    f"{ERMRole.RISK_HEAD.value}::{ERMIntent.GET_PENDING_APPROVALS.value}": {
        "role": ERMRole.RISK_HEAD.value,
        "intent": ERMIntent.GET_PENDING_APPROVALS.value,
        "task": "View Stage 4 approval queue",
        "operation": OperationType.READ.value,
        "allowed": True,
        "expected_agent": "orchestrator",
        "expected_tool": "get_pending_approvals",
        "expected_behavior": "Return Stage 4 risks pending final executive signoff",
    },
    f"{ERMRole.RISK_HEAD.value}::{ERMIntent.APPROVE_RISK.value}": {
        "role": ERMRole.RISK_HEAD.value,
        "intent": ERMIntent.APPROVE_RISK.value,
        "task": "Final signoff activating the risk",
        "operation": OperationType.APPROVAL.value,
        "allowed": True,
        "expected_agent": "approval_workflow",
        "expected_tool": "approve_or_reject_risk",
        "expected_behavior": "Transition risk_status to 1 (Fully Approved/Active), complete signoff",
    },

    # -------------------------------------------------------------
    # 5. AUDITOR
    # -------------------------------------------------------------
    f"{ERMRole.AUDITOR.value}::{ERMIntent.VIEW_AUDIT_TRAIL.value}": {
        "role": ERMRole.AUDITOR.value,
        "intent": ERMIntent.VIEW_AUDIT_TRAIL.value,
        "task": "Inspect governance timeline and audit log",
        "operation": OperationType.READ.value,
        "allowed": True,
        "expected_agent": "orchestrator",
        "expected_tool": "get_risk_details",
        "expected_behavior": "Provide full read-only history of transitions and remarks",
    },
    f"{ERMRole.AUDITOR.value}::{ERMIntent.CREATE_RISK.value}": {
        "role": ERMRole.AUDITOR.value,
        "intent": ERMIntent.CREATE_RISK.value,
        "task": "Attempt to create a risk entry",
        "operation": OperationType.STATE_CHANGE.value,
        "allowed": False,
        "expected_agent": "risk_creation_agent",
        "expected_tool": "save_risk",
        "expected_behavior": "Deny mutation; auditor role is strictly read-only",
    },
    f"{ERMRole.AUDITOR.value}::{ERMIntent.APPROVE_RISK.value}": {
        "role": ERMRole.AUDITOR.value,
        "intent": ERMIntent.APPROVE_RISK.value,
        "task": "Attempt approval signoff",
        "operation": OperationType.APPROVAL.value,
        "allowed": False,
        "expected_agent": "approval_workflow",
        "expected_tool": "approve_or_reject_risk",
        "expected_behavior": "Deny execution with RBAC authorization error",
    }
}


def lookup_matrix(role: str, intent: str) -> Optional[Dict[str, Any]]:
    """Lookup expected matrix entry for a role and intent."""
    key = f"{role}::{intent}"
    return ROLE_INTENT_MATRIX.get(key)
