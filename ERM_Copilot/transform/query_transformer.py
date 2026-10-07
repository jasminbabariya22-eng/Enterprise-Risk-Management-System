"""
Query Transformation and Intent Enhancement Engine for ERM Copilot.
Expands industrial acronyms, corrects typos/shorthands, enriches context, and structures multi-intents.
"""
import re
from typing import Dict, Any, List, Optional, Tuple
import logging

logger = logging.getLogger("ERM_Copilot.transform.query")

# Industrial & ERM Acronym Dictionary
ERM_ACRONYMS = {
    r'\bro\b': 'Risk Owner',
    r'\bfh\b': 'Functional Head',
    r'\brm\b': 'Risk Manager',
    r'\bcro\b': 'Chief Risk Officer (Risk Head)',
    r'\bmtg\b': 'mitigation',
    r'\brsk\b(?!\s*[-_0-9])': 'risk',
    r'\bhzd\b': 'hazard',
    r'\blkh\b': 'likelihood',
    r'\bimp\b': 'impact',
    r'\bscr\b': 'score',
    r'\bpsv\b': 'Pressure Safety Valve (PSV)',
    r'\besd\b': 'Emergency Shutdown (ESD)',
    r'\bfmea\b': 'Failure Mode and Effects Analysis (FMEA)',
    r'\bhazop\b': 'Hazard and Operability Study (HAZOP)',
    r'\bcdu\b': 'Crude Distillation Unit (CDU)',
    r'\bvdu\b': 'Vacuum Distillation Unit (VDU)',
    r'\bfccu\b': 'Fluid Catalytic Cracking Unit (FCCU)',
    r'\bdcs\b': 'Distributed Control System (DCS)',
    r'\bcmms\b': 'Computerized Maintenance Management System (CMMS)',
    r'\bl(\d)\s*i(\d)\b': r'Likelihood \1 Impact \2'
}

# Slang & Shorthand Corrections
SHORTHAND_MAPPINGS = {
    r'\bshw\b': 'show',
    r'\blst\b': 'list',
    r'\bhgh\b': 'high',
    r'\bcrit\b': 'critical',
    r'\bmed\b': 'medium',
    r'\bdept\b': 'department',
    r'\bops\b': 'operations',
    r'\bmaint\b': 'maintenance',
    r'\bplz\b': 'please',
    r'\bu\b': 'you',
    r'\br\b': 'are',
    r'\bapprv\b': 'approval',
    r'\bpndg\b': 'pending',
    r'\bovrdue\b': 'overdue',
    r'\bactn\b': 'action'
}


