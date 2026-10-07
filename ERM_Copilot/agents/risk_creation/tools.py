"""
Tools, Parsers, and Backend Validation Helpers for Risk Creation.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from ERM_Copilot.services.db_service import erm_db


def parse_target_date(text: str) -> Optional[str]:
    """Parse user text into a standard ISO/display target date string."""
    cleaned = text.strip().lower()
    
    # Check relative intervals, e.g. "+30 days", "30 days", "in 60 days"
    days_match = re.search(r'(?:\+|in\s+)?(\d{1,3})\s*(?:days?|d)\b', cleaned)
    if days_match:
        days = int(days_match.group(1))
        future_dt = datetime.now(timezone.utc) + timedelta(days=days)
        return future_dt.strftime("%Y-%m-%d")

    # Common formats: YYYY-MM-DD, DD-MM-YYYY, DD/MM/YYYY, DD Month YYYY
    date_formats = [
        "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y",
        "%d %B %Y", "%d %b %Y", "%d-%b-%Y", "%d-%B-%Y",
        "%B %d %Y", "%B %d, %Y", "%b %d %Y", "%b %d, %Y"
    ]
    for fmt in date_formats:
        try:
            dt = datetime.strptime(text.strip(), fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    # Regex search for date pattern inside larger sentence
    iso_match = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', text)
    if iso_match:
        return iso_match.group(1)

    dmy_match = re.search(r'\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b', text)
    if dmy_match:
        try:
            d, m, y = int(dmy_match.group(1)), int(dmy_match.group(2)), int(dmy_match.group(3))
            dt = datetime(y, m, d)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    text_dmy = re.search(r'\b(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\b', text)
    if text_dmy:
        raw_str = f"{text_dmy.group(1)} {text_dmy.group(2)} {text_dmy.group(3)}"
        for fmt in ["%d %B %Y", "%d %b %Y"]:
            try:
                dt = datetime.strptime(raw_str, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                pass

    return None


def parse_progress(text: str) -> Optional[int]:
    """Extract progress percentage (0-100) from user text."""
    cleaned = text.strip().lower()
    pct_match = re.search(r'\b(\d{1,3})\s*%', cleaned)
    if pct_match:
        val = int(pct_match.group(1))
        return val if 0 <= val <= 100 else None

    word_match = re.search(r'(?:progress\s*(?:is|to|at)?\s*)?(\d{1,3})\s*(?:percent)?\b', cleaned)
    if word_match:
        val = int(word_match.group(1))
        if 0 <= val <= 100:
            return val

    digits = [int(s) for s in re.findall(r'\b\d{1,3}\b', text)]
    for d in digits:
        if 0 <= d <= 100:
            return d

    return None


def detect_field_edits(msg: str) -> Optional[Tuple[str, str]]:
    """Detect if user is requesting to edit a specific field before confirmation."""
    lower = msg.strip().lower()

    # Target Date
    if any(w in lower for w in ["target date", "completion date", "due date", "timeline"]):
        val = re.sub(r'^(?:change|update|set|edit|modify)\s*(?:the\s*)?(?:target|completion|due)?\s*(?:date|timeline)\s*(?:to|is|=)?\s*', '', msg, flags=re.IGNORECASE).strip()
        return "target_date", val

    # Progress
    if any(w in lower for w in ["progress", "completion percentage", "percent"]):
        val = re.sub(r'^(?:change|update|set|edit|modify)\s*(?:the\s*)?progress\s*(?:percentage|percent)?\s*(?:to|is|=)?\s*', '', msg, flags=re.IGNORECASE).strip()
        return "progress", val

    # Mitigation
    if any(w in lower for w in ["mitigation", "treatment", "control"]):
        val = re.sub(r'^(?:change|update|set|edit|modify)\s*(?:the\s*)?(?:mitigation|treatment|control)\s*(?:to|is|=)?\s*', '', msg, flags=re.IGNORECASE).strip()
        return "mitigation", val

    # Action Plan
    if any(w in lower for w in ["action plan", "action", "plan"]):
        val = re.sub(r'^(?:change|update|set|edit|modify)\s*(?:the\s*)?action\s*plan\s*(?:to|is|=)?\s*', '', msg, flags=re.IGNORECASE).strip()
        return "action_plan", val

    # Description
    if any(w in lower for w in ["description", "risk description", "hazard description"]):
        val = re.sub(r'^(?:change|update|set|edit|modify)\s*(?:the\s*)?(?:risk\s*)?description\s*(?:to|is|=)?\s*', '', msg, flags=re.IGNORECASE).strip()
        return "risk_description", val

    # Risk Name / Title
    if any(w in lower for w in ["risk name", "risk title", "title", "name"]):
        val = re.sub(r'^(?:change|update|set|edit|modify)\s*(?:the\s*)?(?:risk\s*)?(?:name|title)\s*(?:to|is|=)?\s*', '', msg, flags=re.IGNORECASE).strip()
        return "risk_name", val

    # Co-Owner
    if any(w in lower for w in ["co-owner", "co owner", "co_owner"]):
        val = re.sub(r'^(?:change|update|set|edit|modify)\s*(?:the\s*)?(?:risk\s*)?co[\s\-_]?owner\s*(?:to|is|=)?\s*', '', msg, flags=re.IGNORECASE).strip()
        return "co_owner", val

    # Action Owner
    if any(w in lower for w in ["action owner", "action_owner"]):
        val = re.sub(r'^(?:change|update|set|edit|modify)\s*(?:the\s*)?action\s*owner\s*(?:to|is|=)?\s*', '', msg, flags=re.IGNORECASE).strip()
        return "action_owner", val

    # Inherent Assessment
    if any(w in lower for w in ["inherent severity", "inherent score", "inherent rating", "inherent risk", "inherent likelihood"]):
        val = re.sub(r'^(?:change|update|set|edit|modify)\s*(?:the\s*)?inherent\s*(?:severity|score|rating|risk|assessment)?\s*(?:to|is|=)?\s*', '', msg, flags=re.IGNORECASE).strip()
        return "inherent_assessment", val

    # Current Assessment
    if any(w in lower for w in ["current severity", "current score", "current rating", "current risk", "residual risk", "current likelihood"]):
        val = re.sub(r'^(?:change|update|set|edit|modify)\s*(?:the\s*)?(?:current|residual)\s*(?:severity|score|rating|risk|assessment)?\s*(?:to|is|=)?\s*', '', msg, flags=re.IGNORECASE).strip()
        return "current_assessment", val

    # Status
    if any(w in lower for w in ["status", "workflow status", "submission status"]):
        val = re.sub(r'^(?:change|update|set|edit|modify)\s*(?:the\s*)?(?:workflow|submission)?\s*status\s*(?:to|is|=)?\s*', '', msg, flags=re.IGNORECASE).strip()
        return "status", val

    return None
