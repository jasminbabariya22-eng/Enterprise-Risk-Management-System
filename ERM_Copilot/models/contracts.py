"""
Base contracts and execution models for ERM Copilot.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class AgentRequest(BaseModel):
    message: str
    user_id: Optional[str] = "5"
    user_role: Optional[str] = "Risk Owner"
    session_id: Optional[str] = None
    created_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    parameters: Dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    request_id: str
    agent_id: str
    status: str = "success"
    success: bool = True
    response: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RequestContext(BaseModel):
    request_id: str
    user_id: Optional[str] = "5"
    session_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
