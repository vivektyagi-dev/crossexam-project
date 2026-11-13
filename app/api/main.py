"""The front desk: receives uploads, answers status questions, records human decisions.
It never waits for AI work - it saves, queues and replies straight away.

Authentication: the API trusts the X-User and X-Role headers forwarded by the web screen. On
GCP, put Identity-Aware Proxy (or Cloud Run IAM) in front of both services; never expose
this API publicly without it.
"""

from __future__ import annotations

import csv
import io
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

import redis
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import cast, func, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import (
    Batch,
    DocStatus,
    Document,
    EmailOutbox,
    Extraction,
    LLMCall,
    PackStatus,
    PendingAction,
    Priority,
    ReviewAction,
    ShipmentPack,
)
from app.db.session import get_db, session_scope
from app.ingestion.readers import spreadsheet_rows
from app.ingestion.storage import get_storage
from app.observability.logging import bind, configure_logging, get_logger
from app.observability.metrics import (
    register_activity_gauges,
    register_queue_gauge,
    register_status_gauges,
    setup_metrics,
)
from app.observability.tracing import current_trace_id, setup_tracing
from app.services import pipeline
from app.services.packs import pack_documents
from app.services.quality import quality_snapshot
from app.workers.celery_app import AGENT_QUEUES, READER_QUEUES

configure_logging()
log = get_logger(__name__)
_redis = redis.Redis.from_url(settings.redis_url)


def queue_lengths() -> dict[str, int]:
    return {q: int(_redis.llen(q)) for q in READER_QUEUES + AGENT_QUEUES}


def status_counts(model, statuses) -> dict[str, int]:
    """Every status is reported, so one that empties drops to 0 instead of vanishing."""
    with session_scope() as s:
        counts = dict(s.execute(select(model.status, func.count()).group_by(model.status)).all())
    return {st.value: counts.get(st, 0) for st in statuses}


def ai_spend() -> Decimal:
    with session_scope() as s:
        return s.scalar(select(func.coalesce(func.sum(LLMCall.cost_usd), 0)))


def injection_documents() -> int:
    """Documents the injection guard cleaned. A split bundle counts through its parts, which
    inherit its flags."""
    with session_scope() as s:
        return s.scalar(select(func.count()).select_from(Document).where(
            cast(Document.flags, JSONB).contains(["possible_injection"]), Document.status != DocStatus.split))


# The dashboard's activity panels: recent windows read from the database, like /stats.
RATE_MINUTES = 5  # "per minute" panels average over this window
ROUTES = ("auto_approve", "investigate", "human_review")


def _since(**window) -> datetime:
    return datetime.now(UTC) - timedelta(**window)


def documents_per_minute() -> dict[str, float]:
    since = _since(minutes=RATE_MINUTES)
    with session_scope() as s:
        extracted = s.scalar(select(func.count()).select_from(Extraction).where(Extraction.created_at >= since))
        failed = s.scalar(select(func.count()).select_from(Document).where(
            Document.status == DocStatus.failed, Document.updated_at >= since))
    return {"extracted": extracted / RATE_MINUTES, "failed": failed / RATE_MINUTES}


def packs_routed_last_hour() -> dict[str, int]:
    """Same definition as the routes on the Monitoring page: packs created in the window."""
    with session_scope() as s:
        counts = dict(s.execute(select(ShipmentPack.route, func.count()).where(
            ShipmentPack.created_at >= _since(hours=1), ShipmentPack.route.isnot(None), ShipmentPack.route != "wait")
            .group_by(ShipmentPack.route)).all())
    return {**dict.fromkeys(ROUTES, 0), **counts}


def ai_spend_last_hour_by_agent() -> dict[str, Decimal]:
    with session_scope() as s:
        return dict(s.execute(select(LLMCall.agent, func.sum(LLMCall.cost_usd))
                              .where(LLMCall.created_at >= _since(hours=1)).group_by(LLMCall.agent)).all())


def tokens_per_minute() -> dict[str, float]:
    with session_scope() as s:
        tokens_in, tokens_out = s.execute(
            select(func.coalesce(func.sum(LLMCall.input_tokens), 0), func.coalesce(func.sum(LLMCall.output_tokens), 0))
            .where(LLMCall.created_at >= _since(minutes=RATE_MINUTES))).one()
    return {"input": tokens_in / RATE_MINUTES, "output": tokens_out / RATE_MINUTES}


