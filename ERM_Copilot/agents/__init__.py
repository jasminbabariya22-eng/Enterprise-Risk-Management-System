"""
ERM Copilot Multi-Agent Framework.

Modular Architecture:
- orchestrator: Master ERMCopilotAgent and suggestion router
- approval: LangGraph 3-tier Governance Approval & Audit Agent
- risk_creation: 7-step ISO-31000 Risk Formulation & Scoring Agent
- treatment: Risk Treatment & Action Plan Lifecycle Agent
"""
from ERM_Copilot.agents.base import BaseAgent

# 1. Master Orchestrator
from ERM_Copilot.agents.orchestrator import (
    ERMCopilotAgent,
    erm_copilot_agent,
    ERM_SYSTEM_PROMPT,
    get_role_suggestions,
    normalize_role,
    APPROVER_SUGGESTIONS,
    ROLE_SUGGESTIONS
)

# 2. Approval Sub-Agent (LangGraph)
from ERM_Copilot.agents.approval import (
    approval_agent,
    ApprovalWorkflowAgent,
    ApprovalState,
    approve_or_reject_risk
)

# 3. Risk Creation Sub-Agent
from ERM_Copilot.agents.risk_creation import (
    risk_creation_agent,
    RiskCreationAgent,
    RiskCreationSession,
    RiskCreationState,
    RiskMatrixCalculator,
    build_preview
)

# 4. Treatment Sub-Agent
from ERM_Copilot.agents.treatment import (
    treatment_management_agent,
    TreatmentManagementAgent,
    TreatmentSession,
    TreatmentState
)

__all__ = [
    "BaseAgent",
    # Orchestrator
    "erm_copilot_agent",
    "ERMCopilotAgent",
    "ERM_SYSTEM_PROMPT",
    "get_role_suggestions",
    "normalize_role",
    "APPROVER_SUGGESTIONS",
    "ROLE_SUGGESTIONS",
    # Approval
    "approval_agent",
    "ApprovalWorkflowAgent",
    "ApprovalState",
    "approve_or_reject_risk",
    # Risk Creation
    "risk_creation_agent",
    "RiskCreationAgent",
    "RiskCreationSession",
    "RiskCreationState",
    "RiskMatrixCalculator",
    "build_preview",
    # Treatment
    "treatment_management_agent",
    "TreatmentManagementAgent",
    "TreatmentSession",
    "TreatmentState"
]
