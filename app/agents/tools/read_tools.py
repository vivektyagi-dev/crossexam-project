"""Read-only tools. They only query; none of them can change data.

In production these run against a database role with SELECT-only grants
(see infra/terraform/sql.tf); locally they share the app connection.
"""

from __future__ import annotations

import json
from decimal import Decimal

from langchain.tools import ToolRuntime, tool
from sqlalchemy import func, select

from app.agents.context import AgentContext
from app.config import settings
from app.db.models import (
    Document,
    Extraction,
    GoodsReceipt,
    PackDocument,
    Product,
    PurchaseOrder,
    Resolution,
    ShipmentPack,
    Supplier,
)
from app.db.session import session_scope
from app.rules.dedupe import find_invoice_duplicates
from app.rules.match_engine import run_match
from app.rules.normalize import gstin_is_valid, norm_po
from app.schemas import DocType


def _j(obj) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False)


# ---------------------------------------------------------------- classifier tools
@tool
def page_text(page_number: int, runtime: ToolRuntime[AgentContext]) -> str:
    """Full text of one page (1-based) of the document being classified."""
    with session_scope() as s:
        doc = s.get(Document, runtime.context.document_id)
        pages = doc.page_texts or []
        if not 1 <= page_number <= len(pages):
            return f"Page {page_number} does not exist; the document has {len(pages)} pages."
        return pages[page_number - 1] or "(page is blank or unreadable)"


@tool
def page_image(page_number: int, runtime: ToolRuntime[AgentContext]) -> str:
    """Re-read one page (1-based) with the vision model. Use only when page_text looks
    garbled or empty, e.g. a stamp or handwriting covers key fields."""
    from app.agents.vision import transcribe_page
    from app.ingestion.readers import render_page_png
    from app.ingestion.storage import get_storage

    with session_scope() as s:
        doc = s.get(Document, runtime.context.document_id)
        root = s.get(Document, doc.parent_id) if doc.parent_id else doc
        offset = (doc.page_start or 1) - 1
        data = get_storage().get(root.storage_path)
        png = render_page_png(root.filename, data, offset + page_number - 1)
        return transcribe_page(png, file_hash=root.file_hash or root.id, page_index=offset + page_number - 1,
                               ctx=runtime.context)


@tool
def doc_type_catalog() -> str:
    """The document types this system handles and how to recognise each one."""
    return _j({
        DocType.invoice.value: "Title 'Tax Invoice'/'Invoice'; seller GSTIN, invoice no., line items with prices, GST, total.",
        DocType.packing_list.value: "Title 'Packing List'; cartons per item, batch numbers, weights; usually no prices.",
        DocType.lorry_receipt.value: "Transporter's 'Lorry Receipt', 'LR', 'Consignment Note' or 'Bill of Lading'; "
                                     "vehicle number, packages, consignor/consignee.",
        DocType.eway_bill.value: "'E-Way Bill'; 12-digit EWB number, GSTINs, HSN codes, vehicle, validity.",
        DocType.quality_certificate.value: "'Certificate of Analysis'/'Quality Certificate'; batch, test results, "
                                           "manufacture and expiry dates, PASS/FAIL.",
        DocType.credit_note.value: "'Credit Note'; reduces an earlier invoice; references the original invoice.",
        DocType.debit_note.value: "'Debit Note'; increases or disputes an earlier invoice.",
        DocType.other.value: "Anything else (cover letters, blank pages, advertisements).",
    })


# ---------------------------------------------------------------- extractor tools
@tool
def hsn_lookup(code: str) -> str:
    """Look up a product by SKU or HSN code: name, HSN, expected GST rate, units per carton."""
    with session_scope() as s:
        q = code.strip().upper()
        rows = s.scalars(select(Product).where((func.upper(Product.sku) == q) | (Product.hsn == q))).all()
        if not rows:
            return f"No product found for '{code}'."
        return _j([{"sku": p.sku, "name": p.name, "hsn": p.hsn, "gst_rate": p.gst_rate,
                    "units_per_carton": p.units_per_carton} for p in rows])


@tool
def gstin_check(gstin: str) -> str:
    """Validate a GSTIN's format and checksum, and look it up in the supplier master."""
    g = gstin.strip().upper()
    valid = gstin_is_valid(g)
    with session_scope() as s:
        sup = s.scalars(select(Supplier).where(Supplier.gstin == g)).first()
        return _j({"gstin": g, "format_and_checksum_valid": valid,
                   "known_supplier": sup.name if sup else None,
                   "hint": None if valid else "Check for misread characters (0/O, 1/I, 5/S, 8/B)."})


