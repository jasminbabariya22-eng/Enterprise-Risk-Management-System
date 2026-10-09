"""
Failure Taxonomy and Error Classification Engine.
Maps any evaluation failure to its exact technical or behavioral root cause.
"""
from enum import Enum
from typing import Dict, Any, Optional


class FailureCategory(str, Enum):
    INTENT_FAILURE = "INTENT_FAILURE"
    AGENT_ROUTING_FAILURE = "AGENT_ROUTING_FAILURE"
    TOOL_SELECTION_FAILURE = "TOOL_SELECTION_FAILURE"
    TOOL_PARAMETER_FAILURE = "TOOL_PARAMETER_FAILURE"
    DATA_RETRIEVAL_FAILURE = "DATA_RETRIEVAL_FAILURE"
    RBAC_FAILURE = "RBAC_FAILURE"
    HALLUCINATION = "HALLUCINATION"
    GROUNDING_FAILURE = "GROUNDING_FAILURE"
    BUSINESS_RULE_FAILURE = "BUSINESS_RULE_FAILURE"
    RESPONSE_QUALITY_FAILURE = "RESPONSE_QUALITY_FAILURE"
    CONTEXT_FAILURE = "CONTEXT_FAILURE"
    SECURITY_FAILURE = "SECURITY_FAILURE"
    UI_FAILURE = "UI_FAILURE"
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"


class EvaluationFailure(Exception):
    """Exception raised when an evaluation test case fails assertions."""

    def __init__(self, category: FailureCategory, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(f"[{category.value}] {message}")
        self.category = category
        self.message = message
        self.details = details or {}
