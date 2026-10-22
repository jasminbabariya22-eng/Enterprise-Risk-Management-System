"""
Risk Matrix & Scoring Service for 5x5 ERM Matrix.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple


class RiskMatrixCalculator:
    """Authoritative 5x5 ERM Risk Matrix Calculation & Severity Classification (All 25 Combinations)."""

    LIKELIHOOD_LABELS = {
        1: "Remote",
        2: "Unlikely",
        3: "Possible",
        4: "Probable",
        5: "Expected"
    }

    IMPACT_LABELS = {
        1: "Negligible",
        2: "Minor",
        3: "Moderate",
        4: "Major",
        5: "Extreme"
    }

    WORD_TO_LIKELIHOOD = {
        "remote": 1, "rare": 1,
        "unlikely": 2,
        "possible": 3, "moderate likelihood": 3,
        "probable": 4, "likely": 4,
        "expected": 5, "almost certain": 5, "certain": 5
    }

    WORD_TO_IMPACT = {
        "negligible": 1, "insignificant": 1,
        "minor": 2, "low impact": 2,
        "moderate": 3, "medium impact": 3,
        "major": 4, "high impact": 4,
        "extreme": 5, "catastrophic": 5, "critical impact": 5
    }

    @staticmethod
    def is_valid_rating(value: Any) -> bool:
        """Check if rating is a valid integer between 1 and 5."""
        if value is None or isinstance(value, bool):
            return False
        try:
            val_int = int(value)
            return 1 <= val_int <= 5 and float(value) == val_int
        except (ValueError, TypeError):
            return False

    @staticmethod
    def validate_rating(rating: Any, field_name: str = "Rating") -> Tuple[bool, Optional[str]]:
        """Validate rating is strictly an integer between 1 and 5."""
        if rating is None:
            return False, f"{field_name} is missing."
        if isinstance(rating, bool):
            return False, f"{field_name} must be an integer between 1 and 5, not a boolean."
        try:
            val_int = int(rating)
            if float(rating) != val_int:
                return False, f"{field_name} must be a whole integer between 1 and 5 (got {rating})."
            if not (1 <= val_int <= 5):
                return False, f"{field_name} must be between 1 and 5 (got {rating})."
            return True, None
        except (ValueError, TypeError):
            return False, f"{field_name} must be a valid integer between 1 and 5 (got {rating})."

    @classmethod
    def calculate_score(cls, likelihood: int, impact: int, strict: bool = True) -> Tuple[int, str, str]:
        """
        Calculate Risk Score and Severity Level according to ERM 5x5 Matrix standards.
        Returns: (score, level_name, severity_badge)
        Raises ValueError if ratings are invalid and strict=True.
        """
        if strict:
            ok_l, err_l = cls.validate_rating(likelihood, "Likelihood")
            if not ok_l:
                raise ValueError(err_l)
            ok_i, err_i = cls.validate_rating(impact, "Impact")
            if not ok_i:
                raise ValueError(err_i)
            l = int(likelihood)
            i = int(impact)
        else:
            l = max(1, min(5, int(likelihood)))
            i = max(1, min(5, int(impact)))

        score = l * i

        if score >= 15:
            return score, "CRITICAL", "[CRITICAL]"
        elif score >= 10:
            return score, "HIGH", "[HIGH]"
        elif score >= 5:
            return score, "MEDIUM", "[MEDIUM]"
        else:
            return score, "LOW", "[LOW]"

    @classmethod
    def parse_likelihood_impact(cls, text: str) -> Optional[Tuple[int, int]]:
        """Extract likelihood (1-5) and impact (1-5) numbers or names from user text across all 25 combinations."""
        lower = text.strip().lower()

        # Check explicit option keywords
        if any(w in lower for w in ["option a", "4x5", "4 5", "score 20"]):
            return 4, 5
        if any(w in lower for w in ["option b", "3x4", "3 4", "score 12"]):
            return 3, 4
        if any(w in lower for w in ["option c", "3x3", "3 3", "score 9"]):
            return 3, 3
        if any(w in lower for w in ["option d", "2x2", "2 2", "score 4"]):
            return 2, 2

        # Check if text contains explicit numbers out of bounds (e.g. 0 or > 5)
        raw_digits = [int(s) for s in re.findall(r'\b\d+\b', text)]
        if any(d < 1 or d > 5 for d in raw_digits):
            return None

        # Check named word combinations, e.g. "Probable Major" or "Likelihood Remote Impact Moderate"
        found_l = None
        found_i = None

        for word, val in cls.WORD_TO_LIKELIHOOD.items():
            if word in lower:
                found_l = val
                break

        for word, val in cls.WORD_TO_IMPACT.items():
            if word in lower:
                found_i = val
                break

        if found_l is not None and found_i is not None:
            return found_l, found_i

        # Pattern: L=3, I=4 or Likelihood 3 Impact 4 or L3 I4 or 3x4 or 3 4
        match = re.search(r'(?:likelihood|l)?\s*[:=]?\s*([1-5])\s*(?:x|,|and|\s)\s*(?:impact|i)?\s*[:=]?\s*([1-5])\b', lower)
        if match:
            return int(match.group(1)), int(match.group(2))

        # Explicit "Likelihood 3 ... Impact 4"
        l_match = re.search(r'(?:likelihood|l)\s*[:=]?\s*([1-5])\b', lower)
        i_match = re.search(r'(?:impact|i)\s*[:=]?\s*([1-5])\b', lower)
        if l_match and i_match:
            return int(l_match.group(1)), int(i_match.group(1))

        # Standalone digits 1-5 (supports all 25 combinations from 1 1 to 5 5)
        numbers = [int(s) for s in re.findall(r'\b[1-5]\b', text)]
        if len(numbers) >= 2:
            return numbers[0], numbers[1]
        elif len(numbers) == 1 and found_i is not None:
            return numbers[0], found_i
        elif len(numbers) == 1 and found_l is not None:
            return found_l, numbers[0]

        return None

    @classmethod
    def parse_single_likelihood(cls, text: str) -> Optional[int]:
        """Extract a single likelihood value (1-5) or keyword from user text."""
        lower = text.strip().lower()
        for word, val in cls.WORD_TO_LIKELIHOOD.items():
            if word in lower:
                return val
        match = re.search(r'(?:likelihood|prob|l)\s*[:=]?\s*([1-5])\b', lower)
        if match:
            return int(match.group(1))
        return None

    @classmethod
    def parse_single_impact(cls, text: str) -> Optional[int]:
        """Extract a single impact value (1-5) or keyword from user text."""
        lower = text.strip().lower()
        for word, val in cls.WORD_TO_IMPACT.items():
            if word in lower:
                return val
        match = re.search(r'(?:impact|sev|i)\s*[:=]?\s*([1-5])\b', lower)
        if match:
            return int(match.group(1))
        return None