@tool
def unit_convert(quantity: float, from_unit: str, to_unit: str, sku: str) -> str:
    """Convert between units, cartons, cases and kg for a SKU (cartons and cases are the same)."""
    with session_scope() as s:
        p = s.scalars(select(Product).where(func.upper(Product.sku) == sku.strip().upper())).first()
        if not p:
            return f"Unknown SKU '{sku}'."
        per_carton = {"carton": 1, "case": 1, "unit": p.units_per_carton, "kg": float(p.carton_weight_kg)}
        f, t = from_unit.lower().rstrip("s"), to_unit.lower().rstrip("s")
        if f not in per_carton or t not in per_carton:
            return "Units must be one of: unit, carton, case, kg."
        cartons = quantity / float(per_carton[f])
        return _j({"quantity": round(cartons * float(per_carton[t]), 3), "unit": t})


# ---------------------------------------------------------------- reconciler tools
@tool
def find_related_docs(runtime: ToolRuntime[AgentContext]) -> str:
    """Documents NOT yet in any pack that may belong to the current pack because they share
    an identifier with it (invoice number, e-way bill, batch, vehicle). Candidates only:
    the vehicle alone is weak evidence, because one lorry carries many shipments."""
    from app.services.grouping import doc_keys

    with session_scope() as s:
        pack = s.get(ShipmentPack, runtime.context.pack_id)
        keys = set(pack.keys or [])
        linked = select(PackDocument.document_id)
        candidates = s.execute(
            select(Document, Extraction).join(Extraction, Extraction.document_id == Document.id)
            .where(Document.id.not_in(linked), Document.batch_id == pack.batch_id)
        ).all()
        out = []
        for doc, ext in candidates:
            strong, weak = doc_keys(ext.doc_type, ext.data)
            shared = sorted((strong | weak) & keys)
            if shared:
                out.append({"document_id": doc.id, "doc_type": ext.doc_type, "filename": doc.filename,
                            "shared_identifiers": shared,
                            "summary": {k: v for k, v in list(ext.data.items())[:8]}})
        return _j(out[:15]) if out else "No unlinked candidate documents."


@tool
def match_engine(runtime: ToolRuntime[AgentContext]) -> str:
    """Run the deterministic match engine on the current pack: quantities, prices, tax,
    e-way bill, vehicle, quality certificates and duplicates. Never recalculate yourself."""
    from app.services.packs import build_snapshot

    with session_scope() as s:
        pack = s.get(ShipmentPack, runtime.context.pack_id)
        result = run_match(build_snapshot(s, pack))
        return _j(result.to_json())


@tool
def tolerance_rules(supplier_gstin: str) -> str:
    """Agreed price and quantity tolerances for a supplier."""
    with session_scope() as s:
        sup = s.scalars(select(Supplier).where(Supplier.gstin == supplier_gstin.strip().upper())).first()
        return _j({
            "price_tolerance_pct": sup.price_tolerance_pct if sup and sup.price_tolerance_pct is not None
            else settings.default_price_tolerance_pct,
            "qty_tolerance_pct": sup.qty_tolerance_pct if sup and sup.qty_tolerance_pct is not None
            else settings.default_qty_tolerance_pct,
            "min_shelf_life_days": settings.min_shelf_life_days,
            "eway_value_tolerance_pct": settings.eway_value_tolerance_pct,
        })


# ---------------------------------------------------------------- exception tools
@tool
def po_grn_lookup(po_number: str) -> str:
    """Full purchase order and every goods receipt recorded against it."""
    with session_scope() as s:
        po = s.scalars(select(PurchaseOrder).where(PurchaseOrder.po_number == norm_po(po_number))).first()
        if not po:
            return f"No purchase order {po_number}."
        grns = s.scalars(select(GoodsReceipt).where(GoodsReceipt.po_id == po.id)).all()
        return _j({
            "po_number": po.po_number, "order_date": po.order_date, "supplier": po.supplier.name,
            "lines": [{"sku": line.sku, "qty_cartons": line.qty_cartons, "price_per_carton": line.price_per_carton}
                      for line in po.lines],
            "goods_receipts": [{"grn": g.grn_number, "received": g.received_date, "vehicle": g.vehicle_no,
                                "lines": [{"sku": gl.sku, "qty_cartons": gl.qty_cartons, "batch": gl.batch_no}
                                          for gl in g.lines]} for g in grns],
        })


