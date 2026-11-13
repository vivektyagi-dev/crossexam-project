"""Structured JSON logs. Every line carries the ids bound for the current unit of work
(batch_id, document_id, pack_id, trace_id), so one search in Cloud Logging returns a
document's whole story across the API, workers and agents.

Cloud Logging reads `severity` and `logging.googleapis.com/trace` from JSON stdout.
"""

from __future__ import annotations

import logging
import sys

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars, merge_contextvars

from app.config import settings

_configured = False


def _gcp_fields(_, method_name, event_dict):
    event_dict["severity"] = method_name.upper().replace("WARN", "WARNING").replace("WARNINGING", "WARNING")
    trace_id = event_dict.get("trace_id")
    if trace_id and settings.gcp_project:
        event_dict["logging.googleapis.com/trace"] = f"projects/{settings.gcp_project}/traces/{trace_id}"
    return event_dict


def _add_trace(_, __, event_dict):
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx and ctx.is_valid:
            event_dict.setdefault("trace_id", format(ctx.trace_id, "032x"))
    except Exception:
        pass
    return event_dict


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=settings.log_level)
    structlog.configure(
        processors=[
            merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _add_trace,
            _gcp_fields,
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(settings.log_level)),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    for noisy in ("httpx", "httpcore", "urllib3", "google_genai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _configured = True


def get_logger(name: str = "crossexam"):
    configure_logging()
    return structlog.get_logger(name)


def bind(**ids) -> None:
    bind_contextvars(**{k: v for k, v in ids.items() if v is not None})


def clear() -> None:
    clear_contextvars()