class QueryTransformer:
    """Transforms raw, noisy user queries into clear, enriched, context-aware ERM intents."""

    @classmethod
    def expand_acronyms_and_shorthand(cls, text: str) -> Tuple[str, bool]:
        """Expands ERM acronyms and normalizes conversational plant slang."""
        transformed = text
        was_modified = False

        # 1. Expand shorthands
        for pattern, replacement in SHORTHAND_MAPPINGS.items():
            if re.search(pattern, transformed, flags=re.IGNORECASE):
                transformed = re.sub(pattern, replacement, transformed, flags=re.IGNORECASE)
                was_modified = True

        # 2. Expand industrial acronyms
        for pattern, replacement in ERM_ACRONYMS.items():
            if re.search(pattern, transformed, flags=re.IGNORECASE):
                transformed = re.sub(pattern, replacement, transformed, flags=re.IGNORECASE)
                was_modified = True

        return transformed, was_modified

    @classmethod
    def enrich_context(cls, text: str, user_role: Optional[str], dept_name: Optional[str]) -> str:
        """
        Enriches ambiguous queries with explicit contextual parameters.
        e.g., 'show my pending approvals' -> 'show pending approvals for Functional Head in Operations department'
        """
        lower = text.lower()
        enriched = text

        # If query refers to 'my risks' or 'my queue', inject role and department
        if any(term in lower for term in ["my risks", "my approval", "my queue", "my department", "our risks"]):
            context_clauses = []
            if user_role:
                context_clauses.append(f"Role: {user_role}")
            if dept_name:
                context_clauses.append(f"Department: {dept_name}")

            if context_clauses:
                clause_str = ", ".join(context_clauses)
                logger.debug(f"Context enriched: '{text}' with [{clause_str}]")

        return enriched

    @classmethod
    def extract_search_keyword(cls, text: str) -> Optional[str]:
        """
        Extract the core subject/title/keyword from natural conversational sentences.
        e.g.:
          - 'I have a maker on Risk. This Risk title is Test 1. So I want to hold out the information related to this Risk.' -> 'Test 1'
          - 'What are the details of risk called Gas Leakage?' -> 'Gas Leakage'
          - 'Show information about compressor seal' -> 'compressor seal'
        """
        if not text or not text.strip():
            return None
        
        cleaned = text.strip()

        # 1. Check for explicit Risk Code (e.g. RSK-GAS-034, RSK-001)
        r_code_match = re.search(r'\b(RSK-[A-Z0-9]+-\d{1,4}|[A-Z]{2,5}-\d{1,5}|RSK-\d{1,4})\b', cleaned, re.IGNORECASE)
        if r_code_match:
            return r_code_match.group(1).upper()

        # 2. Check for explicit "title is / named / called / for risk" patterns
        title_patterns = [
            r'(?:risk\s+)?title\s+(?:is|was|called|named|of)?\s*[:"\'`]?\s*([a-zA-Z0-9\s\-_]{2,50}?)(?:\.|\s+so\b|\s+and\b|\s+which\b|["\'`\n]|$)',
            r'(?:named|called|titled)\s*[:"\'`]?\s*([a-zA-Z0-9\s\-_]{2,50}?)(?:\.|\s+so\b|\s+and\b|\s+which\b|["\'`\n]|$)',
            r'(?:information|details|data|info|status)\s+(?:of|on|for|about|regarding)\s+(?:the\s+)?(?:risk\s+)?[:"\'`]?\s*([a-zA-Z0-9\s\-_]{2,50}?)(?:\.|\s+so\b|\s+and\b|["\'`\n]|$)',
            r'(?:about|on|for|regarding)\s+(?:the\s+)?(?:risk\s+)?[:"\'`]?\s*([a-zA-Z0-9\s\-_]{2,50}?)(?:\.|\s+so\b|\s+and\b|["\'`\n]|$)',
        ]
        for pat in title_patterns:
            m = re.search(pat, cleaned, re.IGNORECASE)
            if m:
                extracted = m.group(1).strip()
                if extracted.lower() not in ["this", "that", "it", "risk", "the risk", "my risk", "a risk"]:
                    return extracted

        # 3. Clean leading command words (show/search/find/view/get/list)
        clean_kw = re.sub(
            r'^(?:show|search|find|view|list|get|look up|give me|check|what are the details of|tell me about)\s+(?:me\s+)?(?:all\s+)?(?:the\s+)?(?:risks?|hazards?|items?|information|details)?\s*(?:about|on|for|regarding|in|related to)?\s*',
            '', cleaned, flags=re.IGNORECASE
        ).strip()

        # Remove trailing pleasantries / filler
        clean_kw = re.sub(r'(?:\s+in\s+my\s+department|\s+please|\s+plz|\.)$', '', clean_kw, flags=re.IGNORECASE).strip()

        return clean_kw if clean_kw and len(clean_kw) >= 2 else None

    @classmethod
    def transform(cls, text: str, user_role: Optional[str] = None, dept_name: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
        """
        Executes the complete transformation pipeline.
        Returns: (transformed_query, transformation_metadata)
        """
        # 1. Clean extra whitespace
        cleaned = " ".join(text.strip().split())

        # 2. Expand acronyms & shorthands
        expanded, was_expanded = cls.expand_acronyms_and_shorthand(cleaned)

        # 3. Contextual enrichment
        enriched = cls.enrich_context(expanded, user_role, dept_name)

        metadata = {
            "original_query": text,
            "was_transformed": was_expanded or (enriched != text),
            "normalized_query": enriched
        }

        return enriched, metadata
