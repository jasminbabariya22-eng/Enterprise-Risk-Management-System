"""
Backward-compatibility forwarder for Risk Creation Agent.
Real implementation resides in `ERM_Copilot.agents.risk_creation`.
"""
from ERM_Copilot.agents.risk_creation.agent import (
    RiskCreationAgent,
    risk_creation_agent
)
from ERM_Copilot.agents.risk_creation.state import (
    RiskCreationState,
    RiskCreationSession
)
from ERM_Copilot.agents.risk_creation.scoring import RiskMatrixCalculator
from ERM_Copilot.agents.risk_creation.suggestions import (
    RiskSuggestionProvider,
    StaticRiskSuggestionProvider,
    static_suggestion_provider
)
from ERM_Copilot.agents.risk_creation.prompts import build_preview
from ERM_Copilot.agents.risk_creation.tools import (
    parse_target_date,
    parse_progress,
    detect_field_edits
)

from ERM_Copilot.agents.risk_creation.requirements import (
    FieldConstraint,
    FieldRequirement,
    RiskCreationRequirements,
    get_risk_creation_requirements
)
from ERM_Copilot.agents.risk_creation.extraction import (
    ExtractedRiskFields,
    extract_risk_fields
)
from ERM_Copilot.agents.risk_creation.completeness import (
    RiskCompletenessAssessment,
    assess_risk_completeness
)
from ERM_Copilot.agents.risk_creation.merge import (
    RiskMergeResult,
    merge_risk_draft
)

__all__ = [
    "RiskCreationAgent",
    "risk_creation_agent",
    "RiskCreationState",
    "RiskCreationSession",
    "RiskMatrixCalculator",
    "RiskSuggestionProvider",
    "StaticRiskSuggestionProvider",
    "static_suggestion_provider",
    "build_preview",
    "parse_target_date",
    "parse_progress",
    "detect_field_edits",
    "FieldConstraint",
    "FieldRequirement",
    "RiskCreationRequirements",
    "get_risk_creation_requirements",
    "ExtractedRiskFields",
    "extract_risk_fields",
    "RiskCompletenessAssessment",
    "assess_risk_completeness",
    "RiskMergeResult",
    "merge_risk_draft",
]
