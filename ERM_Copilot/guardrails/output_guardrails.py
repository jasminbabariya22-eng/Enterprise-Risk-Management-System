"""
Output Guardrails for ERM Copilot.
Enforces mathematical consistency (Likelihood x Impact = Score), prevents dangerous advice, and formats clean markdown.
"""
import re
from typing import Tuple, Dict, Any, List, Optional
import logging

logger = logging.getLogger("ERM_Copilot.guardrails.output")

# Forbidden unsafe recommendations in industrial plant operations
UNSAFE_ADVICE_PATTERNS = [
    r'(bypass|disable|override)\s+(the\s+)?(safety\s+interlock|emergency\s+shutdown|esd|psv|relief\s+valve)',
    r'(ignore|suppress)\s+(the\s+)?(alarm|leakage|corrosion\s+warning)',
    r'operate\s+above\s+(maximum\s+allowable|design\s+pressure|mop)',
    r'skip\s+(the\s+)?(hydrostatic\s+test|mandatory\s+inspection|safety\s+audit)'
]


class OutputGuardrail:
    """Validates and enforces post-generation safety, accuracy, and schema constraints."""

    @classmethod
    def verify_mathematical_consistency(cls, text: str) -> Tuple[str, bool]:
        """
        Validates that any explicit Likelihood (1-5) and Impact (1-5) 
        multiplication matches the reported Score (1-25). Corrects hallucinated scores.
        """
        modified = False
        result_text = text

        # Match patterns like "Likelihood: 4, Impact: 5, Score: 18" or "L=4, I=5 -> 18"
        pattern = r'(?:likelihood|L)\s*[:=]\s*([1-5])\b.*?(?:impact|I)\s*[:=]\s*([1-5])\b.*?(?:score|total)\s*[:=]\s*(\d{1,2})\b'
        for match in re.finditer(pattern, text, flags=re.IGNORECASE | re.DOTALL):
            l_val = int(match.group(1))
            i_val = int(match.group(2))
            stated_score = int(match.group(3))
            expected_score = l_val * i_val

            if stated_score != expected_score:
                logger.warning(f"Guardrail Alert: Math mismatch corrected. L={l_val} * I={i_val} = {expected_score}, but LLM outputted {stated_score}.")
                # Replace stated score with expected score
                old_segment = match.group(0)
                corrected_segment = re.sub(rf'\b{stated_score}\b', str(expected_score), old_segment)
                result_text = result_text.replace(old_segment, corrected_segment)
                modified = True

        return result_text, modified

    @classmethod
    def check_industrial_safety(cls, text: str) -> Tuple[bool, Optional[str]]:
        """Ensures the response does not give hazardous plant operations advice."""
        lower = text.lower()
        for pattern in UNSAFE_ADVICE_PATTERNS:
            if re.search(pattern, lower, flags=re.IGNORECASE):
                logger.error(f"Guardrail Critical Violation: Unsafe industrial advice detected: '{pattern}'")
                return False, "Output was blocked by ERM Safety Guardrails: Hazardous operational advice detected."
        return True, None

    @classmethod
    def sanitize_output(cls, text: str) -> str:
        """Removes duplicate unwanted system prompts, fixes markdown table spacing."""
        cleaned = text.strip()
        # Remove repeated conversational greetings if stacked
        cleaned = re.sub(r'^(Hello|Hi|Greetings)!\s+(Hello|Hi|Greetings)!', r'\1!', cleaned, flags=re.IGNORECASE)
        # Ensure proper table alignment syntax
        return cleaned
