"""The five agents, all built with LangChain v1 `create_agent` and the same middleware stack.

    Supervisor ──calls──> Reconciler (as a tool)       one per shipment pack
    Classifier                                          one per uploaded file
    Extractors (one per document family)                one per document
    Exception resolver (own resumable thread, human approval for writes)

Celery orchestrates volume (thousands of documents in parallel); the supervisor
orchestrates judgement inside one pack.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import HumanMessage

from app.agents import prompts
from app.agents.context import AgentContext
from app.agents.llm import get_chat_model, model_name
from app.agents.middleware.stack import build_middleware
from app.agents.tools.read_tools import (
    CLASSIFIER_TOOLS,
    EXCEPTION_READ_TOOLS,
    EXTRACTOR_TOOLS,
    RECONCILER_TOOLS,
    match_engine,
    pack_overview,
)
from app.agents.tools.write_tools import HITL_CONFIG, WRITE_TOOLS
from app.config import settings
from app.schemas import (
    DOC_FAMILY,
    SCHEMA_BY_TYPE,
    Classification,
    DocType,
    ExceptionFinding,
    ReconciliationReport,
    SupervisorDecision,
)

MAX_DOC_CHARS = 60_000


def _document_message(header: str, text: str) -> HumanMessage:
    return HumanMessage(f"{header}\n<document>\n{text[:MAX_DOC_CHARS]}\n</document>")


# ----------------------------------------------------------------------------- classifier
def build_classifier():
    return create_agent(
        get_chat_model("small"), tools=CLASSIFIER_TOOLS, system_prompt=prompts.CLASSIFIER,
        middleware=build_middleware(kind="classifier"), response_format=ToolStrategy(Classification),
        context_schema=AgentContext, name="classifier",
    )


def classify(page_texts: list[str], filename: str, ctx: AgentContext) -> Classification:
    pages = "\n\n".join(f"=== PAGE {i + 1} ===\n{t[:3000]}" for i, t in enumerate(page_texts))
    msg = _document_message(f"File: {filename}\nPages: {len(page_texts)}", pages)
    result = build_classifier().invoke({"messages": [msg]}, context=ctx, config=ctx.run_config())
    out: Classification = result["structured_response"]
    return _repair_segments(out, len(page_texts))


def _repair_segments(c: Classification, n_pages: int) -> Classification:
    """Code, not AI, guarantees every page is covered exactly once and in order."""
    segs = sorted(c.segments, key=lambda s: s.start_page)
    fixed = []
    expected = 1
    for seg in segs:
        start = max(seg.start_page, expected)
        end = min(max(seg.end_page, start), n_pages)
        if start > n_pages:
            break
        if start > expected and fixed:  # gap: extend the previous segment
            fixed[-1].end_page = start - 1
        elif start > expected:
            start = expected
        seg.start_page, seg.end_page = start, end
        fixed.append(seg)
        expected = end + 1
    if not fixed:
        from app.schemas import Segment

        fixed = [Segment(doc_type=DocType.other, start_page=1, end_page=n_pages, reason="unclassified")]
    if fixed[-1].end_page < n_pages:
        fixed[-1].end_page = n_pages
    c.segments = fixed
    return c


# ----------------------------------------------------------------------------- extractors
@lru_cache(maxsize=32)
def build_extractor(doc_type: str, tier: str):
    schema = SCHEMA_BY_TYPE[DocType(doc_type)]
    family = DOC_FAMILY[DocType(doc_type)]
    return create_agent(
        get_chat_model(tier), tools=EXTRACTOR_TOOLS,
        system_prompt=prompts.EXTRACTOR.format(family=family, schema=schema.__name__),
        middleware=build_middleware(kind="extractor"), response_format=ToolStrategy(schema),
        context_schema=AgentContext, name=f"extractor_{family}",
    )


def extract(doc_type: str, text: str, filename: str, ctx: AgentContext, tier: str = "small",
            feedback: list[str] | None = None) -> tuple[dict, float, str]:
    header = f"File: {filename}\nDocument type: {doc_type}"
    if feedback:
        header += ("\nA previous reading failed these checks - re-read carefully: " + ", ".join(feedback))
    agent = build_extractor(doc_type, tier)
    result = agent.invoke({"messages": [_document_message(header, text)]}, context=ctx,
                          config=ctx.run_config([doc_type, tier]))
    data = result["structured_response"].model_dump(mode="json")
    return data, float(data.get("confidence", 0.0)), model_name(get_chat_model(tier))


# ----------------------------------------------------------------------------- reconciler
def build_reconciler():
    return create_agent(
        get_chat_model("mid"), tools=RECONCILER_TOOLS, system_prompt=prompts.RECONCILER,
        middleware=build_middleware(kind="reconciler", gate_confidence=False),
        response_format=ToolStrategy(ReconciliationReport), context_schema=AgentContext, name="reconciler",
    )


def reconcile(ctx: AgentContext) -> ReconciliationReport:
    sub = AgentContext(agent="reconciler", batch_id=ctx.batch_id, pack_id=ctx.pack_id, flags=ctx.flags)
    result = build_reconciler().invoke(
        {"messages": [HumanMessage("Reconcile this shipment pack.")]}, context=sub, config=sub.run_config())
    return result["structured_response"]


# ----------------------------------------------------------------------------- supervisor
@tool
def run_reconciler(runtime: ToolRuntime[AgentContext]) -> str:
    """Ask the reconciliation specialist to link stray papers and run the match engine."""
    report = reconcile(runtime.context)
    from app.services.pipeline import link_documents

    linked = link_documents(runtime.context.pack_id, report.linked_document_ids)
    return json.dumps({**report.model_dump(), "linked_document_ids": linked})


def build_supervisor():
    return create_agent(
        get_chat_model("small"), tools=[run_reconciler, pack_overview, match_engine],
        system_prompt=prompts.SUPERVISOR, middleware=build_middleware(kind="supervisor"),
        response_format=ToolStrategy(SupervisorDecision), context_schema=AgentContext, name="supervisor",
    )


def supervise(ctx: AgentContext) -> SupervisorDecision:
    result = build_supervisor().invoke(
        {"messages": [HumanMessage("Decide where this shipment pack goes next.")]}, context=ctx,
        config=ctx.run_config())
    return result["structured_response"]


# ----------------------------------------------------------------------------- exception resolver
_saver = None


def _checkpointer():
    """Postgres checkpointer: the agent's thread survives worker restarts, so a person can
    approve hours later and any worker can resume it."""
    global _saver
    if _saver is None:
        import atexit

        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg_pool import ConnectionPool

        pool = ConnectionPool(settings.psycopg_dsn, max_size=5, open=True,
                              kwargs={"autocommit": True, "prepare_threshold": 0})
        atexit.register(pool.close)
        _saver = PostgresSaver(pool)
    return _saver


def use_checkpointer(saver) -> None:
    """Tests inject an in-memory saver."""
    global _saver
    _saver = saver


def build_exception_agent():
    return create_agent(
        get_chat_model("strong"), tools=[*EXCEPTION_READ_TOOLS, *WRITE_TOOLS], system_prompt=prompts.EXCEPTION,
        middleware=build_middleware(kind="exception", hitl_tools=HITL_CONFIG),
        response_format=ToolStrategy(ExceptionFinding), context_schema=AgentContext,
        checkpointer=_checkpointer(), name="exception_resolver",
    )


def run_exception_agent(ctx: AgentContext, thread_id: str, resume: dict | None = None) -> dict[str, Any]:
    """Start (resume=None) or resume an investigation. Returns
    {"interrupt": [...action requests...]} when waiting for a person, or
    {"finding": ExceptionFinding} when finished."""
    from langgraph.types import Command

    agent = build_exception_agent()
    config = {**ctx.run_config(), "configurable": {"thread_id": thread_id}}
    payload: Any = Command(resume=resume) if resume is not None else {
        "messages": [HumanMessage("Investigate this shipment pack and propose a resolution.")]}
    result = agent.invoke(payload, context=ctx, config=config)
    interrupts = result.get("__interrupt__") or []
    if interrupts:
        value = interrupts[0].value
        return {"interrupt": value.get("action_requests", []), "review_configs": value.get("review_configs", [])}
    return {"finding": result.get("structured_response")}
