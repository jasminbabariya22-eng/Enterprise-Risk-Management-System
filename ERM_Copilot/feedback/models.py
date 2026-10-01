"""
User Feedback and RLHF Quality Loop Models for ERM Copilot.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field
import uuid


class FeedbackEntry(BaseModel):
    feedback_id: str = Field(default_factory=lambda: f"FB-{uuid.uuid4().hex[:8].upper()}")
    request_id: Optional[str] = None
    user_id: Optional[str] = "5"
    user_role: Optional[str] = "Risk Owner"
    department: Optional[str] = None
    rating: int = Field(..., description="1 for Thumbs Up / Positive, -1 for Thumbs Down / Negative")
    category: Optional[str] = Field(default="general", description="e.g. helpful, accurate_math, hallucination, unclear_mitigation, slow")
    comment: Optional[str] = None
    prompt: Optional[str] = None
    response_snippet: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FeedbackSummary(BaseModel):
    total_feedback: int
    positive_count: int
    negative_count: int
    satisfaction_rate_pct: float
    category_distribution: Dict[str, int]
