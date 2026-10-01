"""
User Feedback Service for ERM Copilot.
Handles feedback ingestion, persistence (file / database), and live analytics.
"""
import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pathlib import Path

from ERM_Copilot.feedback.models import FeedbackEntry, FeedbackSummary

logger = logging.getLogger("ERM_Copilot.feedback.service")

FEEDBACK_STORAGE_PATH = Path(__file__).resolve().parent / "feedback_store.jsonl"


class FeedbackService:
    """Service to capture, store, and analyze user feedback on Copilot responses."""

    def __init__(self, storage_path: Path = FEEDBACK_STORAGE_PATH):
        self.storage_path = storage_path
        self._in_memory_entries: List[Dict[str, Any]] = []
        self._load_existing()

    def _load_existing(self):
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            self._in_memory_entries.append(json.loads(line.strip()))
            except Exception as e:
                logger.error(f"Error loading feedback store: {e}")

    def record_feedback(
        self,
        rating: int,
        category: Optional[str] = "general",
        comment: Optional[str] = None,
        request_id: Optional[str] = None,
        user_id: Optional[str] = "5",
        user_role: Optional[str] = "Risk Owner",
        department: Optional[str] = None,
        prompt: Optional[str] = None,
        response: Optional[str] = None
    ) -> FeedbackEntry:
        """Records a new user feedback rating and appends to persistent storage."""
        entry = FeedbackEntry(
            request_id=request_id,
            user_id=user_id,
            user_role=user_role,
            department=department,
            rating=1 if rating > 0 else -1,
            category=category or "general",
            comment=comment,
            prompt=prompt[:200] if prompt else None,
            response_snippet=response[:300] if response else None
        )

        entry_dict = entry.model_dump(mode="json")
        self._in_memory_entries.append(entry_dict)

        try:
            with open(self.storage_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry_dict) + "\n")
            logger.info(f"Feedback recorded: {entry.feedback_id} | Rating: {entry.rating} ({entry.category})")
        except Exception as e:
            logger.error(f"Failed to append feedback: {e}")

        return entry

    def get_summary(self) -> Dict[str, Any]:
        """Calculates live satisfaction metrics and category breakdowns."""
        total = len(self._in_memory_entries)
        if total == 0:
            return {
                "total_feedback": 0,
                "positive_count": 0,
                "negative_count": 0,
                "satisfaction_rate_pct": 100.0,
                "category_distribution": {}
            }

        pos = sum(1 for e in self._in_memory_entries if e.get("rating", 0) > 0)
        neg = total - pos
        rate = (pos / total) * 100.0

        cats: Dict[str, int] = {}
        for e in self._in_memory_entries:
            c = e.get("category", "general")
            cats[c] = cats.get(c, 0) + 1

        return {
            "total_feedback": total,
            "positive_count": pos,
            "negative_count": neg,
            "satisfaction_rate_pct": round(rate, 2),
            "category_distribution": cats
        }


# Global Singleton Instance
erm_feedback_service = FeedbackService()
