"""
Structured Risk Field Extraction Module for ERM Copilot.
Extracts all recognizable risk attributes from natural language messages in any order,
using structured LLM extraction with resilient deterministic fallback.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from ERM_Copilot.agents.risk_creation.scoring import RiskMatrixCalculator
from ERM_Copilot.agents.risk_creation.tools import parse_target_date, parse_progress
from ERM_Copilot.gateway.client import portkey_client

logger = logging.getLogger("ERM_Copilot.agents.risk_creation.extraction")


class ExtractedRiskFields(BaseModel):
    """
    Typed, schema-validated model for extracted risk attributes.
    Absent fields are explicitly None, never hallucinated or fabricated.
    """
    risk_name: Optional[str] = None
    risk_description: Optional[str] = None
    inherent_likelihood: Optional[int] = None
    inherent_impact: Optional[int] = None
    mitigation: Optional[str] = None
    current_likelihood: Optional[int] = None
    current_impact: Optional[int] = None
    action_plan: Optional[str] = None
    action_owner_name: Optional[str] = None
    action_owner_id: Optional[int] = None
    risk_co_owner_name: Optional[str] = None
    risk_co_owner_id: Optional[int] = None
    target_date: Optional[str] = None
    progress: Optional[int] = None
    submission_mode: Optional[str] = None  # "draft" or "submit"
    extraction_source: str = "deterministic"  # "llm", "deterministic", "hybrid"
    is_correction: bool = False
    corrected_field: Optional[str] = None
    raw_extracted: Dict[str, Any] = Field(default_factory=dict)


EXTRACTION_SYSTEM_PROMPT = """You are an expert Enterprise Risk Management (ERM) field extraction engine.
Analyze the user's message and extract any mentioned risk attributes into valid JSON with these EXACT keys:
- "risk_name": string or null (Hazard or risk title/name)
- "risk_description": string or null (Event, threat, failure mode, or consequence description)
- "inherent_likelihood": integer 1-5 or null (Likelihood before controls)
- "inherent_impact": integer 1-5 or null (Impact before controls)
- "mitigation": string or null (Preventive controls, engineering barriers, or safety mitigations)
- "current_likelihood": integer 1-5 or null (Residual/current likelihood after mitigation)
- "current_impact": integer 1-5 or null (Residual/current impact after mitigation)
- "action_plan": string or null (Specific tactical action plan, maintenance tasks, or SOP updates)
- "action_owner_name": string or null (Name of person or title assigned to action)
- "risk_co_owner_name": string or null (Name of enterprise co-owner)
- "target_date": string or null (Any specified deadline or target date)
- "submission_mode": "draft", "submit", or null (Whether user wants to save as draft or submit to functional head)

