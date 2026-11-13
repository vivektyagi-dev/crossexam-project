"""Custom middleware. Built-in LangChain middleware is used wherever it exists; these
four cover what the business needs on top:

- InjectionGuardMiddleware: text inside documents is data, never instructions.
- RateLimitMiddleware: one shared requests-per-minute budget for every worker.
- CostLedgerMiddleware: one ledger row per model call (tokens, cost, latency).
- ConfidenceGateMiddleware: low-confidence answers are routed to a person.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agents.context import AgentContext
from app.agents.llm import model_name
from app.config import settings
from app.observability import metrics
from app.observability.logging import get_logger

log = get_logger(__name__)

# Phrases that try to steer an AI. Deliberately broad: a false positive costs one human
# review; a false negative could approve a bad invoice.
INJECTION_PATTERNS = [
    r"ignore (all |any |the )?(previous|prior|above|earlier) (instructions|rules|prompts?)",
    r"disregard (all |the )?(previous|prior|above) ",
    r"\b(you are|act as) (now )?(an? )?(ai|assistant|system|admin)",
    r"\bsystem prompt\b",
    r"note to (the )?(ai|llm|assistant|model|automated)",
    r"(auto[- ]?)?approve (this|the) (invoice|payment|document) (immediately|for immediate|without)",
    r"do not (flag|report|check|verify)",
    r"\bnew instructions?\b",
]

_INJECTION_RE = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)
_REDACTION = "[REMOVED BY SAFETY FILTER: text that attempted to instruct the AI]"


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


def scan_for_injection(text: str) -> list[str]:
    return [m.group(0) for m in _INJECTION_RE.finditer(text or "")]


def _sanitize(content: Any) -> Any:
    def clean(s: str) -> str:
        out_lines = []
        for line in s.splitlines():
            out_lines.append(_REDACTION if _INJECTION_RE.search(line) else line)
        return "\n".join(out_lines)

    if isinstance(content, str):
        return clean(content)
    if isinstance(content, list):
        return [{**b, "text": clean(b["text"])} if isinstance(b, dict) and "text" in b else b for b in content]
    return content


class InjectionGuardMiddleware(AgentMiddleware):
    """Strips instruction-like lines from document text and tool results before every
    model call, and raises the `possible_injection` flag so the pack goes to a person."""

    def wrap_model_call(self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]):
        ctx: AgentContext | None = getattr(request.runtime, "context", None)
        new_messages = []
        hits: list[str] = []
        for msg in request.messages:
            if isinstance(msg, HumanMessage | ToolMessage):
                found = scan_for_injection(_text_of(msg.content))
                if found:
                    hits.extend(found)
                    msg = msg.model_copy(update={"content": _sanitize(msg.content)})
            new_messages.append(msg)
        if hits:
            if ctx is not None:
                ctx.flag("possible_injection", f"Removed: {hits[:3]}")
            metrics.injection_blocked.add(1, {"agent": ctx.agent if ctx else "unknown"})
            log.warning("injection_guard_triggered", matches=hits[:3])
            request = request.override(messages=new_messages)
        return handler(request)


class RateLimitMiddleware(AgentMiddleware):
    def wrap_model_call(self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]):
        if settings.llm_provider != "fake":
            from app.workers.ratelimit import acquire

            waited = acquire()
            if waited > 0.5:
                metrics.ratelimit_wait.record(waited)
        return handler(request)


def _usage(response: ModelResponse | AIMessage) -> tuple[int, int]:
    messages = response.result if isinstance(response, ModelResponse) else [response]
    tin = tout = 0
    for m in messages:
        usage = getattr(m, "usage_metadata", None) or {}
        tin += int(usage.get("input_tokens", 0) or 0)
        tout += int(usage.get("output_tokens", 0) or 0)
    return tin, tout


def cost_of(model: str, tokens_in: int, tokens_out: int) -> Decimal:
    prices = settings.model_prices
    pin, pout = prices.get(model, prices.get("default", (0.0, 0.0)))
    return (Decimal(str(pin)) * tokens_in + Decimal(str(pout)) * tokens_out) / Decimal(1_000_000)


def record_llm_call(ctx: AgentContext | None, model: str, tin: int, tout: int, latency_ms: int, ok: bool) -> None:
    from app.db.models import LLMCall
    from app.db.session import session_scope

    cost = cost_of(model, tin, tout)
    agent = ctx.agent if ctx else "unknown"
    try:
        with session_scope() as s:
            s.add(LLMCall(batch_id=ctx.batch_id if ctx else None, document_id=ctx.document_id if ctx else None,
                          pack_id=ctx.pack_id if ctx else None, agent=agent, model=model, input_tokens=tin,
                          output_tokens=tout, cost_usd=cost, latency_ms=latency_ms, ok=ok))
    except Exception as exc:  # the ledger must never break the pipeline
        log.error("cost_ledger_write_failed", error=str(exc))
    attrs = {"agent": agent, "model": model}
    metrics.llm_tokens.add(tin, {**attrs, "direction": "input"})
    metrics.llm_tokens.add(tout, {**attrs, "direction": "output"})
    metrics.llm_cost.add(float(cost), attrs)
    metrics.llm_latency.record(latency_ms / 1000, attrs)
    metrics.llm_calls.add(1, {**attrs, "ok": str(ok)})


class CostLedgerMiddleware(AgentMiddleware):
    """Innermost wrapper, so it records the model that actually ran (including fallbacks
    and retries) - one row per real API call."""

    def wrap_model_call(self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]):
        ctx: AgentContext | None = getattr(request.runtime, "context", None)
        name = model_name(request.model)
        started = time.perf_counter()
        try:
            response = handler(request)
        except Exception:
            record_llm_call(ctx, name, 0, 0, int((time.perf_counter() - started) * 1000), ok=False)
            raise
        tin, tout = _usage(response)
        record_llm_call(ctx, name, tin, tout, int((time.perf_counter() - started) * 1000), ok=True)
        return response


class ConfidenceGateMiddleware(AgentMiddleware):
    """After the agent finishes, a structured answer below the threshold raises the
    `low_confidence` flag; the pipeline then sends the item to a person."""

    def __init__(self, threshold: float | None = None):
        super().__init__()
        self.threshold = threshold if threshold is not None else settings.confidence_threshold

    def after_agent(self, state, runtime) -> dict[str, Any] | None:
        result = state.get("structured_response")
        ctx: AgentContext | None = getattr(runtime, "context", None)
        conf = getattr(result, "confidence", None)
        if conf is not None and conf < self.threshold and ctx is not None:
            ctx.flag("low_confidence", f"confidence {conf:.2f} < {self.threshold:.2f}")
        return None