def llm_latency_p95() -> dict[str, float]:
    """Seconds, per model."""
    with session_scope() as s:
        rows = s.execute(select(LLMCall.model, func.percentile_cont(0.95).within_group(LLMCall.latency_ms))
                         .where(LLMCall.created_at >= _since(minutes=RATE_MINUTES)).group_by(LLMCall.model)).all()
    return {model: ms / 1000 for model, ms in rows}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_metrics(start_http_server=False)  # the API serves /metrics itself
    register_queue_gauge(queue_lengths)
    register_status_gauges(documents=lambda: status_counts(Document, DocStatus),
                           packs=lambda: status_counts(ShipmentPack, PackStatus), spend=ai_spend,
                           injections=injection_documents)
    register_activity_gauges(documents_per_minute=documents_per_minute, packs_routed=packs_routed_last_hour,
                             spend_by_agent=ai_spend_last_hour_by_agent, tokens_per_minute=tokens_per_minute,
                             latency_p95=llm_latency_p95)
    yield


app = FastAPI(title="CrossExam API", description="Multi-agent cross-examination of supply-chain documents", version="0.2.0", lifespan=lifespan)
setup_tracing(fastapi_app=app, celery=True)  # celery: the tasks an upload queues continue its trace


Role = Literal["ap_executive", "finance_manager"]


def user(x_user: str = Header(default="anonymous"), x_role: Role = Header(default="ap_executive")):
    return {"name": x_user, "role": x_role}


# ------------------------------------------------------------------------------- health
@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/readyz")
def readyz(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    _redis.ping()
    return {"ok": True}


@app.get("/metrics")
def prometheus_metrics():
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ------------------------------------------------------------------------------- batches
@app.post("/batches")
async def create_batch(files: list[UploadFile] = File(...), name: str = Form(""),
                       priority: Priority = Form(Priority.normal), u=Depends(user), db: Session = Depends(get_db)):
    from app.workers.tasks import enqueue_document

    batch = Batch(name=name or f"Upload by {u['name']}", priority=priority, created_by=u["name"])
    db.add(batch)
    db.flush()
    bind(batch_id=batch.id)
    created, duplicates = [], []
    trace_id = current_trace_id()
    for f in files:
        data = await f.read()
        doc, is_new = pipeline.ingest_file(db, batch, f.filename or "upload.bin", data)
        if is_new:
            doc.trace_id = trace_id
            created.append(doc.id)
        else:
            duplicates.append({"filename": f.filename, "existing_document_id": doc.id})
    if not created:
        batch.status = "grouped"  # nothing new to process
    db.commit()
    for doc_id in created:  # enqueue only after commit, so workers can see the rows
        enqueue_document(doc_id, priority.value)
    log.info("batch_created", files=len(files), new=len(created), duplicates=len(duplicates))
    return {"batch_id": batch.id, "accepted": len(created), "duplicate_files": duplicates}


@app.get("/batches")
def list_batches(db: Session = Depends(get_db)):
    rows = db.scalars(select(Batch).order_by(Batch.created_at.desc()).limit(50)).all()
    return [{"id": b.id, "name": b.name, "priority": b.priority.value, "status": b.status,
             "created_at": b.created_at, "created_by": b.created_by} for b in rows]


@app.get("/batches/{batch_id}")
def batch_status(batch_id: str, db: Session = Depends(get_db)):
    batch = db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404, "batch not found")
    live = {k.decode(): int(v) for k, v in (_redis.hgetall(f"progress:{batch_id}") or {}).items()}
    return {"id": batch.id, "name": batch.name, "status": batch.status, "priority": batch.priority.value,
            "live_counters": live, **pipeline.batch_progress(db, batch_id),
            "queues": queue_lengths()}


# ------------------------------------------------------------------------------- packs
def _pack_summary(p: ShipmentPack) -> dict:
    return {"id": p.id, "batch_id": p.batch_id, "po_number": p.po_number, "supplier_gstin": p.supplier_gstin,
            "status": p.status.value, "issue_codes": p.issue_codes, "invoice_total": p.invoice_total,
            "payable_amount": p.payable_amount, "finding": p.finding, "flags": p.flags,
            "updated_at": p.updated_at}


@app.get("/packs")
def list_packs(status: str | None = None, batch_id: str | None = None, limit: int = 200,
               db: Session = Depends(get_db)):
    q = select(ShipmentPack).order_by(ShipmentPack.updated_at.desc()).limit(limit)
    if status:
        q = q.where(ShipmentPack.status.in_([PackStatus(s) for s in status.split(",")]))
    if batch_id:
        q = q.where(ShipmentPack.batch_id == batch_id)
    return [_pack_summary(p) for p in db.scalars(q).all()]


