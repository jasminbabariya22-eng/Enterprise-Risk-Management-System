"""
Trusted Execution Context for ERM AI Harness.
Ensures strict separation between verified server-side identity and untrusted LLM input.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator

from ERM_Copilot.ai_harness.exceptions import AuthenticationError


class HarnessContext(BaseModel):
    """
    Immutable, verified server-side context for governed AI orchestration.
    
    CRITICAL SECURITY INVARIANTS:
    1. user_id and user_role MUST be populated from trusted authentication session / token.
    2. Prompt-supplied or LLM-suggested identity fields are NEVER used to populate this context.
    3. No fallback default user IDs (e.g. '5') are allowed.
    """
    user_id: str = Field(..., description="Verified user identifier from server session.")
    user_role: str = Field(..., description="Verified ERM role from server RBAC.")
    dept_id: Optional[int] = Field(default=None, description="Verified department ID if constrained.")
    dept_name: Optional[str] = Field(default=None, description="Verified department name.")
    request_id: str = Field(default_factory=lambda: f"req-{uuid.uuid4().hex[:12]}", description="External correlation ID.")
    run_id: str = Field(default_factory=lambda: f"run-{uuid.uuid4().hex[:12]}", description="Unique AI execution run ID.")
    session_id: Optional[str] = Field(default=None, description="Conversation session ID.")
    allowed_tools: Optional[List[str]] = Field(default=None, description="Explicit tool whitelist if restricted.")
    confirmation_state: Optional[Dict[str, Any]] = Field(default=None, description="Active pending confirmation context.")
    trace_metadata: Dict[str, Any] = Field(default_factory=dict, description="Audit and diagnostic trace attributes.")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Context creation timestamp.")
    is_authenticated: bool = Field(default=True, description="Strict authentication flag.")

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        cleaned = str(v).strip() if v is not None else ""
        if not cleaned:
            raise AuthenticationError("Authenticated user ID must be a non-empty string.")
        return cleaned

    @field_validator("user_role")
    @classmethod
    def validate_user_role(cls, v: str) -> str:
        cleaned = str(v).strip() if v is not None else ""
        if not cleaned:
            raise AuthenticationError("Authenticated user role must be a non-empty string.")
        return cleaned

    @classmethod
    def build_from_auth(
        cls,
        user_id: Any,
        user_role: Any,
        dept_id: Optional[Any] = None,
        dept_name: Optional[Any] = None,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
        confirmation_state: Optional[Dict[str, Any]] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> HarnessContext:
        """
        Factory method to safely build context from server session.
        Fails safely if required identity context is missing.
        """
        if user_id is None or str(user_id).strip() in ("", "None", "null"):
            raise AuthenticationError("Cannot create HarnessContext: missing trusted user_id.")
        if user_role is None or str(user_role).strip() in ("", "None", "null"):
            raise AuthenticationError("Cannot create HarnessContext: missing trusted user_role.")

        parsed_dept_id: Optional[int] = None
        if dept_id is not None:
            try:
                parsed_dept_id = int(dept_id)
            except (ValueError, TypeError):
                parsed_dept_id = None

        return cls(
            user_id=str(user_id).strip(),
            user_role=str(user_role).strip(),
            dept_id=parsed_dept_id,
            dept_name=str(dept_name).strip() if dept_name else None,
            session_id=str(session_id).strip() if session_id else None,
            request_id=str(request_id).strip() if request_id else f"req-{uuid.uuid4().hex[:12]}",
            confirmation_state=confirmation_state,
            trace_metadata=extra_metadata or {},
            is_authenticated=True,
        )

    def is_enterprise_level(self) -> bool:
        """Check whether the user role has organization-wide visibility."""
        role_lower = self.user_role.lower()
        return any(
            r in role_lower
            for r in ["super admin", "admin", "risk head", "risk manager", "management", "auditor", "executive", "ceo", "board"]
        )

    def to_safe_trace_dict(self) -> Dict[str, Any]:
        """Export sanitized representation for observability without leaking sensitive session payloads."""
        return {
            "request_id": self.request_id,
            "run_id": self.run_id,
            "user_id": self.user_id,
            "user_role": self.user_role,
            "dept_id": self.dept_id,
            "dept_name": self.dept_name,
            "session_id": self.session_id,
            "is_enterprise": self.is_enterprise_level(),
            "timestamp": self.created_at.isoformat(),
        }
