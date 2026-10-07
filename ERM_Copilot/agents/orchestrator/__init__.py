"""
ERM Copilot Master Orchestrator Package.
"""
from ERM_Copilot.agents.orchestrator.agent import ERMCopilotAgent, erm_copilot_agent
from ERM_Copilot.agents.orchestrator.prompts import ERM_SYSTEM_PROMPT
from ERM_Copilot.agents.orchestrator.suggestions import (
    get_role_suggestions,
    normalize_role,
    APPROVER_SUGGESTIONS,
    ROLE_SUGGESTIONS
)

__all__ = [
    "ERMCopilotAgent",
    "erm_copilot_agent",
    "ERM_SYSTEM_PROMPT",
    "get_role_suggestions",
    "normalize_role",
    "APPROVER_SUGGESTIONS",
    "ROLE_SUGGESTIONS"
]