CRITICAL RULES:
1. ONLY return pure JSON with keys above. Do not include markdown or explanations.
2. If an attribute is NOT mentioned, set its value to null. NEVER invent or guess IDs, numbers, or text.
3. Likelihood and Impact MUST be integers between 1 and 5.
4. Do NOT output user_id, dept_id, or department_id.
"""


def _clean_json_str(raw: str) -> str:
    """Strip markdown code fence wrappers from JSON string."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def deterministic_extract(message: str) -> ExtractedRiskFields:
    """
    Deterministic rule-based extractor using regular expressions, keyword boundaries,
    and scoring patterns. Used as primary standalone parser or safety fallback.
    """
    extracted = ExtractedRiskFields(extraction_source="deterministic")
    msg = message.strip()
    lower_msg = msg.lower()

    # 1. Target Date
    t_date = parse_target_date(msg)
    if t_date:
        extracted.target_date = t_date

    # 2. Progress
    prog = parse_progress(msg)
    if prog is not None:
        extracted.progress = prog

    # 3. Submission Mode
    if any(w in lower_msg for w in ["submit to functional head", "submit to fh", "submit for approval", "submit risk", "mode submit"]):
        extracted.submission_mode = "submit"
    elif any(w in lower_msg for w in ["save as draft", "save draft", "keep as draft", "mode draft"]):
        extracted.submission_mode = "draft"

    # 4. Inherent & Current Likelihood / Impact Numbers
    # Case A: Explicit labeled inherent likelihood / impact
    # e.g. "inherent likelihood 4 and impact 5" or "inherent: likelihood=4, impact=5" or "inherent 4x5"
    inh_match = re.search(r'inherent\s*(?:risk|assessment|rating|severity)?\s*(?:likelihood|l)?\s*[:=]?\s*([1-5])\s*(?:and|,|x|\*|\s)?\s*(?:impact|i)?\s*[:=]?\s*([1-5])', lower_msg)
    if inh_match:
        extracted.inherent_likelihood = int(inh_match.group(1))
        extracted.inherent_impact = int(inh_match.group(2))
    else:
        # Separate matches
        inh_l = re.search(r'inherent\s*(?:likelihood|prob|probability)\s*[:=]?\s*([1-5])', lower_msg)
        if inh_l:
            extracted.inherent_likelihood = int(inh_l.group(1))
        inh_i = re.search(r'inherent\s*(?:impact|consequence|severity)\s*[:=]?\s*([1-5])', lower_msg)
        if inh_i:
            extracted.inherent_impact = int(inh_i.group(1))

    # Case B: Explicit labeled residual / current likelihood / impact
    curr_match = re.search(r'(?:current|residual)\s*(?:risk|assessment|rating|severity)?\s*(?:likelihood|l)?\s*[:=]?\s*([1-5])\s*(?:and|,|x|\*|\s)?\s*(?:impact|i)?\s*[:=]?\s*([1-5])', lower_msg)
    if curr_match:
        extracted.current_likelihood = int(curr_match.group(1))
        extracted.current_impact = int(curr_match.group(2))
    else:
        cur_l = re.search(r'(?:current|residual)\s*(?:likelihood|prob|probability)\s*[:=]?\s*([1-5])', lower_msg)
        if cur_l:
            extracted.current_likelihood = int(cur_l.group(1))
        cur_i = re.search(r'(?:current|residual)\s*(?:impact|consequence|severity)\s*[:=]?\s*([1-5])', lower_msg)
        if cur_i:
            extracted.current_impact = int(cur_i.group(1))

    # Case C: Matrix option codes (Option A 4x5, Option B 3x4, etc.)
    matrix_match = re.search(r'\b([1-5])\s*[xX*]\s*([1-5])\b', msg)
    if matrix_match and extracted.inherent_likelihood is None:
        extracted.inherent_likelihood = int(matrix_match.group(1))
        extracted.inherent_impact = int(matrix_match.group(2))

    # 5. Mitigation extraction via boundary keywords
    mit_patterns = [
        r'(?:mitigation|mitigation\s*strategy|controls?)\s*(?:is|are|=|:)\s*([^\n\.,;]+(?:[^\n\.,;]+){1,3})',
        r'mitigate\s*(?:by|with|using)\s*([^\n\.,;]+(?:[^\n\.,;]+){1,3})',
    ]
    for p in mit_patterns:
        m = re.search(p, msg, re.IGNORECASE)
        if m:
            cand = m.group(1).strip()
            if len(cand) >= 5 and not any(kw in cand.lower() for kw in ["likelihood", "impact", "action plan"]):
                extracted.mitigation = cand
                break

    # 6. Action Plan extraction via boundary keywords
    act_patterns = [
        r'(?:action\s*plan|tactical\s*action|treatment\s*action|action)\s*(?:is|are|=|:)\s*([^\n\.,;]+(?:[^\n\.,;]+){1,3})',
        r'action\s*plan\s*to\s*([^\n\.,;]+(?:[^\n\.,;]+){1,3})',
    ]
    for p in act_patterns:
        m = re.search(p, msg, re.IGNORECASE)
        if m:
            cand = m.group(1).strip()
            if len(cand) >= 5 and not any(kw in cand.lower() for kw in ["likelihood", "impact", "mitigation"]):
                extracted.action_plan = cand
                break

    # 7. Description extraction
    desc_patterns = [
        r'(?:risk\s*description|event\s*description|description|threat)\s*(?:is|are|=|:)\s*([^\n;]+)',
    ]
    for p in desc_patterns:
        m = re.search(p, msg, re.IGNORECASE)
        if m:
            cand = m.group(1).strip()
            if len(cand) >= 5:
                extracted.risk_description = cand
                break

    # 8. Risk Name / Title extraction
    title_patterns = [
        r'(?:risk\s*name|risk\s*title|title)\s*(?:is|=|:)\s*([^\n\.,;]+)',
        r'(?:create|save|add|new|draft|record)\s*(?:a\s*)?(?:new\s*)?risk\s*(?:for|on|regarding|about)\s+([^,\n\.;]+)',
    ]
    for p in title_patterns:
        m = re.search(p, msg, re.IGNORECASE)
        if m:
            cand = m.group(1).strip()
            # Clean trailing instructions
            clean_cand = re.split(r'\b(?:with|where|and|inherent|current|mitigation|action|likelihood|impact|target)\b', cand, flags=re.IGNORECASE)[0].strip()
            if len(clean_cand) >= 3:
                words = clean_cand.split()
                extracted.risk_name = " ".join([w.capitalize() if not (w.upper().startswith("P-") or (len(w) == 1 and w.isupper())) else w.upper() for w in words])
                break

    # 9. Action Owner Name
    ao_match = re.search(r'(?:assign\s*action\s*owner|action\s*owner)\s*(?:is|=|:)?\s*([A-Za-z0-9_\s]{2,30})', msg, re.IGNORECASE)
    if ao_match:
        ao_cand = ao_match.group(1).strip()
        clean_ao = re.split(r'\b(?:with|where|and|target|date|due|by|for)\b', ao_cand, flags=re.IGNORECASE)[0].strip()
        if len(clean_ao) >= 2 and not any(kw in clean_ao.lower() for kw in ["likelihood", "impact", "mitigation", "plan"]):
            extracted.action_owner_name = clean_ao

    # 10. Co-Owner Name
    co_match = re.search(r'(?:assign\s*co[\s\-_]?owner|co[\s\-_]?owner)\s*(?:is|=|:)?\s*([A-Za-z0-9_\s]{2,30})', msg, re.IGNORECASE)
    if co_match:
        co_cand = co_match.group(1).strip()
        clean_co = re.split(r'\b(?:with|where|and|target|date|due|by|for)\b', co_cand, flags=re.IGNORECASE)[0].strip()
        if len(clean_co) >= 2:
            extracted.risk_co_owner_name = clean_co

    return extracted


