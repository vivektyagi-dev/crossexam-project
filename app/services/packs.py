"""Loading shipment packs into the plain snapshot the match engine understands."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import (
    Document,
    Extraction,
    GoodsReceipt,
    PackDocument,
    Product,
    PurchaseOrder,
    ShipmentPack,
    Supplier,
)
from app.rules.dedupe import find_invoice_duplicates
from app.rules.match_engine import GRNSnapshot, PackSnapshot, POSnapshot
from app.rules.normalize import norm_po


def latest_extraction(session: Session, document_id: str) -> Extraction | None:
    return session.scalars(
        select(Extraction).where(Extraction.document_id == document_id).order_by(Extraction.id.desc())
    ).first()


def pack_documents(session: Session, pack_id: str) -> list[tuple[Document, Extraction | None]]:
    docs = session.scalars(
        select(Document).join(PackDocument, PackDocument.document_id == Document.id)
        .where(PackDocument.pack_id == pack_id).order_by(Document.created_at)
    ).all()
    return [(d, latest_extraction(session, d.id)) for d in docs]


def load_po(session: Session, po_number: str | None) -> PurchaseOrder | None:
    if not po_number:
        return None
    return session.scalars(select(PurchaseOrder).where(PurchaseOrder.po_number == norm_po(po_number))).first()


def build_snapshot(session: Session, pack: ShipmentPack) -> PackSnapshot:
    rows = pack_documents(session, pack.id)
    documents = []
    dup_hits: list[dict] = []
    for doc, ext in rows:
        if ext is None:
            continue
        documents.append({"id": doc.id, "doc_type": ext.doc_type, "data": ext.data, "flags": doc.flags or [],
                          "confidence": ext.confidence, "uncertain_fields": ext.data.get("uncertain_fields", []),
                          "duplicate_of": doc.duplicate_of, "filename": doc.filename})
        if ext.doc_type == "invoice":
            hits = find_invoice_duplicates(session, doc.id, ext.data, settings.duplicate_date_window_days)
            for h in hits:
                other = session.get(Document, h["other_document_id"])
                # Report each pair once: the later document is the suspected duplicate.
                if other is not None and (other.created_at, other.id) < (doc.created_at, doc.id):
                    dup_hits.append({**h, "document_id": doc.id})

    po = load_po(session, pack.po_number)
    po_snap = None
    grns: list[GRNSnapshot] = []
    supplier = None
    if po is not None:
        supplier = session.get(Supplier, po.supplier_id)
        po_snap = POSnapshot(
            po_number=po.po_number, supplier_gstin=supplier.gstin,
            lines={line.sku.upper(): {"qty": line.qty_cartons, "price": line.price_per_carton} for line in po.lines})
        for g in session.scalars(select(GoodsReceipt).where(GoodsReceipt.po_id == po.id)).all():
            grns.append(GRNSnapshot(g.grn_number, g.received_date, g.vehicle_no,
                                    {gl.sku.upper(): {"qty": gl.qty_cartons, "batch": gl.batch_no} for gl in g.lines}))
    products = {p.sku.upper(): {"gst_rate": p.gst_rate, "requires_coa": p.requires_coa, "hsn": p.hsn}
                for p in session.scalars(select(Product)).all()}
    price_tol = (supplier.price_tolerance_pct if supplier and supplier.price_tolerance_pct is not None
                 else settings.default_price_tolerance_pct)
    qty_tol = (supplier.qty_tolerance_pct if supplier and supplier.qty_tolerance_pct is not None
               else settings.default_qty_tolerance_pct)
    return PackSnapshot(
        documents=documents, po=po_snap, grns=grns, products=products,
        price_tolerance_pct=Decimal(price_tol), qty_tolerance_pct=Decimal(qty_tol),
        eway_value_tolerance_pct=settings.eway_value_tolerance_pct,
        min_shelf_life_days=settings.min_shelf_life_days, confidence_threshold=settings.confidence_threshold,
        duplicate_hits=dup_hits,
    )
