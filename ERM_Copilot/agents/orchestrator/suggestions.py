"""
Role-Wise Question Suggestion Service for ERM Copilot.
Provides deterministic, role-tailored question suggestions for all authenticated ERM roles.
Designed with a provider abstraction for seamless future extensibility.
"""
from abc import ABC, abstractmethod
from typing import List, Set, Dict

APPROVER_SUGGESTIONS: List[str] = [
    "Show risks pending my approval",
    "Show high and critical risks",
    "Show risks that need my action"
]

APPROVER_ROLES: Set[str] = {
    "Functional Head",
    "Risk Manager",
    "Risk Head"
}

ROLE_SUGGESTIONS: Dict[str, List[str]] = {
    "Risk Owner": [
        "Create a new risk",
        "Show my open risks",
        "Show risks that need my action"
    ],
    "Action Owner": [
        "Show my pending actions",
        "Show my overdue actions",
        "Show my assigned risks"
    ],
    "Admin": [
        "Show overall risk status",
        "Show high and critical risks",
        "Show risks by department"
    ],
    "Auditor": [
        "Show audit trail for risk",
        "Show pending approvals",
        "Show all risks in the register"
    ],
    "Executive": [
        "Show executive risk profile",
        "Show high and critical risks",
        "Show risks by department"
    ]
}


def normalize_role(role: str) -> str:
    """Normalize raw role string to standard canonical ERM role name."""
    if not role or not isinstance(role, str):
        return ""
    r = role.strip().lower().replace("_", " ").replace("-", " ")
    
    if r in ["ro", "risk owner", "owner"]:
        return "Risk Owner"
    if r in ["fh", "functional head", "function head", "dept head", "department head"]:
        return "Functional Head"
    if r in ["rm", "risk manager", "manager"]:
        return "Risk Manager"
    if r in ["rh", "risk head", "cro", "chief risk officer", "head"]:
        return "Risk Head"
    if r in ["ao", "action owner", "actionee"]:
        return "Action Owner"
    if r in ["admin", "super admin", "superadmin", "administrator", "system admin"]:
        return "Admin"
    if r in ["audit", "auditor", "compliance"]:
        return "Auditor"
    if r in ["executive", "management", "c-suite", "board"]:
        return "Executive"
    
    return role.strip()


class SuggestionProvider(ABC):
    """Abstract base class for Copilot suggestion providers."""
    
    @abstractmethod
    def get_suggestions(self, role: str) -> List[str]:
        """Return exactly 3 suggested questions for the given authenticated role."""
        pass


class StaticSuggestionProvider(SuggestionProvider):
    """Deterministic static suggestion provider based on ERM role policies."""
    
    def get_suggestions(self, role: str) -> List[str]:
        canonical = normalize_role(role)
        if not canonical:
            return []
        
        # Approvers (FH, RM, RH) share the same unified suggestion set
        if canonical in APPROVER_ROLES:
            return list(APPROVER_SUGGESTIONS)
        
        # Other defined roles
        if canonical in ROLE_SUGGESTIONS:
            return list(ROLE_SUGGESTIONS[canonical])
        
        # Unknown or unsupported role -> return empty list (safe behavior)
        return []


# Global default provider instance
_default_provider: SuggestionProvider = StaticSuggestionProvider()


def get_role_suggestions(role: str) -> List[str]:
    """
    Public entry point to get exactly 3 Copilot question suggestions for an authenticated role.
    
    Args:
        role: Authenticated user's role (string).
        
    Returns:
        List[str]: Exactly 3 questions, or empty list [] if role is unknown/unsupported.
    """
    return _default_provider.get_suggestions(role)
