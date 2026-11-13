"""The pipeline's steps as plain functions. Celery tasks (app/workers/tasks.py) are thin
wrappers around these, so every step can be tested without a broker.

Every step is safe to run twice:
  1. files are deduplicated by content hash on intake,
  2. work is *claimed* with an atomic UPDATE before it starts (with a lease, so a
     crashed worker's claim expires and the work is picked up again),
  3. AI answers are cached by content hash + model + prompt version,
  4. writes are upserts or carry idempotency keys.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agents.context import AgentContext
from app.config import settings
from app.db.models import (
    TERMINAL_DOC_STATES,
    Batch,
    DocStatus,
    Document,
    Extraction,
    LLMCache,
    PackDocument,
    PackStatus,
    PendingAction,
    Priority,
    ReviewAction,
    ShipmentPack,
)
from app.db.session import session_scope
from app.ingestion.readers import Fmt, read_document, render_page_png
from app.ingestion.storage import get_storage, raw_path, sha256_bytes
from app.observability import metrics
from app.observability.logging import get_logger
from app.rules.match_engine import run_match
from app.rules.normalize import norm_invoice_no, norm_po
from app.rules.validation import validate
from app.schemas import DocType
from app.services.grouping import UnionFind, doc_keys
from app.services.packs import build_snapshot

log = get_logger(__name__)


def now() -> datetime:
    return datetime.now(UTC)


# ============================================================================ intake
def ingest_file(session: Session, batch: Batch, filename: str, data: bytes) -> tuple[Document, bool]:
    """Save the file and register it. Returns (document, is_new). A file seen before
    returns the existing document and creates no work (dedupe layer 1)."""
    file_hash = sha256_bytes(data)
    existing = session.scalars(select(Document).where(Document.file_hash == file_hash)).first()
    if existing:
        return existing, False
    path = get_storage().put(raw_path(file_hash, filename), data)
    doc = Document(batch_id=batch.id, file_hash=file_hash, filename=filename, storage_path=path,
                   status=DocStatus.queued)
    session.add(doc)
    try:
        session.flush()
    except IntegrityError:  # a concurrent upload of the same bytes won the race
        session.rollback()
        return session.scalars(select(Document).where(Document.file_hash == file_hash)).one(), False
    return doc, True


# ============================================================================ claiming
def claim_document(doc_id: str, from_states: set[DocStatus], to_state: DocStatus) -> bool:
    """Atomically move a document into a working state. Only one worker wins. A claim
    older than the lease is considered abandoned (worker crashed) and can be re-claimed."""
    stale = now() - timedelta(seconds=settings.claim_lease_seconds)
    with session_scope() as s:
        res = s.execute(
            update(Document)
            .where(Document.id == doc_id,
                   or_(Document.status.in_(from_states),
                       and_(Document.status == to_state, Document.claimed_at < stale)))
            .values(status=to_state, claimed_at=now(), attempts=Document.attempts + 1)
            .returning(Document.id)
        ).first()
        return res is not None


def claim_pack(pack_id: str, from_states: set[PackStatus], to_state: PackStatus) -> bool:
    stale = now() - timedelta(seconds=settings.claim_lease_seconds)
    with session_scope() as s:
        res = s.execute(
            update(ShipmentPack)
            .where(ShipmentPack.id == pack_id,
                   or_(ShipmentPack.status.in_(from_states),
                       and_(ShipmentPack.status == to_state, ShipmentPack.claimed_at < stale)))
            .values(status=to_state, claimed_at=now())
            .returning(ShipmentPack.id)
        ).first()
        return res is not None


def ctx_for_document(doc: Document, agent: str) -> AgentContext:
    return AgentContext(agent=agent, batch_id=doc.batch_id, document_id=doc.id)


def fail_document(doc_id: str, error: str) -> None:
    with session_scope() as s:
        doc = s.get(Document, doc_id)
        doc.status = DocStatus.failed
        doc.error = error[:2000]
    metrics.docs_processed.add(1, {"outcome": "failed"})


# ============================================================================ step 1: read
def read_step(doc_id: str) -> dict[str, Any]:
    """Detect the format and get page texts. Returns
    {"next": "vision", "pages": [...]} | {"next": "classify"} | {"next": "done"}."""
    if not claim_document(doc_id, {DocStatus.queued}, DocStatus.reading):
        return {"next": "skip"}
    with session_scope() as s:
        doc = s.get(Document, doc_id)
        data = get_storage().get(doc.storage_path)
        result = read_document(doc.filename, data, settings.max_pages_per_document)
        doc.source_format = result.fmt
        if result.structured is not None:
            # Government JSON: already structured; no AI at all.
            doc.doc_type = result.structured["doc_type"]
            doc.page_texts = []
            _save_extraction(s, doc, result.structured["doc_type"], result.structured["data"], 1.0,
                             model="none:gov-json", escalated=False)
            doc.status = DocStatus.extracted
            metrics.docs_processed.add(1, {"outcome": "extracted", "doc_type": doc.doc_type, "format": doc.source_format})
            return {"next": "done"}
        doc.page_texts = result.page_texts
        if result.pages_needing_vision:
            return {"next": "vision", "pages": result.pages_needing_vision}
        doc.status = DocStatus.read
        return {"next": "classify"}


def transcribe_step(doc_id: str, page_index: int) -> None:
    from app.agents.vision import transcribe_page

    with session_scope() as s:
        doc = s.get(Document, doc_id)
        data = get_storage().get(doc.storage_path)
        file_hash, filename = doc.file_hash or doc.id, doc.filename
        ctx = ctx_for_document(doc, "vision")
    png = render_page_png(filename, data, page_index)
    text = transcribe_page(png, file_hash=file_hash, page_index=page_index, ctx=ctx)
    with session_scope() as s:
        # Row lock so concurrent page tasks for the same document don't overwrite each other.
        doc = s.scalars(select(Document).where(Document.id == doc_id).with_for_update()).one()
        pages = list(doc.page_texts or [])
        pages[page_index] = text
        doc.page_texts = pages


def mark_read(doc_id: str) -> None:
    with session_scope() as s:
        s.execute(update(Document).where(Document.id == doc_id, Document.status == DocStatus.reading)
                  .values(status=DocStatus.read))


# ============================================================================ step 2: classify and split
def classify_step(doc_id: str) -> list[str]:
    """Returns ids of documents ready for extraction (the doc itself or its split parts)."""
    from app.agents.agents import classify

    if not claim_document(doc_id, {DocStatus.read}, DocStatus.classifying):
        return []
    with session_scope() as s:
        doc = s.get(Document, doc_id)
        pages, filename, ctx = list(doc.page_texts or []), doc.filename, ctx_for_document(doc, "classifier")

    key = _cache_key("classify", doc_id_hash(doc_id), "\n".join(pages))
    cached = _cache_get(key)
    if cached is None:
        classification = classify(pages, filename, ctx)
        segments = [seg.model_dump(mode="json") for seg in classification.segments]
        _cache_put(key, {"segments": segments, "flags": ctx.flags})
    else:
        segments = cached["segments"]
        ctx.flags.extend(cached.get("flags", []))

    with session_scope() as s:
        doc = s.get(Document, doc_id)
        doc.flags = sorted(set((doc.flags or []) + ctx.flags))
        useful = [seg for seg in segments if seg["doc_type"] != DocType.other.value]
        if len(segments) == 1:
            doc.doc_type = segments[0]["doc_type"]
            if doc.doc_type == DocType.other.value:
                doc.status = DocStatus.extracted  # nothing to extract (cover letter etc.)
                return []
            doc.status = DocStatus.ready
            doc.claimed_at = None
            return [doc.id]
        children = []
        for seg in useful:
            child_id = hashlib.sha256(f"{doc.id}:{seg['start_page']}".encode()).hexdigest()[:32]
            child_id = f"{child_id[:8]}-{child_id[8:12]}-{child_id[12:16]}-{child_id[16:20]}-{child_id[20:32]}"
            if s.get(Document, child_id) is None:  # deterministic ids: re-running never duplicates parts
                s.add(Document(
                    id=child_id, batch_id=doc.batch_id, parent_id=doc.id, file_hash=None,
                    filename=f"{doc.filename} [p{seg['start_page']}-{seg['end_page']}]",
                    storage_path=doc.storage_path, source_format=doc.source_format,
                    page_start=seg["start_page"], page_end=seg["end_page"],
                    page_texts=pages[seg["start_page"] - 1: seg["end_page"]], doc_type=seg["doc_type"],
                    status=DocStatus.ready, flags=list(doc.flags or []), trace_id=doc.trace_id))
            children.append(child_id)
        doc.status = DocStatus.split
        return children


def doc_id_hash(doc_id: str) -> str:
    with session_scope() as s:
        d = s.get(Document, doc_id)
        return d.file_hash or f"{d.parent_id}:{d.page_start}"


# ============================================================================ step 3: extract + validate
def extract_step(doc_id: str) -> None:
    from app.agents.agents import extract

    if not claim_document(doc_id, {DocStatus.ready}, DocStatus.extracting):
        return
    with session_scope() as s:
        doc = s.get(Document, doc_id)
        if s.scalars(select(Extraction).where(Extraction.document_id == doc_id,
                                              Extraction.prompt_version == settings.prompt_version)).first():
            doc.status = DocStatus.extracted  # already done by an earlier attempt
            return
        doc_type, filename = doc.doc_type, doc.filename
        text = "\n\n".join(f"=== PAGE {i + 1} ===\n{t}" for i, t in enumerate(doc.page_texts or []))
        ctx = ctx_for_document(doc, f"extractor_{doc_type}")
        content_id = doc.file_hash or f"{doc.parent_id}:{doc.page_start}"

    escalated = False
    key = _cache_key("extract", content_id, doc_type + "|small")
    cached = _cache_get(key)
    if cached:
        data, confidence, model = cached["data"], cached["confidence"], cached["model"]
        ctx.flags.extend(cached.get("flags", []))
    else:
        data, confidence, model = extract(doc_type, text, filename, ctx, tier="small")
        _cache_put(key, {"data": data, "confidence": confidence, "model": model, "flags": ctx.flags})
    issues = validate(doc_type, data)

    if issues:  # escalate once to a stronger model, telling it what failed
        key2 = _cache_key("extract", content_id, doc_type + "|strong")
        cached2 = _cache_get(key2)
        if cached2:
            data2, conf2, model2 = cached2["data"], cached2["confidence"], cached2["model"]
        else:
            data2, conf2, model2 = extract(doc_type, text, filename, ctx, tier="strong", feedback=issues)
            _cache_put(key2, {"data": data2, "confidence": conf2, "model": model2, "flags": ctx.flags})
        issues2 = validate(doc_type, data2)
        escalated = True
        if len(issues2) <= len(issues):
            data, confidence, model, issues = data2, conf2, model2, issues2
    if issues:
        # Still failing: keep the reading but make sure a person looks at it.
        confidence = min(confidence, settings.confidence_threshold - 0.01)
        ctx.flag("validation_failed", ", ".join(issues))

    with session_scope() as s:
        doc = s.get(Document, doc_id)
        doc.flags = sorted(set((doc.flags or []) + ctx.flags))
        _save_extraction(s, doc, doc_type, data, confidence, model, escalated, issues)
        doc.status = DocStatus.extracted
    metrics.docs_processed.add(1, {"outcome": "extracted", "doc_type": doc_type})


def _save_extraction(s: Session, doc: Document, doc_type: str, data: dict, confidence: float, model: str,
                     escalated: bool, issues: list[str] | None = None) -> None:
    existing = s.scalars(select(Extraction).where(Extraction.document_id == doc.id,
                                                  Extraction.prompt_version == settings.prompt_version)).first()
    row = existing or Extraction(document_id=doc.id, prompt_version=settings.prompt_version)
    row.doc_type, row.data, row.confidence, row.model = doc_type, data, confidence, model
    row.escalated, row.validation_issues = escalated, issues or []
    s.add(row)


def _cache_key(kind: str, content_id: str, extra: str) -> str:
    raw = f"{kind}|{content_id}|{extra}|{settings.prompt_version}|{settings.schema_version}|{settings.llm_provider}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _cache_get(key: str) -> dict | None:
    with session_scope() as s:
        row = s.get(LLMCache, key)
        if row is not None:
            metrics.cache_hits.add(1, {"kind": "pipeline"})
            return row.value
    return None


def _cache_put(key: str, value: dict) -> None:
    with session_scope() as s:
        s.merge(LLMCache(key=key, value=value))


# ============================================================================ batch completion
def try_finish_batch(batch_id: str) -> bool:
    """True exactly once per batch: when its last document reaches a terminal state."""
    terminal = [s.value for s in TERMINAL_DOC_STATES]
    with session_scope() as s:
        pending = select(Document.id).where(Document.batch_id == batch_id,
                                            Document.status.not_in(terminal)).exists()
        res = s.execute(update(Batch).where(Batch.id == batch_id, Batch.status == "processing", ~pending)
                        .values(status="grouping").returning(Batch.id)).first()
        return res is not None


# ============================================================================ step 4: group into packs
def group_step(batch_id: str) -> list[str]:
    """Union documents that share strong identifiers into shipment packs. Attaches to an
    existing open pack (e.g. papers that arrived in an earlier batch) when keys match."""
    with session_scope() as s:
        batch = s.get(Batch, batch_id)
        rows = s.execute(
            select(Document, Extraction).join(Extraction, Extraction.document_id == Document.id)
            .where(Document.batch_id == batch_id, Document.status == DocStatus.extracted,
                   Document.id.not_in(select(PackDocument.document_id)))
        ).all()
        _mark_exact_duplicates(s, rows)

        uf = UnionFind()
        keys_of: dict[str, tuple[set[str], set[str]]] = {}
        for doc, ext in rows:
            strong, weak = doc_keys(ext.doc_type, ext.data)
            keys_of[doc.id] = (strong, weak)
            uf.find(f"doc:{doc.id}")
            for k in strong:
                uf.union(f"doc:{doc.id}", f"key:{k}")
        groups: dict[str, list[tuple[Document, Extraction]]] = {}
        for doc, ext in rows:
            groups.setdefault(uf.find(f"doc:{doc.id}"), []).append((doc, ext))

        open_packs = s.scalars(select(ShipmentPack).where(
            ShipmentPack.status.in_([PackStatus.open, PackStatus.waiting_for_invoice]))).all()
        touched: list[str] = []
        for members in groups.values():
            strong_all = set().union(*(keys_of[d.id][0] for d, _ in members))
            weak_all = set().union(*(keys_of[d.id][1] for d, _ in members))
            has_anchor = any(e.doc_type in ("invoice", "packing_list", "eway_bill") for _, e in members)
            if not strong_all and not has_anchor:
                continue  # orphan: stays unlinked; the reconciler agent may link it later
            pack = next((p for p in open_packs if strong_all & set(p.keys or [])), None)
            if pack is None:
                pack = ShipmentPack(batch_id=batch_id, priority=batch.priority, keys=[])
                s.add(pack)
                s.flush()
                open_packs.append(pack)
            pack.keys = sorted(set(pack.keys or []) | strong_all | weak_all)
            for doc, ext in members:
                s.add(PackDocument(pack_id=pack.id, document_id=doc.id, linked_by="key"))
                if ext.doc_type == "invoice" or (not pack.po_number and ext.data.get("po_number")):
                    pack.po_number = norm_po(ext.data.get("po_number", "")) or pack.po_number
                if ext.doc_type in ("invoice", "eway_bill") and ext.data.get("supplier_gstin"):
                    pack.supplier_gstin = ext.data["supplier_gstin"].upper()
            pack.status = PackStatus.open
            touched.append(pack.id)
        batch.status, batch.grouped_at = "grouped", now()
        return sorted(set(touched))


def is_earlier(a: Document, b: Document) -> bool:
    """Documents uploaded in one request share a timestamp; the id breaks the tie."""
    return (a.created_at, a.id) < (b.created_at, b.id)


def _mark_exact_duplicates(s: Session, rows) -> None:
    """Same supplier + same invoice number: the later document is marked as a duplicate
    of the earliest one, and is excluded from matching and export."""
    for doc, ext in rows:
        if ext.doc_type != "invoice" or doc.duplicate_of:
            continue
        g = (ext.data.get("supplier_gstin") or "").upper()
        n = norm_invoice_no(ext.data.get("invoice_number", ""))
        others = s.execute(
            select(Document, Extraction.data).join(Extraction, Extraction.document_id == Document.id)
            .where(Extraction.doc_type == "invoice", Document.id != doc.id, Document.duplicate_of.is_(None))
        ).all()
        earlier = [o for o, data in others
                   if (data.get("supplier_gstin") or "").upper() == g
                   and norm_invoice_no(data.get("invoice_number", "")) == n and is_earlier(o, doc)]
        if earlier:
            doc.duplicate_of = min(earlier, key=lambda o: (o.created_at, o.id)).id


def link_documents(pack_id: str, document_ids: list[str]) -> list[str]:
    """Link documents the reconciler proposed - but only if they really share an
    identifier with the pack. The agent proposes; code verifies."""
    linked = []
    with session_scope() as s:
        pack = s.get(ShipmentPack, pack_id)
        keys = set(pack.keys or [])
        for did in document_ids:
            ext = s.scalars(select(Extraction).where(Extraction.document_id == did)).first()
            already = s.scalars(select(PackDocument).where(PackDocument.document_id == did)).first()
            if ext is None or already is not None:
                continue
            strong, weak = doc_keys(ext.doc_type, ext.data)
            if (strong | weak) & keys:
                s.add(PackDocument(pack_id=pack_id, document_id=did, linked_by="agent"))
                pack.keys = sorted(keys | strong | weak)
                linked.append(did)
    return linked


# ============================================================================ step 5: match and route
def process_pack_step(pack_id: str) -> str:
    """Run the match engine and decide the route. Returns the route taken."""
    from app.agents.agents import supervise

    if not claim_pack(pack_id, {PackStatus.open}, PackStatus.open):
        return "skip"
    with session_scope() as s:
        pack = s.get(ShipmentPack, pack_id)
        result = run_match(build_snapshot(s, pack))
        ctx = AgentContext(agent="supervisor", batch_id=pack.batch_id, pack_id=pack.id)
        _store_match(pack, result)
    route = result.route

    if route == "wait":
        _set_pack(pack_id, PackStatus.waiting_for_invoice, route="wait")
        return "wait"
    if route == "auto_approve" and not settings.supervisor_for_clean_packs:
        _set_pack(pack_id, PackStatus.auto_approved, finding="All papers agree with the order and the receipt.",
                  route="auto_approve")
        metrics.packs_routed.add(1, {"route": "auto_approve"})
        return "auto_approve"

    decision = supervise(ctx)
    with session_scope() as s:  # the reconciler may have linked papers: re-run the engine
        pack = s.get(ShipmentPack, pack_id)
        result = run_match(build_snapshot(s, pack))
        _store_match(pack, result)
        pack.flags = sorted(set((pack.flags or []) + ctx.flags))

    # Code has the last word: the agent can make a route stricter, never looser.
    final = result.route
    if "possible_injection" in ctx.flags or decision.route == "human_review":
        final = "human_review"
    elif final == "auto_approve" and decision.route != "auto_approve":
        final = "investigate"
    metrics.packs_routed.add(1, {"route": final})
    if final == "auto_approve":
        _set_pack(pack_id, PackStatus.auto_approved, finding=decision.summary, route=final)
    elif final == "wait":
        _set_pack(pack_id, PackStatus.waiting_for_invoice, route=final)
    elif final == "human_review":
        _set_pack(pack_id, PackStatus.needs_review, finding=_human_summary(result, decision.summary), route=final)
    else:
        _set_pack(pack_id, PackStatus.investigating, finding=decision.summary, route=final)
    return final


def _store_match(pack: ShipmentPack, result) -> None:
    pack.match_result = result.to_json()
    pack.issue_codes = result.issue_codes
    pack.invoice_total = result.invoice_total
    pack.payable_amount = result.payable_amount


def _human_summary(result, summary: str) -> str:
    reasons = "; ".join(i.message for i in result.issues if i.code in ("SUSPICIOUS_CONTENT", "LOW_CONFIDENCE"))
    return f"{reasons} {summary}".strip()


def _set_pack(pack_id: str, status: PackStatus, finding: str | None = None, route: str | None = None) -> None:
    with session_scope() as s:
        pack = s.get(ShipmentPack, pack_id)
        pack.status = status
        if route:
            pack.route = route
        pack.claimed_at = None
        if finding:
            pack.finding = finding


# ============================================================================ step 6: investigate (agent + human approval)
def thread_id_for(pack_id: str) -> str:
    return f"pack-{pack_id}"


def investigate_step(pack_id: str) -> str:
    from app.agents.agents import run_exception_agent

    if not claim_pack(pack_id, {PackStatus.investigating}, PackStatus.investigating):
        return "skip"
    with session_scope() as s:
        pack = s.get(ShipmentPack, pack_id)
        ctx = AgentContext(agent="exception_resolver", batch_id=pack.batch_id, pack_id=pack.id)
        thread_id = pack.agent_thread_id or thread_id_for(pack_id)
        pack.agent_thread_id = thread_id
    outcome = run_exception_agent(ctx, thread_id)
    return _handle_agent_outcome(pack_id, outcome, ctx)


def _handle_agent_outcome(pack_id: str, outcome: dict, ctx: AgentContext) -> str:
    with session_scope() as s:
        pack = s.get(ShipmentPack, pack_id)
        pack.flags = sorted(set((pack.flags or []) + ctx.flags))
        if "interrupt" in outcome:
            s.execute(update(PendingAction).where(PendingAction.pack_id == pack_id,
                                                  PendingAction.status == "pending").values(status="superseded"))
            for i, req in enumerate(outcome["interrupt"]):
                args = dict(req.get("args", {}))
                if req["name"] == "propose_fix":
                    pack.finding = args.get("finding") or pack.finding
                    pack.proposal = args
                    engine_pay = Decimal(str(pack.payable_amount or 0))
                    if abs(Decimal(str(args.get("pay_amount", 0))) - engine_pay) > Decimal("1"):
                        args["_warning"] = (f"Agent's pay amount differs from the match engine's "
                                            f"({engine_pay}). Edit before approving.")
                needs_manager = max(Decimal(str(pack.invoice_total or 0)),
                                    Decimal(str(args.get("pay_amount", 0) or 0))) > settings.manager_approval_threshold_inr
                s.add(PendingAction(pack_id=pack_id, position=i, tool_name=req["name"], args=args,
                                    description=req.get("description", ""),
                                    requires_role="finance_manager" if needs_manager else "ap_executive"))
            pack.status = PackStatus.awaiting_approval
            pack.claimed_at = None
            return "awaiting_approval"
        finding = outcome.get("finding")
        if pack.status in (PackStatus.approved, PackStatus.rejected):
            pack.claimed_at = None
            return pack.status.value  # propose_fix ran after approval and set the outcome
        pack.status = PackStatus.needs_review
        pack.claimed_at = None
        if finding is not None:
            pack.finding = f"{finding.finding} Recommended: {finding.recommended_action}"
        return "needs_review"


def record_decisions(pack_id: str, decisions: list[dict], actor: str, role: str) -> dict:
    """Validate a person's decisions on the pending actions and build the HITL resume
    payload. Raises PermissionError / ValueError on invalid input."""
    with session_scope() as s:
        pack = s.get(ShipmentPack, pack_id)
        if pack is None or pack.status != PackStatus.awaiting_approval:
            raise ValueError("This pack is not waiting for approval.")
        pending = s.scalars(select(PendingAction).where(PendingAction.pack_id == pack_id,
                                                        PendingAction.status == "pending")
                            .order_by(PendingAction.position)).all()
        by_id = {d["action_id"]: d for d in decisions}
        if set(by_id) != {p.id for p in pending}:
            raise ValueError("Every pending action needs exactly one decision.")
        hitl = []
        for p in pending:
            d = by_id[p.id]
            if d["type"] in ("approve", "edit") and p.requires_role == "finance_manager" and role != "finance_manager":
                raise PermissionError("Amounts above the approval limit need the finance manager.")
            if d["type"] == "approve":
                hitl.append({"type": "approve"})
                p.status = "approved"
            elif d["type"] == "edit":
                args = {k: v for k, v in (d.get("args") or p.args).items() if not k.startswith("_")}
                hitl.append({"type": "edit", "edited_action": {"name": p.tool_name, "args": args}})
                p.status, p.args = "edited", args
            elif d["type"] == "reject":
                hitl.append({"type": "reject", "message": d.get("message") or "Rejected by reviewer."})
                p.status = "rejected"
            else:
                raise ValueError(f"Unknown decision {d['type']}")
            p.decided_by, p.decided_at = actor, now()
            s.add(ReviewAction(pack_id=pack_id, actor=actor, role=role, action=f"{d['type']}:{p.tool_name}",
                               detail={"args": d.get("args"), "message": d.get("message")}))
        pack.status = PackStatus.investigating
        pack.claimed_at = None
        return {"decisions": hitl}


def resume_step(pack_id: str, resume: dict) -> str:
    from app.agents.agents import run_exception_agent

    if not claim_pack(pack_id, {PackStatus.investigating}, PackStatus.investigating):
        return "skip"
    with session_scope() as s:
        pack = s.get(ShipmentPack, pack_id)
        ctx = AgentContext(agent="exception_resolver", batch_id=pack.batch_id, pack_id=pack.id)
        thread_id = pack.agent_thread_id
    outcome = run_exception_agent(ctx, thread_id, resume=resume)
    return _handle_agent_outcome(pack_id, outcome, ctx)


def manual_decision(pack_id: str, decision: str, actor: str, role: str, comment: str = "") -> None:
    """For packs in needs_review (no agent proposal): a person approves or rejects directly."""
    with session_scope() as s:
        pack = s.get(ShipmentPack, pack_id)
        if pack.status not in (PackStatus.needs_review, PackStatus.awaiting_approval, PackStatus.waiting_for_invoice):
            raise ValueError(f"Pack is {pack.status.value}; nothing to decide.")
        if decision == "approve" and Decimal(str(pack.invoice_total or 0)) > settings.manager_approval_threshold_inr \
                and role != "finance_manager":
            raise PermissionError("Amounts above the approval limit need the finance manager.")
        pack.status = PackStatus.approved if decision == "approve" else PackStatus.rejected
        s.execute(update(PendingAction).where(PendingAction.pack_id == pack_id, PendingAction.status == "pending")
                  .values(status="superseded"))
        s.add(ReviewAction(pack_id=pack_id, actor=actor, role=role, action=f"manual_{decision}",
                           detail={"comment": comment}))


# ============================================================================ export (code only, never an agent)
def export_approved(actor: str) -> tuple[str, list[dict]]:
    """Export approved invoices for payment. Each invoice can only ever be exported once
    (unique invoice key), so re-running the export is harmless."""
    import uuid

    from app.db.models import ExportRecord
    from app.services.packs import pack_documents

    export_id = str(uuid.uuid4())
    rows: list[dict] = []
    with session_scope() as s:
        packs = s.scalars(select(ShipmentPack).where(
            ShipmentPack.status.in_([PackStatus.approved, PackStatus.auto_approved]))).all()
        for pack in packs:
            exported_any = False
            for doc, ext in pack_documents(s, pack.id):
                if ext is None or ext.doc_type != "invoice" or doc.duplicate_of:
                    continue
                key = f"{(ext.data.get('supplier_gstin') or '').upper()}:{norm_invoice_no(ext.data.get('invoice_number', ''))}"
                if s.scalars(select(ExportRecord).where(ExportRecord.invoice_key == key)).first():
                    continue
                amount = pack.payable_amount if pack.payable_amount is not None else Decimal(str(ext.data.get("total", 0)))
                s.add(ExportRecord(invoice_key=key, pack_id=pack.id, export_id=export_id, amount=amount,
                                   exported_by=actor))
                rows.append({"supplier_gstin": ext.data.get("supplier_gstin"), "invoice_number": ext.data.get("invoice_number"),
                             "invoice_date": ext.data.get("invoice_date"), "po_number": pack.po_number,
                             "invoice_total": ext.data.get("total"), "pay_amount": str(amount),
                             "debit_note": (pack.proposal or {}).get("debit_note_amount", 0), "pack_id": pack.id})
                exported_any = True
            if exported_any:
                pack.status = PackStatus.exported
                s.add(ReviewAction(pack_id=pack.id, actor=actor, role="system", action="export",
                                   detail={"export_id": export_id}))
    return export_id, rows


# ============================================================================ housekeeping
def reap_stale() -> dict[str, list[str]]:
    """Find work whose claim expired (worker died mid-task), reset it to the state
    before that step and return what to re-enqueue. Cached AI answers make re-runs free."""
    stale = now() - timedelta(seconds=settings.claim_lease_seconds)
    out: dict[str, list[str]] = {"read": [], "classify": [], "extract": [], "process": [], "investigate": [],
                                 "finish": []}
    back = {DocStatus.reading: (DocStatus.queued, "read"), DocStatus.classifying: (DocStatus.read, "classify"),
            DocStatus.extracting: (DocStatus.ready, "extract")}
    with session_scope() as s:
        for status, (reset_to, stage) in back.items():
            ids = s.scalars(select(Document.id).where(Document.status == status, Document.claimed_at < stale)).all()
            if ids:
                s.execute(update(Document).where(Document.id.in_(ids)).values(status=reset_to, claimed_at=None))
            out[stage] += list(ids)
        # Work that was never picked up at all (e.g. the broker lost a message).
        out["read"] += s.scalars(select(Document.id).where(Document.status == DocStatus.queued,
                                                           Document.updated_at < stale)).all()
        out["classify"] += s.scalars(select(Document.id).where(Document.status == DocStatus.read,
                                                               Document.updated_at < stale)).all()
        out["extract"] += s.scalars(select(Document.id).where(Document.status == DocStatus.ready,
                                                              Document.updated_at < stale)).all()
        out["process"] = list(s.scalars(select(ShipmentPack.id).where(
            ShipmentPack.status == PackStatus.open, ShipmentPack.updated_at < stale)).all())
        waiting = select(PendingAction.pack_id).where(PendingAction.status == "pending")
        out["investigate"] = list(s.scalars(select(ShipmentPack.id).where(
            ShipmentPack.status == PackStatus.investigating, ShipmentPack.updated_at < stale,
            ShipmentPack.id.not_in(waiting))).all())
        out["finish"] = list(s.scalars(select(Batch.id).where(Batch.status == "processing",
                                                               Batch.created_at < stale)).all())
    return out


def batch_progress(session: Session, batch_id: str) -> dict:
    by_status = dict(session.execute(select(Document.status, func.count()).where(Document.batch_id == batch_id)
                                     .group_by(Document.status)).all())
    by_type = dict(session.execute(select(Document.doc_type, func.count()).where(
        Document.batch_id == batch_id, Document.status == DocStatus.extracted).group_by(Document.doc_type)).all())
    packs = dict(session.execute(select(ShipmentPack.status, func.count()).where(ShipmentPack.batch_id == batch_id)
                                 .group_by(ShipmentPack.status)).all())
    return {"documents": {k.value: v for k, v in by_status.items()},
            "by_type": {str(k): v for k, v in by_type.items()},
            "packs": {k.value: v for k, v in packs.items()}}


def priority_of_doc(doc_id: str) -> Priority:
    with session_scope() as s:
        doc = s.get(Document, doc_id)
        return s.get(Batch, doc.batch_id).priority


def priority_of_pack(pack_id: str) -> Priority:
    with session_scope() as s:
        return s.get(ShipmentPack, pack_id).priority


__all__ = ["Fmt"]
