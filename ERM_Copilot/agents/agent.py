"""
Backward-compatibility forwarder for ERM Master Orchestrator Agent.
Real implementation resides in `ERM_Copilot.agents.orchestrator`.
"""
from ERM_Copilot.agents.orchestrator.agent import (
    ERMCopilotAgent,
    erm_copilot_agent,
    ERM_SYSTEM_PROMPT
)
from ERM_Copilot.agents.orchestrator.suggestions import (
    get_role_suggestions,
    normalize_role,
    SuggestionProvider,
    StaticSuggestionProvider
)

__all__ = [
    "ERMCopilotAgent",
    "erm_copilot_agent",
    "ERM_SYSTEM_PROMPT",
    "get_role_suggestions",
    "normalize_role",
    "SuggestionProvider",
    "StaticSuggestionProvider"
]
