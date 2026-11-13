"""Database models.

Master data (suppliers, products, POs, GRNs) mirrors what an ERP would hold.
Pipeline tables record every document, extraction, pack, decision and AI call,
so any outcome can be explained after the fact.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config import settings

JSONType = JSON().with_variant(JSONB(), "postgresql")

if settings.enable_pgvector:
    from pgvector.sqlalchemy import Vector

    EmbeddingType: Any = Vector(settings.embedding_dim)
else:  # pragma: no cover - fallback when the extension is unavailable
    EmbeddingType = JSONType


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


# ----------------------------------------------------------------------------
# Enums
# ----------------------------------------------------------------------------
class DocStatus(enum.StrEnum):
    queued = "queued"
    reading = "reading"
    read = "read"
    classifying = "classifying"
    split = "split"  # parent of split children; terminal for the parent itself
    ready = "ready"  # classified, waiting for extraction
    extracting = "extracting"
    extracted = "extracted"
    duplicate_file = "duplicate_file"
    failed = "failed"


TERMINAL_DOC_STATES = {DocStatus.extracted, DocStatus.split, DocStatus.duplicate_file, DocStatus.failed}


class PackStatus(enum.StrEnum):
    open = "open"
    waiting_for_invoice = "waiting_for_invoice"
    auto_approved = "auto_approved"
    investigating = "investigating"
    awaiting_approval = "awaiting_approval"
    needs_review = "needs_review"  # human decides without an agent proposal
    approved = "approved"
    rejected = "rejected"
    exported = "exported"
    failed = "failed"


class Priority(enum.StrEnum):
    urgent = "urgent"
    normal = "normal"
    bulk = "bulk"


# ----------------------------------------------------------------------------
# Master data
# ----------------------------------------------------------------------------
class Supplier(Base):
    __tablename__ = "suppliers"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    gstin: Mapped[str] = mapped_column(String(15), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(200), default="")
    state_code: Mapped[str] = mapped_column(String(2), default="")
    price_tolerance_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    qty_tolerance_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    uses_einvoice: Mapped[bool] = mapped_column(Boolean, default=False)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    hsn: Mapped[str] = mapped_column(String(8))
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    units_per_carton: Mapped[int] = mapped_column(Integer)
    carton_weight_kg: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    requires_coa: Mapped[bool] = mapped_column(Boolean, default=False)


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    po_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    order_date: Mapped[date] = mapped_column(Date)
    supplier: Mapped[Supplier] = relationship()
    lines: Mapped[list[POLine]] = relationship(back_populates="po", cascade="all, delete-orphan")


class POLine(Base):
    __tablename__ = "po_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"))
    sku: Mapped[str] = mapped_column(String(32))
    qty_cartons: Mapped[int] = mapped_column(Integer)
    price_per_carton: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    po: Mapped[PurchaseOrder] = relationship(back_populates="lines")


class GoodsReceipt(Base):
    __tablename__ = "goods_receipts"
    id: Mapped[int] = mapped_column(primary_key=True)
    grn_number: Mapped[str] = mapped_column(String(32), unique=True)
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    received_date: Mapped[date] = mapped_column(Date)
    vehicle_no: Mapped[str] = mapped_column(String(20), default="")
    lines: Mapped[list[GRNLine]] = relationship(back_populates="grn", cascade="all, delete-orphan")
    po: Mapped[PurchaseOrder] = relationship()


class GRNLine(Base):
    __tablename__ = "grn_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    grn_id: Mapped[int] = mapped_column(ForeignKey("goods_receipts.id"))
    sku: Mapped[str] = mapped_column(String(32))
    qty_cartons: Mapped[int] = mapped_column(Integer)
    batch_no: Mapped[str] = mapped_column(String(32), default="")
    grn: Mapped[GoodsReceipt] = relationship(back_populates="lines")


# ----------------------------------------------------------------------------
# Pipeline
# ----------------------------------------------------------------------------
class Batch(Base):
    __tablename__ = "batches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), default="")
    priority: Mapped[Priority] = mapped_column(Enum(Priority, name="priority"), default=Priority.normal)
    status: Mapped[str] = mapped_column(String(20), default="processing")  # processing|grouping|grouped
    created_by: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    grouped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), index=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"), nullable=True, index=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    filename: Mapped[str] = mapped_column(String(300))
    storage_path: Mapped[str] = mapped_column(String(500))
    source_format: Mapped[str] = mapped_column(String(20), default="unknown")
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_texts: Mapped[list[str] | None] = mapped_column(JSONType, nullable=True)
    doc_type: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    status: Mapped[DocStatus] = mapped_column(Enum(DocStatus, name="doc_status"), default=DocStatus.queued)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_of: Mapped[str | None] = mapped_column(String(36), nullable=True)
    flags: Mapped[list[str]] = mapped_column(JSONType, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # Layer 1 dedupe: one row per unique top-level file. Split children have NULL hashes.
        Index("uq_documents_file_hash", "file_hash", unique=True, postgresql_where=text("file_hash IS NOT NULL")),
    )


class Extraction(Base):
    __tablename__ = "extractions"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    doc_type: Mapped[str] = mapped_column(String(30))
    data: Mapped[dict] = mapped_column(JSONType)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    model: Mapped[str] = mapped_column(String(80), default="")
    prompt_version: Mapped[str] = mapped_column(String(20))
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_issues: Mapped[list] = mapped_column(JSONType, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("document_id", "prompt_version", name="uq_extraction_doc_prompt"),)


class LLMCache(Base):
    """AI answers keyed by content hash + model + prompt + schema: a retry never pays twice."""

    __tablename__ = "llm_cache"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ShipmentPack(Base):
    __tablename__ = "shipment_packs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), index=True)
    po_number: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    supplier_gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    keys: Mapped[list[str]] = mapped_column(JSONType, default=list)
    status: Mapped[PackStatus] = mapped_column(Enum(PackStatus, name="pack_status"), default=PackStatus.open)
    route: Mapped[str | None] = mapped_column(String(20), nullable=True)  # auto_approve|investigate|human_review|wait
    priority: Mapped[Priority] = mapped_column(Enum(Priority, name="priority"), default=Priority.normal)
    match_result: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    issue_codes: Mapped[list[str]] = mapped_column(JSONType, default=list)
    invoice_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    payable_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    finding: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposal: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    agent_thread_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    flags: Mapped[list[str]] = mapped_column(JSONType, default=list)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    documents: Mapped[list[PackDocument]] = relationship(back_populates="pack", cascade="all, delete-orphan")


class PackDocument(Base):
    __tablename__ = "pack_documents"
    pack_id: Mapped[str] = mapped_column(ForeignKey("shipment_packs.id"), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), primary_key=True, unique=True)
    linked_by: Mapped[str] = mapped_column(String(40), default="key")  # key | agent
    pack: Mapped[ShipmentPack] = relationship(back_populates="documents")


class PendingAction(Base):
    """A write action an agent wants to take, held by the human-approval middleware."""

    __tablename__ = "pending_actions"
    id: Mapped[int] = mapped_column(primary_key=True)
    pack_id: Mapped[str] = mapped_column(ForeignKey("shipment_packs.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)  # order inside the HITL request
    tool_name: Mapped[str] = mapped_column(String(60))
    args: Mapped[dict] = mapped_column(JSONType)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|approved|edited|rejected
    requires_role: Mapped[str] = mapped_column(String(30), default="ap_executive")
    decided_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReviewAction(Base):
    """Audit trail: every human action, who, when and why."""

    __tablename__ = "review_actions"
    id: Mapped[int] = mapped_column(primary_key=True)
    pack_id: Mapped[str] = mapped_column(ForeignKey("shipment_packs.id"), index=True)
    actor: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(30))
    action: Mapped[str] = mapped_column(String(40))
    detail: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Resolution(Base):
    """An approved fix. Also the memory behind the similar_cases tool."""

    __tablename__ = "resolutions"
    id: Mapped[int] = mapped_column(primary_key=True)
    pack_id: Mapped[str | None] = mapped_column(ForeignKey("shipment_packs.id"), nullable=True, unique=True)
    supplier_gstin: Mapped[str] = mapped_column(String(15), index=True)
    issue_codes: Mapped[list[str]] = mapped_column(JSONType, default=list)
    summary: Mapped[str] = mapped_column(Text)
    resolution: Mapped[str] = mapped_column(Text)
    pay_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    debit_note_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    embedding: Mapped[Any] = mapped_column(EmbeddingType, nullable=True)
    decided_by: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmailOutbox(Base):
    __tablename__ = "email_outbox"
    id: Mapped[int] = mapped_column(primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True)
    pack_id: Mapped[str] = mapped_column(ForeignKey("shipment_packs.id"), index=True)
    to_address: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    approved_by: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExportRecord(Base):
    """Layer 4 idempotency: an invoice can be exported to the ERP exactly once."""

    __tablename__ = "export_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_key: Mapped[str] = mapped_column(String(80), unique=True)  # gstin:normalised invoice no
    pack_id: Mapped[str] = mapped_column(ForeignKey("shipment_packs.id"))
    export_id: Mapped[str] = mapped_column(String(36), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    exported_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LLMCall(Base):
    """Cost ledger: one row per model call, written by CostLedgerMiddleware."""

    __tablename__ = "llm_calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    document_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    pack_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(80))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class EvalRun(Base):
    __tablename__ = "eval_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    metrics: Mapped[dict] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
