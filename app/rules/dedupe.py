"""Layer 2 dedupe: the same bill arriving as different files (email PDF and a photo of
the paper copy). File hashes can't catch this; extracted fields can.

Hits are flagged for a person - never auto-rejected, because legitimate re-issues exist.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document, Extraction
from app.rules.normalize import dec, norm_invoice_no, parse_date


def find_invoice_duplicates(
    session: Session, document_id: str, data: dict, window_days: int = 7, prompt_version: str | None = None
) -> list[dict]:
    gstin = (data.get("supplier_gstin") or "").upper()
    if not gstin:
        return []
    number = norm_invoice_no(data.get("invoice_number", ""))
    total = dec(data.get("total", 0))
    inv_date = parse_date(data.get("invoice_date", ""))

    rows = session.execute(
        select(Extraction, Document)
        .join(Document, Document.id == Extraction.document_id)
        .where(Extraction.doc_type == "invoice", Extraction.document_id != document_id)
    ).all()
    hits = []
    for ext, doc in rows:
        other = ext.data
        if (other.get("supplier_gstin") or "").upper() != gstin:
            continue
        other_no = norm_invoice_no(other.get("invoice_number", ""))
        other_date = parse_date(other.get("invoice_date", ""))
        if other_no == number:
            hits.append({"kind": "exact", "other_document_id": doc.id, "other_filename": doc.filename,
                         "message": f"Same supplier and invoice number as {other.get('invoice_number')} "
                                    f"({doc.filename})."})
            continue
        other_total = dec(other.get("total", 0))
        close_total = total > 0 and abs(other_total - total) <= total * Decimal("0.005")
        close_date = inv_date and other_date and abs(other_date - inv_date) <= timedelta(days=window_days)
        if close_total and close_date:
            hits.append({"kind": "fuzzy", "other_document_id": doc.id, "other_filename": doc.filename,
                         "message": f"Same supplier and amount as {other.get('invoice_number')} "
                                    f"({doc.filename}), dated {abs((other_date - inv_date).days)} days apart."})
    return hits


def earliest_of(session: Session, ids: list[str]) -> str | None:
    """The first-seen document of a duplicate set is treated as the original."""
    docs = session.scalars(select(Document).where(Document.id.in_(ids)).order_by(Document.created_at)).all()
    return docs[0].id if docs else None
