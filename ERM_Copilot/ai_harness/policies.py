"""
RBAC and Governance Policies for ERM AI Harness Tools.
Enforces role-based permissions, execution categories, and confirmation mandates.
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Set
from ERM_Copilot.ai_harness.exceptions import AuthorizationError


class ToolCategory(str, Enum):
    READ_ONLY = "read_only"
    SEARCH = "search"
    STATE_CHANGING = "state_changing"
    APPROVAL = "approval"
    SYSTEM = "system"


# Standard ERM Roles recognized across the platform
ROLE_RISK_OWNER = "Risk Owner"
ROLE_FUNCTIONAL_HEAD = "Functional Head"
ROLE_RISK_MANAGER = "Risk Manager"
ROLE_RISK_HEADER = "Risk Header"
ROLE_RISK_CHAMPION = "Risk Champion"
ROLE_EXECUTIVE_CEO = "Executive / CEO"
ROLE_BOARD_AUDIT = "Board & Audit Committee"
ROLE_AUDITOR = "Auditor"
ROLE_ADMIN = "Admin"
ROLE_SUPER_ADMIN = "Super Admin"

ALL_ROLES: List[str] = [
    ROLE_RISK_OWNER,
    ROLE_FUNCTIONAL_HEAD,
    ROLE_RISK_MANAGER,
    ROLE_RISK_HEADER,
    ROLE_RISK_CHAMPION,
    ROLE_EXECUTIVE_CEO,
    ROLE_BOARD_AUDIT,
    ROLE_AUDITOR,
    ROLE_ADMIN,
    ROLE_SUPER_ADMIN,
]

# Approver roles authorized to perform governance approvals
APPROVER_ROLES: List[str] = [
    ROLE_FUNCTIONAL_HEAD,
    ROLE_RISK_MANAGER,
    ROLE_RISK_HEADER,
    ROLE_ADMIN,
    ROLE_SUPER_ADMIN,
    ROLE_EXECUTIVE_CEO,
]

# Roles authorized to modify risks and treatments
CREATOR_ROLES: List[str] = [
    ROLE_RISK_OWNER,
    ROLE_FUNCTIONAL_HEAD,
    ROLE_RISK_MANAGER,
    ROLE_RISK_HEADER,
    ROLE_ADMIN,
    ROLE_SUPER_ADMIN,
]


def normalize_role(role_name: str) -> str:
    """Normalize role string to canonical title."""
    if not role_name:
        return ""
    r = role_name.strip().lower()
    if "super admin" in r:
        return ROLE_SUPER_ADMIN
    if "admin" in r:
        return ROLE_ADMIN
    if "functional head" in r or "fh" in r or "hod" in r or "dept head" in r:
        return ROLE_FUNCTIONAL_HEAD
    if "risk manager" in r or "rm" in r:
        return ROLE_RISK_MANAGER
    if "risk head" in r or "rh" in r or "champion" in r:
        return ROLE_RISK_HEADER
    if "executive" in r or "ceo" in r or "md" in r:
        return ROLE_EXECUTIVE_CEO
    if "board" in r or "committee" in r:
        return ROLE_BOARD_AUDIT
    if "auditor" in r or "audit" in r:
        return ROLE_AUDITOR
    if "owner" in r or "maker" in r or "initiator" in r or "user" in r:
        return ROLE_RISK_OWNER
    return role_name.strip()


def is_role_authorized_for_tool(user_role: str, allowed_roles: Optional[List[str]]) -> bool:
    """
    Check whether a user's verified role is permitted to run a specific tool.
    If allowed_roles is None or empty, all authenticated users are permitted.
    """
    if not allowed_roles:
        return True
    
    canonical_user_role = normalize_role(user_role)
    canonical_allowed = {normalize_role(r) for r in allowed_roles}

    # Super Admin and Admin bypass normal role constraints
    if canonical_user_role in (ROLE_SUPER_ADMIN, ROLE_ADMIN):
        return True

    return canonical_user_role in canonical_allowed


def enforce_tool_rbac(tool_name: str, user_role: str, allowed_roles: Optional[List[str]]) -> None:
    """Raise AuthorizationError if the user's role is not authorized."""
    if not is_role_authorized_for_tool(user_role, allowed_roles):
        raise AuthorizationError(
            f"User role '{user_role}' is not authorized to execute tool '{tool_name}'. "
            f"Allowed roles: {', '.join(allowed_roles or [])}"
        )