@tool
def supplier_history(supplier_gstin: str) -> str:
    """A supplier's track record: past resolved exceptions, debit notes and pack outcomes."""
    with session_scope() as s:
        g = supplier_gstin.strip().upper()
        sup = s.scalars(select(Supplier).where(Supplier.gstin == g)).first()
        res = s.scalars(select(Resolution).where(Resolution.supplier_gstin == g)
                        .order_by(Resolution.created_at.desc()).limit(10)).all()
        outcomes = dict(s.execute(select(ShipmentPack.status, func.count()).where(ShipmentPack.supplier_gstin == g)
                                  .group_by(ShipmentPack.status)).all())
        return _j({
            "supplier": sup.name if sup else None, "email": sup.email if sup else None,
            "pack_outcomes": {k.value if hasattr(k, "value") else k: v for k, v in outcomes.items()},
            "past_exceptions": [{"id": r.id, "date": r.created_at.date(), "issues": r.issue_codes,
                                 "resolution": r.resolution, "debit_note": r.debit_note_amount} for r in res],
            "total_debit_notes": sum((r.debit_note_amount or Decimal("0") for r in res), Decimal("0")),
        })


@tool
def similar_cases(description: str, runtime: ToolRuntime[AgentContext]) -> str:
    """Search past RESOLVED exceptions similar to a description (semantic search when
    embeddings are available, otherwise same supplier and same issue codes)."""
    from app.agents.llm import embed_text

    with session_scope() as s:
        pack = s.get(ShipmentPack, runtime.context.pack_id) if runtime.context.pack_id else None
        vec = embed_text(description)
        if vec is not None:
            rows = s.scalars(select(Resolution).where(Resolution.embedding.isnot(None))
                             .order_by(Resolution.embedding.cosine_distance(vec)).limit(5)).all()
        else:
            q = select(Resolution).order_by(Resolution.created_at.desc()).limit(50)
            rows = s.scalars(q).all()
            codes = set(pack.issue_codes or []) if pack else set()

            def score(r):
                return (2 if pack and r.supplier_gstin == pack.supplier_gstin else 0) + len(codes & set(r.issue_codes))

            rows = [r for r in sorted(rows, key=score, reverse=True) if score(r) > 0][:5]
        if not rows:
            return "No similar past cases."
        return _j([{"case_id": r.id, "supplier_gstin": r.supplier_gstin, "issues": r.issue_codes,
                    "summary": r.summary, "resolution": r.resolution, "debit_note": r.debit_note_amount,
                    "date": r.created_at.date()} for r in rows])


@tool
def duplicate_search(supplier_gstin: str, invoice_number: str, total: float, invoice_date: str,
                     runtime: ToolRuntime[AgentContext]) -> str:
    """Invoices with the same supplier and number, or same amount within a few days."""
    with session_scope() as s:
        hits = find_invoice_duplicates(
            s, runtime.context.document_id or "-",
            {"supplier_gstin": supplier_gstin, "invoice_number": invoice_number, "total": total,
             "invoice_date": invoice_date},
            settings.duplicate_date_window_days)
        return _j(hits) if hits else "No duplicates found."


@tool
def pack_overview(runtime: ToolRuntime[AgentContext]) -> str:
    """Every document in the current pack with its extracted fields."""
    from app.services.packs import pack_documents

    with session_scope() as s:
        pack = s.get(ShipmentPack, runtime.context.pack_id)
        docs = [{"document_id": d.id, "filename": d.filename, "doc_type": e.doc_type if e else None,
                 "duplicate_of": d.duplicate_of, "flags": d.flags,
                 "fields": {k: v for k, v in (e.data if e else {}).items() if k not in ("uncertain_fields",)}}
                for d, e in pack_documents(s, pack.id)]
        return _j({"pack_id": pack.id, "po_number": pack.po_number, "supplier_gstin": pack.supplier_gstin,
                   "documents": docs})


CLASSIFIER_TOOLS = [page_text, page_image, doc_type_catalog]
EXTRACTOR_TOOLS = [hsn_lookup, gstin_check, unit_convert]
RECONCILER_TOOLS = [pack_overview, find_related_docs, match_engine, tolerance_rules]
EXCEPTION_READ_TOOLS = [pack_overview, match_engine, po_grn_lookup, supplier_history, similar_cases,
                        duplicate_search, tolerance_rules]
