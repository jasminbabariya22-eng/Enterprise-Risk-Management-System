"""
ERM AI Harness Exception Hierarchy.
Structured, specific exceptions for governance, authentication, authorization,
guardrails, confirmation lifecycle, and tool execution.
"""
from typing import Optional, Dict, Any


class HarnessError(Exception):
    """Base exception for all ERM AI Harness operations."""
    def __init__(self, message: str, status_code: int = 500, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "status_code": self.status_code,
            "details": self.details,
        }


class AuthenticationError(HarnessError):
    """Raised when trusted user identity or required authentication context is missing or invalid."""
    def __init__(self, message: str = "Missing or invalid trusted authentication context.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=401, details=details)


class AuthorizationError(HarnessError):
    """Raised when an authenticated user attempts an operation or tool outside their authorized RBAC scope."""
    def __init__(self, message: str = "User role is not authorized for this operation.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=403, details=details)


class ToolNotFoundError(HarnessError):
    """Raised when an unregistered or disabled tool is requested."""
    def __init__(self, tool_name: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(f"Tool '{tool_name}' is not registered or supported by the ERM harness.", status_code=404, details=details)
        self.tool_name = tool_name


class ToolValidationError(HarnessError):
    """Raised when tool arguments fail schema or business parameter validation."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=400, details=details)


class ConfirmationRequiredError(HarnessError):
    """Raised when a state-changing operation requires explicit human confirmation before execution."""
    def __init__(self, message: str, confirmation_token: Optional[str] = None, pending_action: Optional[Dict[str, Any]] = None):
        details = {
            "requires_confirmation": True,
            "confirmation_token": confirmation_token,
            "pending_action": pending_action or {}
        }
        super().__init__(message, status_code=200, details=details)
        self.confirmation_token = confirmation_token
        self.pending_action = pending_action or {}


class ConfirmationError(HarnessError):
    """Base exception for confirmation errors."""
    def __init__(self, message: str = "Confirmation error.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=400, details=details)


class ConfirmationMismatchError(ConfirmationError):
    """Raised when a confirmation token/fingerprint does not match the pending action or user."""
    def __init__(self, message: str = "Confirmation mismatch or stale confirmation state.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details=details)



class GuardrailViolationError(HarnessError):
    """Raised when input/output fails security, safety, or compliance guardrails."""
    def __init__(self, message: str = "Request blocked by safety and compliance guardrails.", reason: str = "SECURITY_VIOLATION", details: Optional[Dict[str, Any]] = None):
        d = details or {}
        d["reason"] = reason
        super().__init__(message, status_code=400, details=d)
        self.reason = reason


class BoundedExecutionError(HarnessError):
    """Raised when execution exceeds iteration limit or timeout bounds."""
    def __init__(self, message: str = "Execution iteration or timeout limit exceeded.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=504, details=details)


class NonIdempotentRetryError(HarnessError):
    """Raised when an attempt is made to automatically retry a non-idempotent state-changing operation."""
    def __init__(self, tool_name: str, details: Optional[Dict[str, Any]] = None):
        msg = f"Automatic retry blocked: tool '{tool_name}' performs non-idempotent state modification."
        super().__init__(msg, status_code=409, details=details)
        self.tool_name = tool_name
