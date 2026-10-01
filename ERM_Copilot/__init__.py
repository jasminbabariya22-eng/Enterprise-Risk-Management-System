"""
ERM Copilot AI Agent Module.
Clean, decoupled enterprise AI assistant package for Enterprise Risk Management.
"""
from ERM_Copilot.agents.agent import erm_copilot_agent, ERMCopilotAgent
from ERM_Copilot.agents.base import BaseAgent
from ERM_Copilot.models.contracts import AgentRequest, AgentResponse, RequestContext
from ERM_Copilot.models.schemas import RiskItem, RiskTreatmentPlan, RiskActionFollowup, ERMQueryResult
from ERM_Copilot.services.db_service import erm_db, ERMDatabaseService
from ERM_Copilot.services.api_client import erm_api_client, ERMFastAPIClient
from ERM_Copilot.config.settings import settings

from ERM_Copilot.feedback.models import FeedbackEntry, FeedbackSummary
from ERM_Copilot.feedback.service import FeedbackService, erm_feedback_service

__all__ = [
    "erm_copilot_agent",
    "ERMCopilotAgent",
    "BaseAgent",
    "AgentRequest",
    "AgentResponse",
    "RequestContext",
    "RiskItem",
    "RiskTreatmentPlan",
    "RiskActionFollowup",
    "ERMQueryResult",
    "erm_db",
    "ERMDatabaseService",
    "erm_api_client",
    "ERMFastAPIClient",
    "settings",
    "FeedbackEntry",
    "FeedbackSummary",
    "FeedbackService",
    "erm_feedback_service"
]

