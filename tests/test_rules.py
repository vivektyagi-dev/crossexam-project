from datetime import date
from decimal import Decimal

from app.rules.match_engine import GRNSnapshot, PackSnapshot, POSnapshot, run_match
from app.rules.normalize import gstin_check_char, gstin_is_valid, norm_invoice_no, norm_po
from app.rules.validation import validate

GSTIN = "33ABCDE1234F1Z" + gstin_check_char("33ABCDE1234F1Z")


def test_gstin_checksum():
    assert gstin_is_valid(GSTIN)
    bad = GSTIN[:-1] + ("A" if GSTIN[-1] != "A" else "B")
    assert not gstin_is_valid(bad)
    assert not gstin_is_valid("33ABCDE1234F1Y5")


def test_normalisers():
    assert norm_invoice_no("INV-00123") == norm_invoice_no("inv 123") == norm_invoice_no("123") == "123"
    assert norm_po("po 40001") == "PO-40001"


def _invoice(qty=1000, price=480.0, rate=18.0):
    sub = qty * price
    tax = round(sub * rate / 100, 2)
    return {"supplier_gstin": GSTIN, "invoice_number": "INV-9", "invoice_date": "2026-09-10", "po_number": "PO-88421",
            "lines": [{"sku": "SKU-1001", "qty_cartons": qty, "price_per_carton": price, "amount": sub}],
            "subtotal": sub, "gst_rate": rate, "tax_amount": tax, "total": sub + tax, "confidence": 0.97}


def test_invoice_validation_catches_arithmetic():
    assert validate("invoice", _invoice()) == []
    broken = _invoice()
    broken["total"] += 500
    assert "total_mismatch" in validate("invoice", broken)


def _snapshot(docs, received=950, po_price="450", po_qty=1000):
    return PackSnapshot(
        documents=docs,
        po=POSnapshot("PO-88421", GSTIN, {"SKU-1001": {"qty": po_qty, "price": Decimal(po_price)}}),
        grns=[GRNSnapshot("GRN-1", date(2026, 9, 12), "TN45AB1234", {"SKU-1001": {"qty": received, "batch": "SH-2611"}})],
        products={"SKU-1001": {"gst_rate": Decimal("18"), "requires_coa": True, "hsn": "3305"}},
        price_tolerance_pct=Decimal("2"), qty_tolerance_pct=Decimal("0"), eway_value_tolerance_pct=Decimal("1"),
        min_shelf_life_days=180, confidence_threshold=0.8)


def test_shampoo_example_from_the_proposal():
    """The worked example: billed 1,000 at ₹480; received 950; PO price ₹450."""
    inv = _invoice()
    docs = [
        {"id": "i", "doc_type": "invoice", "data": inv, "flags": [], "confidence": 0.97},
        {"id": "p", "doc_type": "packing_list", "data": {"total_cartons": 1000,
                                                         "lines": [{"sku": "SKU-1001", "batch_number": "SH-2611"}]},
         "flags": [], "confidence": 0.97},
        {"id": "l", "doc_type": "lorry_receipt", "data": {"packages": 950, "vehicle_number": "TN45 AB 1234"},
         "flags": [], "confidence": 0.9},
        {"id": "e", "doc_type": "eway_bill", "data": {"total_value": inv["total"], "supplier_gstin": GSTIN,
                                                      "vehicle_number": "TN45AB1234"}, "flags": [], "confidence": 1},
        {"id": "c", "doc_type": "quality_certificate", "data": {"result": "PASS", "expiry_date": "2027-03-31",
                                                                "batch_number": "SH-2611", "certificate_number": "C1"},
         "flags": [], "confidence": 0.97},
    ]
    r = run_match(_snapshot(docs))
    assert set(r.issue_codes) == {"SHORT_SHIPMENT", "PRICE_MISMATCH", "LR_QTY_MISMATCH"}
    assert r.route == "investigate"
    # pay 950 x 450 + 18% GST = 504,450.00 ; billed 566,400.00
    assert r.payable_amount == Decimal("504450.00")
    assert r.debit_note_amount == Decimal("61950.00")


def test_clean_pack_auto_approves():
    inv = _invoice(qty=950, price=450.0)
    docs = [{"id": "i", "doc_type": "invoice", "data": inv, "flags": [], "confidence": 0.97},
            {"id": "c", "doc_type": "quality_certificate", "data": {"result": "PASS", "expiry_date": "2027-12-31",
                                                                    "batch_number": "SH-2611"}, "flags": [], "confidence": 1}]
    r = run_match(_snapshot(docs))
    assert r.ok and r.route == "auto_approve"
    assert r.payable_amount == Decimal(str(inv["total"])).quantize(Decimal("0.01"))


def test_injection_and_low_confidence_force_human_review():
    inv = _invoice(qty=950, price=450.0)
    docs = [{"id": "i", "doc_type": "invoice", "data": inv, "flags": ["possible_injection"], "confidence": 0.97},
            {"id": "c", "doc_type": "quality_certificate", "data": {"result": "PASS", "expiry_date": "2027-12-31",
                                                                    "batch_number": "SH-2611"}, "flags": [], "confidence": 0.5}]
    r = run_match(_snapshot(docs))
    assert r.route == "human_review"
    assert {"SUSPICIOUS_CONTENT", "LOW_CONFIDENCE"} <= set(r.issue_codes)


def test_missing_invoice_waits():
    docs = [{"id": "l", "doc_type": "lorry_receipt", "data": {"packages": 950}, "flags": [], "confidence": 0.9}]
    assert run_match(_snapshot(docs)).route == "wait"
