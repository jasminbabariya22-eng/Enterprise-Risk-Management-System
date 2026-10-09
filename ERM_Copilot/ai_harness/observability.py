"""
Observability and Structured Execution Tracing for ERM AI Harness.
Captures runtime traces, tool latency, retries, and confirmation lifecycles
while strictly redacting sensitive credentials, tokens, and personal secrets.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ERM_Copilot.ai_harness.observability")

# Regex patterns for masking sensitive data in logs/traces
SENSITIVE_PATTERNS = [
    (re.compile(r'(?i)(bearer\s+)[A-Za-z0-9_\-\.]{10,}'), r'\1[REDACTED_TOKEN]'),
    (re.compile(r'(?i)("?(?:password|passwd|secret|api_key|token|auth_token)"?\s*[:=]\s*"?)[^",\s}]+("?)'), r'\1[REDACTED]\2'),
    (re.compile(r'(?i)(authorization:\s*)[^\r\n]+'), r'\1[REDACTED]'),
    (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b'), r'[REDACTED_EMAIL]'),
]


def sanitize_trace_payload(data: Any) -> Any:
    """Recursively mask sensitive values in dictionaries, lists, and strings."""
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            k_str = str(k).lower()
            if any(s in k_str for s in ["password", "secret", "token", "api_key", "auth"]):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = sanitize_trace_payload(v)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_trace_payload(item) for item in data]
    elif isinstance(data, str):
        text = data
        for pattern, replacement in SENSITIVE_PATTERNS:
            text = pattern.sub(replacement, text)
        return text
    return data


class TraceSpan:
    """Individual execution span within a governed AI request."""

    def __init__(self, name: str, span_type: str, run_id: str, request_id: str, metadata: Optional[Dict[str, Any]] = None):
        self.name = name
        self.span_type = span_type
        self.run_id = run_id
        self.request_id = request_id
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.duration_ms: Optional[float] = None
        self.success: bool = True
        self.error_category: Optional[str] = None
        self.error_message: Optional[str] = None
        self.retry_count: int = 0
        self.metadata: Dict[str, Any] = sanitize_trace_payload(metadata or {})

    def complete(self, success: bool = True, error: Optional[Exception] = None, retry_count: int = 0, extra_metadata: Optional[Dict[str, Any]] = None):
        self.end_time = time.time()
        self.duration_ms = round((self.end_time - self.start_time) * 1000, 2)
        self.success = success
        self.retry_count = retry_count
        if error:
            self.error_category = error.__class__.__name__
            self.error_message = sanitize_trace_payload(str(error))
        if extra_metadata:
            self.metadata.update(sanitize_trace_payload(extra_metadata))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "span_type": self.span_type,
            "run_id": self.run_id,
            "request_id": self.request_id,
            "start_time": datetime.fromtimestamp(self.start_time, tz=timezone.utc).isoformat(),
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error_category": self.error_category,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "metadata": self.metadata,
        }


class ObservabilityTracer:
    """
    Central recorder for AI Harness observability and telemetry.
    """

    def __init__(self):
        self._active_spans: Dict[str, TraceSpan] = {}
        self._completed_traces: List[Dict[str, Any]] = []

    def start_span(self, name: str, span_type: str, run_id: str, request_id: str, metadata: Optional[Dict[str, Any]] = None) -> TraceSpan:
        span = TraceSpan(name=name, span_type=span_type, run_id=run_id, request_id=request_id, metadata=metadata)
        logger.info(
            f"[AI_TRACE_START] span='{name}' type='{span_type}' run_id='{run_id}' req_id='{request_id}' metadata={span.metadata}"
        )
        return span

    def record_span(self, span: TraceSpan):
        trace_data = span.to_dict()
        self._completed_traces.append(trace_data)
        if len(self._completed_traces) > 1000:
            self._completed_traces.pop(0)

        level = logging.INFO if span.success else logging.WARNING
        logger.log(
            level,
            f"[AI_TRACE_END] span='{span.name}' status={'OK' if span.success else 'FAIL'} "
            f"duration={span.duration_ms}ms retries={span.retry_count} run_id='{span.run_id}'"
        )

    def log_event(self, event_name: str, run_id: str, request_id: str, payload: Optional[Dict[str, Any]] = None):
        safe_payload = sanitize_trace_payload(payload or {})
        logger.info(f"[AI_EVENT] event='{event_name}' run_id='{run_id}' req_id='{request_id}' data={safe_payload}")


observability_tracer = ObservabilityTracer()
