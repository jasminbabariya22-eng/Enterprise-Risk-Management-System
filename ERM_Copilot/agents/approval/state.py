"""
State definition for LangGraph Conversational Risk Approval / Rejection Workflow.
"""
from typing import TypedDict, Optional, Literal, Dict, Any, List


class ApprovalState(TypedDict, total=False):
    """
    Type definition for the approval workflow state.
    Preserves collected decision parameters across conversational turns.
    """
    session_id: str
    user_id: Optional[str]
    user_role: Optional[str]
    dept_id: Optional[int]
    dept_name: Optional[str]
    
    # Core decision parameters
    risk_id: Optional[str]
    action: Optional[Literal["approve", "reject"]]
    remark: Optional[str]
    
    # State flags
    awaiting_risk_id: bool
    awaiting_action: bool
    awaiting_remark: bool
    awaiting_confirmation: bool
    confirmed: bool
    cancelled: bool
    is_completed: bool
    
    # Results & Messages
    api_result: Optional[Dict[str, Any]]
    error: Optional[str]
    response_message: Optional[str]
    step_code: Optional[str]
    
    # Conversational turn history
    last_user_message: Optional[str]
    messages: List[Dict[str, str]]
