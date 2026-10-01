"""
Abstract Base Agent class for ERM Copilot.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from ERM_Copilot.models.contracts import AgentRequest, AgentResponse, RequestContext


class BaseAgent(ABC):
    """
    Abstract Base Class for all ERM agents.
    """
    def __init__(
        self,
        agent_id: str,
        name: str,
        description: str,
        capabilities: List[str]
    ):
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.capabilities = capabilities

    @abstractmethod
    def execute(self, request: AgentRequest, context: RequestContext) -> Any:
        pass
