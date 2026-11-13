"""Step 4: rule checks on a single extracted document. Exact, free, explainable.

A failure here usually means the AI misread something, so the pipeline retries the
extraction once with a stronger model before giving up and flagging a person.
"""

from __future__ import annotations

from decimal import Decimal

from app.rules.normalize import dec, gstin_is_valid, parse_date

ROUNDING = Decimal("1.00")  # allowed rounding difference in rupees


def validate(doc_type: str, data: dict) -> list[str]:
    fn = _VALIDATORS.get(doc_type)
    return fn(data) if fn else []


def _invoice(d: dict) -> list[str]:
    issues: list[str] = []
    for f in ("supplier_gstin", "invoice_number", "invoice_date", "total"):
        if not d.get(f):
            issues.append(f"missing:{f}")
    if d.get("supplier_gstin") and not gstin_is_valid(d["supplier_gstin"]):
        issues.append("invalid:supplier_gstin")
    if d.get("invoice_date") and not parse_date(d["invoice_date"]):
        issues.append("invalid:invoice_date")
    lines = d.get("lines") or []
    if not lines:
        issues.append("missing:lines")
    for i, line in enumerate(lines):
        expected = dec(line.get("qty_cartons", 0)) * dec(line.get("price_per_carton", 0))
        if abs(dec(line.get("amount", 0)) - expected) > ROUNDING:
            issues.append(f"line_amount_mismatch:{i}")
    line_sum = sum((dec(x.get("amount", 0)) for x in lines), Decimal("0"))
    if lines and abs(line_sum - dec(d.get("subtotal", 0))) > ROUNDING:
        issues.append("subtotal_mismatch")
    expected_tax = dec(d.get("subtotal", 0)) * dec(d.get("gst_rate", 0)) / 100
    if abs(dec(d.get("tax_amount", 0)) - expected_tax) > ROUNDING:
        issues.append("tax_calc_mismatch")
    if abs(dec(d.get("subtotal", 0)) + dec(d.get("tax_amount", 0)) - dec(d.get("total", 0))) > ROUNDING:
        issues.append("total_mismatch")
    return issues


def _packing(d: dict) -> list[str]:
    issues = []
    if not d.get("packing_list_number"):
        issues.append("missing:packing_list_number")
    total = sum(float(x.get("qty_cartons", 0)) for x in d.get("lines") or [])
    if abs(total - float(d.get("total_cartons", 0) or 0)) > 0.01:
        issues.append("carton_total_mismatch")
    return issues


def _lorry(d: dict) -> list[str]:
    issues = [f"missing:{f}" for f in ("lr_number", "vehicle_number") if not d.get(f)]
    if float(d.get("packages", 0) or 0) <= 0:
        issues.append("missing:packages")
    return issues


def _eway(d: dict) -> list[str]:
    issues = []
    ewb = str(d.get("eway_bill_number", ""))
    if not (ewb.isdigit() and len(ewb) == 12):
        issues.append("invalid:eway_bill_number")
    if d.get("supplier_gstin") and not gstin_is_valid(d["supplier_gstin"]):
        issues.append("invalid:supplier_gstin")
    if float(d.get("total_value", 0) or 0) <= 0:
        issues.append("missing:total_value")
    return issues


def _coa(d: dict) -> list[str]:
    issues = [f"missing:{f}" for f in ("batch_number", "expiry_date", "result") if not d.get(f)]
    if d.get("expiry_date") and not parse_date(d["expiry_date"]):
        issues.append("invalid:expiry_date")
    if d.get("result") and d["result"].strip().upper() not in {"PASS", "FAIL"}:
        issues.append("invalid:result")
    return issues


def _note(d: dict) -> list[str]:
    issues = [f"missing:{f}" for f in ("note_number", "original_invoice_number") if not d.get(f)]
    if float(d.get("amount", 0) or 0) <= 0:
        issues.append("missing:amount")
    return issues


_VALIDATORS = {
    "invoice": _invoice,
    "packing_list": _packing,
    "lorry_receipt": _lorry,
    "eway_bill": _eway,
    "quality_certificate": _coa,
    "credit_note": _note,
    "debit_note": _note,
}
