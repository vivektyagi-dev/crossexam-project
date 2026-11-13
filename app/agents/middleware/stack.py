"""The safety layers around every agent, in order (outermost first).

    PIIMiddleware (built-in)          - bank account and IFSC numbers masked
    InjectionGuardMiddleware (custom) - instructions hidden in documents removed + flagged
    ModelCallLimitMiddleware          - caps AI calls per run
    ToolCallLimitMiddleware           - caps tool calls per run
    SummarizationMiddleware           - long investigations keep fitting (exception agent)
    ModelFallbackMiddleware           - backup model when the main one fails
    ModelRetryMiddleware              - retries transient errors with backoff
    RateLimitMiddleware (custom)      - shared requests-per-minute budget
    CostLedgerMiddleware (custom)     - tokens, cost, latency per real call
    ConfidenceGateMiddleware (custom) - low confidence -> person
    HumanInTheLoopMiddleware          - write tools wait for a person's approval
"""

from __future__ import annotations

import re

from langchain.agents.middleware import (
    HumanInTheLoopMiddleware,
    ModelCallLimitMiddleware,
    ModelFallbackMiddleware,
    ModelRetryMiddleware,
    PIIMatch,
    PIIMiddleware,
    SummarizationMiddleware,
    ToolCallLimitMiddleware,
)

from app.agents.llm import get_chat_model
from app.agents.middleware.custom import (
    ConfidenceGateMiddleware,
    CostLedgerMiddleware,
    InjectionGuardMiddleware,
    RateLimitMiddleware,
)
from app.config import settings

# "A/C No: 001234567890" style account numbers. A bare 9-18 digit regex would also mask
# 12-digit e-way bill numbers, which the agents need to read.
_ACCOUNT_RE = re.compile(r"(?i)\b(?:a/?c|acct|account)\s*(?:no\.?|number|#)?\s*[:\-]?\s*(\d{9,18})\b")
_IFSC_RE = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")


def detect_bank_account(text: str) -> list[PIIMatch]:
    return [PIIMatch(type="bank_account", value=m.group(1), start=m.start(1), end=m.end(1))
            for m in _ACCOUNT_RE.finditer(text)]


def detect_ifsc(text: str) -> list[PIIMatch]:
    return [PIIMatch(type="ifsc", value=m.group(0), start=m.start(), end=m.end()) for m in _IFSC_RE.finditer(text)]


def build_middleware(*, kind: str, hitl_tools: dict | None = None, gate_confidence: bool = True) -> list:
    """kind: classifier | extractor | reconciler | supervisor | exception."""
    stack = [
        PIIMiddleware("bank_account", detector=detect_bank_account, strategy="mask",
                      apply_to_input=True, apply_to_tool_results=True),
        PIIMiddleware("ifsc", detector=detect_ifsc, strategy="mask",
                      apply_to_input=True, apply_to_tool_results=True),
        InjectionGuardMiddleware(),
        ModelCallLimitMiddleware(run_limit=settings.max_model_calls_per_run, exit_behavior="end"),
        ToolCallLimitMiddleware(run_limit=settings.max_tool_calls_per_run, exit_behavior="continue"),
    ]
    if kind == "exception":
        stack.append(SummarizationMiddleware(model=get_chat_model("small"), trigger=("tokens", 60_000),
                                             keep=("messages", 12)))
    stack += [
        ModelFallbackMiddleware(get_chat_model("fallback")),
        ModelRetryMiddleware(max_retries=2, initial_delay=2.0, on_failure="error"),
        RateLimitMiddleware(),
        CostLedgerMiddleware(),
    ]
    if gate_confidence:
        stack.append(ConfidenceGateMiddleware())
    if hitl_tools:
        stack.append(HumanInTheLoopMiddleware(interrupt_on=hitl_tools,
                                              description_prefix="Approval needed before this action runs"))
    return stack
