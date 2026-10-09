"""
Bounded Retry and Failure Recovery Policy for ERM AI Harness.
Guarantees that only safe, idempotent, read-only tools are eligible for automatic retry.
Strictly blocks automatic retries of state-changing actions (risk save, approval, treatment modification).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Type
from ERM_Copilot.ai_harness.exceptions import (
    AuthenticationError,
    AuthorizationError,
    BoundedExecutionError,
    ConfirmationError,
    ConfirmationMismatchError,
    ConfirmationRequiredError,
    GuardrailViolationError,
    NonIdempotentRetryError,
    ToolValidationError,
)

logger = logging.getLogger("ERM_Copilot.ai_harness.retry")

# Exceptions that represent permanent/client/policy failures and should NEVER be retried
NON_RETRYABLE_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    AuthenticationError,
    AuthorizationError,
    ToolValidationError,
    ConfirmationRequiredError,
    ConfirmationMismatchError,
    GuardrailViolationError,
    NonIdempotentRetryError,
    ValueError,
    TypeError,
    KeyError,
)


class RetryPolicy:
    """
    Evaluates failure eligibility and applies bounded exponential backoff.
    """

    DEFAULT_MAX_RETRIES = 2
    INITIAL_BACKOFF_SECONDS = 0.2
    BACKOFF_MULTIPLIER = 2.0

    @classmethod
    def is_transient_error(cls, exc: Exception) -> bool:
        """Determine if an exception represents a transient network/timeout failure."""
        if isinstance(exc, NON_RETRYABLE_EXCEPTIONS):
            return False

        exc_str = str(exc).lower()
        transient_indicators = [
            "timeout", "timed out", "connection reset", "connection refused",
            "503", "502", "504", "temporary failure", "rate limit", "busy"
        ]
        return any(ind in exc_str for ind in transient_indicators) or isinstance(exc, (TimeoutError, ConnectionError))

    @classmethod
    def execute_with_retry(
        cls,
        func: Callable[[], Any],
        tool_name: str,
        is_idempotent: bool,
        is_state_changing: bool,
        max_retries: int = DEFAULT_MAX_RETRIES,
        timeout_seconds: Optional[float] = None,
    ) -> Tuple[Any, int]:
        """
        Execute a function with strict safety guards around retries.
        
        Returns:
            Tuple[Any, int]: (result, retry_count)
        """
        # Strict rule: NEVER retry state-changing actions automatically
        if is_state_changing or not is_idempotent:
            try:
                result = func()
                return result, 0
            except Exception as e:
                logger.warning(
                    f"[RETRY_BLOCKED] Tool '{tool_name}' failed with error: {e}. "
                    f"Automatic retry rejected because tool is state-changing (idempotent={is_idempotent})."
                )
                raise e

        # Safe read-only / idempotent retry loop
        attempts = 0
        current_delay = cls.INITIAL_BACKOFF_SECONDS

        while attempts <= max_retries:
            try:
                result = func()
                return result, attempts
            except Exception as e:
                attempts += 1
                if attempts > max_retries or not cls.is_transient_error(e):
                    logger.error(
                        f"[RETRY_EXHAUSTED] Tool '{tool_name}' failed after {attempts - 1} retries. Error: {e}"
                    )
                    raise e

                logger.info(
                    f"[RETRYING] Transient error in tool '{tool_name}' (attempt {attempts}/{max_retries}): {e}. "
                    f"Waiting {current_delay:.2f}s..."
                )
                time.sleep(current_delay)
                current_delay *= cls.BACKOFF_MULTIPLIER

        raise BoundedExecutionError(f"Tool '{tool_name}' failed after {max_retries} retry attempts.")
