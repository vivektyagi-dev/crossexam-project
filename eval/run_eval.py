"""Measure the system against the generator's ground truth.

    python -m eval.run_eval --truth data/generated/ground_truth.json --batch <batch_id>

Reports: field accuracy per document type and per format, classification accuracy,
problem detection (recall per planted problem, false alarms on clean shipments),
automation rate, AI cost per document and batch wall-clock time. Writes a markdown
report and records the numbers in the eval_runs table.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import func, select

from app.db.models import Batch, Document, EvalRun, Extraction, LLMCall, ShipmentPack
from app.db.session import session_scope
from app.rules.normalize import norm_invoice_no, norm_vehicle

KEY_FIELDS = {
    "invoice": ["supplier_gstin", "invoice_number", "invoice_date", "po_number", "subtotal", "tax_amount", "total",
                "gst_rate"],
    "packing_list": ["packing_list_number", "invoice_number", "total_cartons"],
    "lorry_receipt": ["lr_number", "vehicle_number", "invoice_number", "packages"],
    "eway_bill": ["eway_bill_number", "supplier_gstin", "invoice_number", "total_value"],
    "quality_certificate": ["certificate_number", "batch_number", "expiry_date", "result"],
}


def _same(field: str, a, b) -> bool:
    if a is None or b is None:
        return False
    if isinstance(b, int | float) or field in ("subtotal", "tax_amount", "total", "total_value", "packages",
                                                "total_cartons", "gst_rate"):
        try:
            return abs(Decimal(str(a)) - Decimal(str(b))) <= Decimal("0.5")
        except Exception:
            return False
    if field == "invoice_number":
        return norm_invoice_no(str(a)) == norm_invoice_no(str(b))
    if field == "vehicle_number":
        return norm_vehicle(str(a)) == norm_vehicle(str(b))
    return re.sub(r"\s", "", str(a)).upper() == re.sub(r"\s", "", str(b)).upper()


def evaluate(truth_path: str, batch_id: str | None) -> dict:
    truth = json.loads(open(truth_path).read())
    by_file = {f["file"]: f for f in truth["files"]}
    field_hits: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    format_hits: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    class_hits = [0, 0]
    with session_scope() as s:
        if batch_id is None:
            batch_id = s.scalars(select(Batch.id).order_by(Batch.created_at.desc())).first()
        batch = s.get(Batch, batch_id)
        rows = s.execute(select(Document, Extraction).join(Extraction, Extraction.document_id == Document.id)
                         .where(Document.batch_id == batch_id)).all()
        for doc, ext in rows:
            name, page = doc.filename, 1
            m = re.match(r"(.+) \[p(\d+)-(\d+)\]$", name)
            if m:
                name, page = m.group(1), int(m.group(2))
            entry = by_file.get(name)
            if not entry:
                continue
            seg = next((sg for sg in entry["segments"] if sg["pages"][0] == page), entry["segments"][0])
            class_hits[1] += 1
            class_hits[0] += int(seg["doc_type"] == ext.doc_type)
            for field in KEY_FIELDS.get(seg["doc_type"], []):
                ok = _same(field, ext.data.get(field), seg["fields"].get(field))
                field_hits[seg["doc_type"]][0] += int(ok)
                field_hits[seg["doc_type"]][1] += 1
                format_hits[entry["format"]][0] += int(ok)
                format_hits[entry["format"]][1] += 1

        packs = {p.po_number: p for p in s.scalars(select(ShipmentPack).where(ShipmentPack.batch_id == batch_id))}
        recall: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        false_alarms, clean = 0, 0
        for sh in truth["shipments"]:
            pack = packs.get(sh["po_number"])
            found = set(pack.issue_codes or []) if pack else set()
            for problem in sh["problems"]:
                from datagen.generate import EXPECTED_CODES

                recall[problem][1] += 1
                recall[problem][0] += int(EXPECTED_CODES[problem] <= found)
            if not sh["problems"]:
                clean += 1
                false_alarms += int(pack is None or pack.route != "auto_approve")
        routes = dict(s.execute(select(ShipmentPack.route, func.count()).where(ShipmentPack.batch_id == batch_id)
                                .group_by(ShipmentPack.route)).all())
        cost = s.scalar(select(func.coalesce(func.sum(LLMCall.cost_usd), 0)).where(LLMCall.batch_id == batch_id))
        n_docs = len(rows)
        seconds = (batch.grouped_at - batch.created_at).total_seconds() if batch.grouped_at else None
        decided = sum(v for k, v in routes.items() if k and k != "wait")
        result = {
            "batch_id": batch_id,
            "documents": n_docs,
            "classification_accuracy": round(class_hits[0] / class_hits[1], 4) if class_hits[1] else None,
            "field_accuracy_by_type": {k: round(v[0] / v[1], 4) for k, v in field_hits.items()},
            "field_accuracy_by_format": {k: round(v[0] / v[1], 4) for k, v in format_hits.items()},
            "problem_recall": {k: f"{v[0]}/{v[1]}" for k, v in recall.items()},
            "false_alarms_on_clean_shipments": f"{false_alarms}/{clean}",
            "automation_rate": round(routes.get("auto_approve", 0) / decided, 4) if decided else None,
            "ai_cost_usd": str(Decimal(cost).quantize(Decimal("0.0001"))),
            "ai_cost_per_document_usd": str((Decimal(cost) / n_docs).quantize(Decimal("0.000001"))) if n_docs else None,
            "seconds_to_group_batch": seconds,
        }
        s.add(EvalRun(name="ground_truth_eval", metrics=result))
    return result


def to_markdown(r: dict) -> str:
    lines = ["# Evaluation report", "", f"Batch `{r['batch_id']}` - {r['documents']} documents", ""]
    lines += ["| Metric | Value |", "|---|---|"]
    for k in ("classification_accuracy", "automation_rate", "false_alarms_on_clean_shipments", "ai_cost_usd",
              "ai_cost_per_document_usd", "seconds_to_group_batch"):
        lines.append(f"| {k.replace('_', ' ')} | {r[k]} |")
    for title, key in (("Field accuracy by document type", "field_accuracy_by_type"),
                       ("Field accuracy by format", "field_accuracy_by_format"),
                       ("Planted problems caught", "problem_recall")):
        lines += ["", f"## {title}", "", "| | |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in sorted(r[key].items())]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--truth", default="data/generated/ground_truth.json")
    ap.add_argument("--batch", default=None, help="batch id (default: latest)")
    ap.add_argument("--out", default="eval_report.md")
    args = ap.parse_args()
    report = evaluate(args.truth, args.batch)
    md = to_markdown(report)
    open(args.out, "w").write(md)
    print(md)