@app.get("/packs/{pack_id}")
def pack_detail(pack_id: str, db: Session = Depends(get_db)):
    pack = db.get(ShipmentPack, pack_id)
    if not pack:
        raise HTTPException(404, "pack not found")
    docs = [{"id": d.id, "filename": d.filename, "format": d.source_format, "doc_type": e.doc_type if e else d.doc_type,
             "pages": [d.page_start, d.page_end], "flags": d.flags, "duplicate_of": d.duplicate_of,
             "confidence": e.confidence if e else None, "model": e.model if e else None,
             "escalated": e.escalated if e else None, "validation_issues": e.validation_issues if e else [],
             "data": e.data if e else None} for d, e in pack_documents(db, pack_id)]
    actions = db.scalars(select(PendingAction).where(PendingAction.pack_id == pack_id)
                         .order_by(PendingAction.id)).all()
    audit = db.scalars(select(ReviewAction).where(ReviewAction.pack_id == pack_id)
                       .order_by(ReviewAction.created_at)).all()
    cost = db.scalar(select(func.coalesce(func.sum(LLMCall.cost_usd), 0)).where(LLMCall.pack_id == pack_id))
    return {**_pack_summary(pack), "match_result": pack.match_result, "proposal": pack.proposal,
            "documents": docs,
            "actions": [{"id": a.id, "tool": a.tool_name, "args": a.args, "description": a.description,
                         "status": a.status, "requires_role": a.requires_role, "decided_by": a.decided_by}
                        for a in actions],
            "audit": [{"actor": a.actor, "role": a.role, "action": a.action, "detail": a.detail,
                       "at": a.created_at} for a in audit],
            "agent_cost_usd": str(Decimal(cost or 0).quantize(Decimal("0.0001")))}


class Decision(BaseModel):
    action_id: int
    type: Literal["approve", "edit", "reject"]
    args: dict | None = None
    message: str | None = None


class DecisionRequest(BaseModel):
    decisions: list[Decision]


@app.post("/packs/{pack_id}/decisions")
def decide(pack_id: str, body: DecisionRequest, u=Depends(user)):
    """A person approves, edits or rejects the agent's held actions; the agent then resumes."""
    from app.workers.tasks import resume_pack

    try:
        resume = pipeline.record_decisions(pack_id, [d.model_dump() for d in body.decisions], u["name"], u["role"])
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    resume_pack.apply_async((pack_id, resume), queue="agent.urgent")
    return {"queued": True}


class ManualDecision(BaseModel):
    decision: Literal["approve", "reject"]
    comment: str = ""


@app.post("/packs/{pack_id}/manual-decision")
def manual(pack_id: str, body: ManualDecision, u=Depends(user)):
    try:
        pipeline.manual_decision(pack_id, body.decision, u["name"], u["role"], body.comment)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"ok": True}


def _original(db: Session, doc_id: str) -> tuple[Document, bytes]:
    """The uploaded file a document came from (a split bundle's parent, for its children)."""
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "document not found")
    root = db.get(Document, doc.parent_id) if doc.parent_id else doc
    return root, get_storage().get(root.storage_path)


@app.get("/documents/{doc_id}/file")
def document_file(doc_id: str, db: Session = Depends(get_db)):
    root, data = _original(db, doc_id)
    name = root.filename.lower()
    media = ("application/pdf" if name.endswith(".pdf") else "image/png" if name.endswith(".png")
             else "image/jpeg" if name.endswith((".jpg", ".jpeg")) else "application/json" if name.endswith(".json")
             else "application/octet-stream")
    return Response(data, media_type=media)


@app.get("/documents/{doc_id}/table")
def document_table(doc_id: str, db: Session = Depends(get_db)):
    """A spreadsheet original as rows of text, for the review screen."""
    root, data = _original(db, doc_id)
    try:
        return {"sheets": spreadsheet_rows(root.filename, data)}
    except Exception as exc:  # not a spreadsheet, or one pandas cannot open
        raise HTTPException(415, "This original is not a readable spreadsheet.") from exc


# ------------------------------------------------------------------------------- export, outbox, stats
@app.post("/exports")
def export(u=Depends(user)):
    """ERP export of approved invoices. Code only - no agent can call this."""
    export_id, rows = pipeline.export_approved(u["name"])
    buf = io.StringIO()
    fields = ["supplier_gstin", "invoice_number", "invoice_date", "po_number", "invoice_total", "pay_amount",
              "debit_note", "pack_id"]
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename=export-{export_id}.csv",
                                      "X-Export-Rows": str(len(rows))})


@app.get("/outbox")
def outbox(db: Session = Depends(get_db)):
    rows = db.scalars(select(EmailOutbox).order_by(EmailOutbox.created_at.desc()).limit(100)).all()
    return [{"id": r.id, "pack_id": r.pack_id, "to": r.to_address, "subject": r.subject, "body": r.body,
             "status": r.status, "created_at": r.created_at} for r in rows]


@app.get("/stats")
def stats(hours: int = 24 * 30):
    return quality_snapshot(hours=hours)


# ------------------------------------------------------------------------------- admin (Cloud Scheduler)
@app.post("/admin/reap-stale")
def admin_reap():
    from app.workers.tasks import reap_stale

    reap_stale.apply_async(queue="agent.urgent")
    return {"queued": True}


@app.post("/admin/nightly-check")
def admin_nightly():
    from app.workers.tasks import nightly_quality_check

    nightly_quality_check.apply_async(queue="agent.bulk")
    return {"queued": True}
