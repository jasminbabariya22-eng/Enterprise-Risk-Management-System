"""
Safe Risk Draft Merge Module.
Merges newly extracted risk fields into an existing RiskCreationSession draft non-destructively,
respecting server-side context, tracking field provenance, and handling explicit corrections.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from ERM_Copilot.agents.risk_creation.extraction import ExtractedRiskFields
from ERM_Copilot.agents.risk_creation.scoring import RiskMatrixCalculator
from ERM_Copilot.agents.risk_creation.state import RiskCreationSession

logger = logging.getLogger("ERM_Copilot.agents.risk_creation.merge")


class RiskMergeResult(BaseModel):
    """
    Result of merging extracted fields into the active risk draft.
    Tracks modified fields, conflicting inputs, and whether corrections were applied.
    """
    modified_fields: List[str] = Field(default_factory=list)
    conflicts: Dict[str, str] = Field(default_factory=dict)
    applied_corrections: List[str] = Field(default_factory=list)
    ignored_server_overrides: List[str] = Field(default_factory=list)
    success: bool = True
    message: str = ""


def merge_risk_draft(
    draft: RiskCreationSession,
    extracted: ExtractedRiskFields,
    server_context: Dict[str, Any]
) -> RiskMergeResult:
    """
    Safely and non-destructively merge extracted attributes into the existing draft.
    
    Invariants:
    1. Authenticated user_id and dept_id from server_context ALWAYS override any user/model values.
    2. Previously accepted valid fields are NEVER overwritten by None or empty string.
    3. Mathematical assessment scores are automatically re-calculated upon rating changes.
    4. Field provenance is recorded.
    """
    result = RiskMergeResult()
    now_utc = datetime.now(timezone.utc)

    # 1. Enforce Server-Side Identity Context (Non-negotiable security boundary)
    auth_user_id = server_context.get("user_id") or draft.user_id
    auth_dept_id = server_context.get("dept_id") or draft.dept_id
    auth_dept_name = server_context.get("dept_name") or draft.dept_name
    auth_user_role = server_context.get("user_role") or server_context.get("role") or draft.user_role

    if auth_user_id:
        draft.user_id = auth_user_id
    if auth_dept_id:
        draft.dept_id = auth_dept_id
    if auth_dept_name:
        draft.dept_name = auth_dept_name
    if auth_user_role:
        draft.user_role = auth_user_role

    # 2. Risk Name / Title
    if extracted.risk_name and extracted.risk_name.strip():
        new_val = extracted.risk_name.strip()
        if draft.risk_name and draft.risk_name != new_val:
            if extracted.is_correction and extracted.corrected_field in ["risk_name", "title"]:
                draft.risk_name = new_val
                draft.field_provenance["risk_name"] = "user_corrected"
                result.applied_corrections.append("risk_name")
                result.modified_fields.append("risk_name")
            else:
                # Retain existing if not explicit correction, or accept if current is generic
                if draft.risk_name in ["Operational Hazard", "Draft Risk", "Operational Risk"]:
                    draft.risk_name = new_val
                    draft.field_provenance["risk_name"] = "user_stated"
                    result.modified_fields.append("risk_name")
        elif not draft.risk_name:
            draft.risk_name = new_val
            draft.field_provenance["risk_name"] = "user_stated"
            result.modified_fields.append("risk_name")

    # 3. Risk Description
    if extracted.risk_description and extracted.risk_description.strip():
        new_desc = extracted.risk_description.strip()
        if draft.risk_description and draft.risk_description != new_desc:
            if extracted.is_correction and extracted.corrected_field in ["risk_description", "description"]:
                draft.risk_description = new_desc
                draft.field_provenance["risk_description"] = "user_corrected"
                result.applied_corrections.append("risk_description")
                result.modified_fields.append("risk_description")
            elif len(new_desc) > len(draft.risk_description):
                draft.risk_description = new_desc
                draft.field_provenance["risk_description"] = "user_stated"
                result.modified_fields.append("risk_description")
        elif not draft.risk_description:
            draft.risk_description = new_desc
            draft.field_provenance["risk_description"] = "user_stated"
            result.modified_fields.append("risk_description")

    # 4. Inherent Assessment (Likelihood & Impact)
    inh_updated = False
    if extracted.inherent_likelihood is not None:
        if 1 <= extracted.inherent_likelihood <= 5:
            if draft.inherent_likelihood != extracted.inherent_likelihood:
                draft.inherent_likelihood = extracted.inherent_likelihood
                draft.field_provenance["inherent_likelihood"] = "user_stated"
                result.modified_fields.append("inherent_likelihood")
                inh_updated = True
        else:
            result.conflicts["inherent_likelihood"] = f"Inherent Likelihood must be 1-5, got {extracted.inherent_likelihood}."

    if extracted.inherent_impact is not None:
        if 1 <= extracted.inherent_impact <= 5:
            if draft.inherent_impact != extracted.inherent_impact:
                draft.inherent_impact = extracted.inherent_impact
                draft.field_provenance["inherent_impact"] = "user_stated"
                result.modified_fields.append("inherent_impact")
                inh_updated = True
        else:
            result.conflicts["inherent_impact"] = f"Inherent Impact must be 1-5, got {extracted.inherent_impact}."

    if inh_updated and draft.inherent_likelihood and draft.inherent_impact:
        draft.update_inherent_assessment(draft.inherent_likelihood, draft.inherent_impact)
        draft.field_provenance["inherent_score"] = "calculated"
        result.modified_fields.append("inherent_score")

    # 5. Mitigation
    if extracted.mitigation and extracted.mitigation.strip():
        new_mit = extracted.mitigation.strip()
        if not draft.mitigation or (extracted.is_correction and extracted.corrected_field == "mitigation"):
            draft.mitigation = new_mit
            draft.field_provenance["mitigation"] = "user_corrected" if extracted.is_correction else "user_stated"
            result.modified_fields.append("mitigation")

    # 6. Current / Residual Assessment
    cur_updated = False
    if extracted.current_likelihood is not None:
        if 1 <= extracted.current_likelihood <= 5:
            if draft.current_likelihood != extracted.current_likelihood:
                draft.current_likelihood = extracted.current_likelihood
                draft.field_provenance["current_likelihood"] = "user_stated"
                result.modified_fields.append("current_likelihood")
                cur_updated = True
        else:
            result.conflicts["current_likelihood"] = f"Current Likelihood must be 1-5, got {extracted.current_likelihood}."

    if extracted.current_impact is not None:
        if 1 <= extracted.current_impact <= 5:
            if draft.current_impact != extracted.current_impact:
                draft.current_impact = extracted.current_impact
                draft.field_provenance["current_impact"] = "user_stated"
                result.modified_fields.append("current_impact")
                cur_updated = True
        else:
            result.conflicts["current_impact"] = f"Current Impact must be 1-5, got {extracted.current_impact}."

    if cur_updated and draft.current_likelihood and draft.current_impact:
        draft.update_current_assessment(draft.current_likelihood, draft.current_impact)
        draft.field_provenance["current_score"] = "calculated"
        result.modified_fields.append("current_score")

    # 7. Action Plan
    if extracted.action_plan and extracted.action_plan.strip():
        new_act = extracted.action_plan.strip()
        if not draft.action_plan or (extracted.is_correction and extracted.corrected_field == "action_plan"):
            draft.action_plan = new_act
            draft.field_provenance["action_plan"] = "user_corrected" if extracted.is_correction else "user_stated"
            result.modified_fields.append("action_plan")

    # 8. Target Date
    if extracted.target_date and extracted.target_date.strip():
        draft.target_date = extracted.target_date.strip()
        draft.field_provenance["target_date"] = "user_stated"
        result.modified_fields.append("target_date")

    # 9. Progress
    if extracted.progress is not None and 0 <= extracted.progress <= 100:
        draft.progress = extracted.progress
        draft.field_provenance["progress"] = "user_stated"
        result.modified_fields.append("progress")

    # 10. Submission Mode & Status
    if extracted.submission_mode:
        draft.submission_mode = extracted.submission_mode
        if extracted.submission_mode == "submit":
            draft.status_id = 2
            draft.status_name = "Submitted to Functional Head"
        else:
            draft.status_id = 1
            draft.status_name = "Draft"
        draft.field_provenance["status_id"] = "user_stated"
        result.modified_fields.append("status_id")

    # 11. Co-Owner & Action Owner Names (If present in extracted)
    from ERM_Copilot.ai_harness.tool_registry import _handle_lookup_eligible_owners
    if extracted.risk_co_owner_name and not draft.risk_co_owner_name:
        try:
            res_co = _handle_lookup_eligible_owners(
                owner_type="co_owner",
                search_term=extracted.risk_co_owner_name,
                caller_role=server_context.get("role") or server_context.get("user_role"),
                caller_dept_id=draft.dept_id,
            )
            owners_co = res_co.get("owners", [])
            if owners_co:
                matched = owners_co[0]
                draft.risk_co_owner_id = matched.get("user_id")
                draft.risk_co_owner_name = matched.get("full_name") or extracted.risk_co_owner_name
                draft.risk_co_owner_role = matched.get("role_name", "Co-Owner")
                draft.field_provenance["risk_co_owner_name"] = "user_stated"
                result.modified_fields.append("risk_co_owner_name")
            else:
                draft.pending_co_owner = extracted.risk_co_owner_name
        except Exception as e:
            logger.debug(f"Could not resolve co-owner name: {e}")
            draft.pending_co_owner = extracted.risk_co_owner_name

    if extracted.action_owner_name and not draft.action_owner_name:
        try:
            res_ao = _handle_lookup_eligible_owners(
                owner_type="action_owner",
                search_term=extracted.action_owner_name,
                dept_id=draft.dept_id,
                caller_role=server_context.get("role") or server_context.get("user_role"),
                caller_dept_id=draft.dept_id,
            )
            owners_ao = res_ao.get("owners", [])
            if owners_ao:
                matched = owners_ao[0]
                draft.action_owner_id = matched.get("user_id")
                draft.action_owner_name = matched.get("full_name") or extracted.action_owner_name
                draft.action_owner_role = matched.get("role_name", "Action Owner")
                draft.field_provenance["action_owner_name"] = "user_stated"
                result.modified_fields.append("action_owner_name")
            else:
                draft.pending_action_owner = extracted.action_owner_name
        except Exception as e:
            logger.debug(f"Could not resolve action owner name: {e}")
            draft.pending_action_owner = extracted.action_owner_name

    draft.updated_at = now_utc
    result.success = len(result.conflicts) == 0
    return result