def extract_risk_fields(message: str, current_draft: Optional[Any] = None) -> ExtractedRiskFields:
    """
    Extract every recognizable risk field from the user message, regardless of order.
    Invokes the LLM gateway with structured JSON parsing, falling back smoothly to
    deterministic pattern extraction if the LLM is unreachable or returns invalid format.
    """
    clean_msg = message.strip()
    if not clean_msg:
        return ExtractedRiskFields(extraction_source="deterministic")

    # Step 1: Run deterministic extractor first to capture high-confidence tokens (ratings, dates, etc.)
    det_result = deterministic_extract(clean_msg)

    # Step 2: Attempt LLM extraction for natural language subtleties
    llm_payload: Optional[Dict[str, Any]] = None
    try:
        if portkey_client and hasattr(portkey_client, "chat") and hasattr(portkey_client.chat, "completions"):
            messages = [
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": clean_msg}
            ]
            response = portkey_client.chat.completions.create(
                messages=messages,
                temperature=0.0
            )
            raw_text = ""
            if hasattr(response, "choices") and response.choices:
                first_choice = response.choices[0]
                if hasattr(first_choice, "message"):
                    raw_text = getattr(first_choice.message, "content", "") or ""

            if raw_text:
                cleaned = _clean_json_str(raw_text)
                llm_payload = json.loads(cleaned)
    except Exception as e:
        logger.debug(f"[LLM_EXTRACTION_FALLBACK] Gateway error or unavailable: {e}. Using deterministic extraction.")
        llm_payload = None

    if not llm_payload or not isinstance(llm_payload, dict):
        return det_result

    # Step 3: Merge LLM extracted fields with deterministic baseline
    # Favor LLM for semantic text (descriptions, mitigations, action plans) and deterministic for strict bounds
    final = ExtractedRiskFields(
        extraction_source="hybrid",
        raw_extracted=llm_payload
    )

    # Risk Name
    final.risk_name = (
        det_result.risk_name
        or (str(llm_payload.get("risk_name")).strip() if llm_payload.get("risk_name") else None)
    )

    # Risk Description
    final.risk_description = (
        (str(llm_payload.get("risk_description")).strip() if llm_payload.get("risk_description") else None)
        or det_result.risk_description
    )

    # Mitigation
    final.mitigation = (
        (str(llm_payload.get("mitigation")).strip() if llm_payload.get("mitigation") else None)
        or det_result.mitigation
    )

    # Action Plan
    final.action_plan = (
        (str(llm_payload.get("action_plan")).strip() if llm_payload.get("action_plan") else None)
        or det_result.action_plan
    )

    # Inherent Likelihood & Impact (Strict integer 1-5 validation)
    inh_l = det_result.inherent_likelihood or llm_payload.get("inherent_likelihood")
    if inh_l is not None:
        try:
            val = int(inh_l)
            if 1 <= val <= 5:
                final.inherent_likelihood = val
        except (ValueError, TypeError):
            pass

    inh_i = det_result.inherent_impact or llm_payload.get("inherent_impact")
    if inh_i is not None:
        try:
            val = int(inh_i)
            if 1 <= val <= 5:
                final.inherent_impact = val
        except (ValueError, TypeError):
            pass

    # Current Likelihood & Impact
    cur_l = det_result.current_likelihood or llm_payload.get("current_likelihood")
    if cur_l is not None:
        try:
            val = int(cur_l)
            if 1 <= val <= 5:
                final.current_likelihood = val
        except (ValueError, TypeError):
            pass

    cur_i = det_result.current_impact or llm_payload.get("current_impact")
    if cur_i is not None:
        try:
            val = int(cur_i)
            if 1 <= val <= 5:
                final.current_impact = val
        except (ValueError, TypeError):
            pass

    # Target Date
    final.target_date = det_result.target_date or (str(llm_payload.get("target_date")).strip() if llm_payload.get("target_date") else None)

    # Submission Mode
    final.submission_mode = det_result.submission_mode or (str(llm_payload.get("submission_mode")).strip() if llm_payload.get("submission_mode") else None)

    # Action Owner & Co-Owner
    final.action_owner_name = det_result.action_owner_name or (str(llm_payload.get("action_owner_name")).strip() if llm_payload.get("action_owner_name") else None)
    final.risk_co_owner_name = det_result.risk_co_owner_name or (str(llm_payload.get("risk_co_owner_name")).strip() if llm_payload.get("risk_co_owner_name") else None)
    final.progress = det_result.progress

    return final
