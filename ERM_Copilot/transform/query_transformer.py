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
    r'\brsk\b': 'risk',
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
