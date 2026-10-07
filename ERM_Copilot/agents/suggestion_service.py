"""
Backward-compatibility forwarder for Role Suggestion Service.
Real implementation resides in `ERM_Copilot.agents.orchestrator.suggestions`.
"""
from ERM_Copilot.agents.orchestrator.suggestions import (
    get_role_suggestions,
    normalize_role,
    SuggestionProvider,
    StaticSuggestionProvider,
    APPROVER_SUGGESTIONS,
    APPROVER_ROLES,
    ROLE_SUGGESTIONS
)

__all__ = [
    "get_role_suggestions",
    "normalize_role",
    "SuggestionProvider",
    "StaticSuggestionProvider",
    "APPROVER_SUGGESTIONS",
    "APPROVER_ROLES",
    "ROLE_SUGGESTIONS"
]
