"""The match engine: compares every paper in a shipment pack with each other, with the
purchase order and with the goods receipt. Plain code by design - agents call it as a
tool, but never do this arithmetic themselves.

Input is a plain snapshot (no database access), so the engine is trivially testable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal

from app.rules.normalize import dec, norm_vehicle, parse_date, pct_diff

BLOCK = "block"  # needs a decision before payment
INFO = "info"  # worth showing, does not block


@dataclass
class Issue:
    code: str
    severity: str
    message: str
    evidence: dict = field(default_factory=dict)


@dataclass
class POSnapshot:
    po_number: str
    supplier_gstin: str
    lines: dict[str, dict]  # sku -> {"qty": int, "price": Decimal}


@dataclass
class GRNSnapshot:
    grn_number: str
    received_date: date | None
    vehicle_no: str
    lines: dict[str, dict]  # sku -> {"qty": int, "batch": str}


@dataclass
class PackSnapshot:
    documents: list[dict]  # {"id", "doc_type", "data", "flags", "confidence", "duplicate_of"}
    po: POSnapshot | None
    grns: list[GRNSnapshot]
    products: dict[str, dict]  # sku -> {"gst_rate": Decimal, "requires_coa": bool, "hsn": str}
    price_tolerance_pct: Decimal
    qty_tolerance_pct: Decimal
    eway_value_tolerance_pct: Decimal
    min_shelf_life_days: int
    confidence_threshold: float
    duplicate_hits: list[dict] = field(default_factory=list)  # from app.rules.dedupe


@dataclass
class MatchResult:
    ok: bool
    route: str  # auto_approve | investigate | human_review | wait
    issues: list[Issue]
    invoice_total: Decimal
    payable_amount: Decimal
    debit_note_amount: Decimal
    lines: list[dict]

    def to_json(self) -> dict:
        d = asdict(self)
        for k in ("invoice_total", "payable_amount", "debit_note_amount"):
            d[k] = str(d[k])
        for line in d["lines"]:
            for k, v in list(line.items()):
                if isinstance(v, Decimal):
                    line[k] = str(v)
        return d

    @property
    def issue_codes(self) -> list[str]:
        return sorted({i.code for i in self.issues})


def _docs(snapshot: PackSnapshot, doc_type: str) -> list[dict]:
    return [d for d in snapshot.documents if d["doc_type"] == doc_type and not d.get("duplicate_of")]


def run_match(s: PackSnapshot) -> MatchResult:
    issues: list[Issue] = []
    invoices = _docs(s, "invoice")
    zero = Decimal("0.00")

    # ---- human-review triggers (not for an agent to argue with) -----------------
    for d in s.documents:
        if "possible_injection" in (d.get("flags") or []):
            issues.append(Issue("SUSPICIOUS_CONTENT", BLOCK,
                                "Document contains text that tries to instruct the AI system; a person must review it.",
                                {"document_id": d["id"]}))
        if d.get("confidence", 1.0) < s.confidence_threshold:
            issues.append(Issue("LOW_CONFIDENCE", BLOCK,
                                f"{d['doc_type']} could not be read with confidence ({d.get('confidence', 0):.2f}).",
                                {"document_id": d["id"], "uncertain_fields": d.get("uncertain_fields", [])}))

    for hit in s.duplicate_hits:
        issues.append(Issue("POSSIBLE_DUPLICATE", BLOCK, hit["message"], hit))

    if not invoices:
        return MatchResult(False, "wait", issues + [Issue("MISSING_INVOICE", INFO,
                           "Shipping papers received but no invoice yet; the pack will wait.")],
                           zero, zero, zero, [])

    # ---- aggregate billed lines across the pack's invoices ------------------------
    billed: dict[str, dict] = {}
    invoice_total = zero
    invoice_rate = None
    for inv in invoices:
        data = inv["data"]
        invoice_total += dec(data.get("total", 0))
        invoice_rate = dec(data.get("gst_rate", 0))
        for line in data.get("lines", []):
            sku = line["sku"].strip().upper()
            b = billed.setdefault(sku, {"qty": Decimal("0"), "price": dec(line.get("price_per_carton", 0))})
            b["qty"] += dec(line.get("qty_cartons", 0), "1")
    credit = sum((dec(n["data"].get("amount", 0)) for n in _docs(s, "credit_note")), zero)

    # ---- purchase order ---------------------------------------------------------
    if s.po is None:
        po_ref = invoices[0]["data"].get("po_number") or "(none printed)"
        issues.append(Issue("NO_PO", BLOCK, f"No purchase order found for PO number {po_ref}.", {"po_number": po_ref}))
    else:
        inv_gstin = invoices[0]["data"].get("supplier_gstin", "").upper()
        if inv_gstin and inv_gstin != s.po.supplier_gstin.upper():
            issues.append(Issue("PO_SUPPLIER_MISMATCH", BLOCK,
                                f"Invoice GSTIN {inv_gstin} differs from the PO supplier {s.po.supplier_gstin}.",
                                {"invoice_gstin": inv_gstin, "po_gstin": s.po.supplier_gstin}))

    received: dict[str, Decimal] = {}
    grn_batches: set[str] = set()
    received_date = None
    for g in s.grns:
        received_date = received_date or g.received_date
        for sku, gl in g.lines.items():
            received[sku.upper()] = received.get(sku.upper(), Decimal("0")) + Decimal(gl["qty"])
            if gl.get("batch"):
                grn_batches.add(gl["batch"].upper())
    if s.po is not None and not s.grns:
        issues.append(Issue("NO_GRN", BLOCK, "The warehouse has not recorded receiving these goods yet.",
                            {"po_number": s.po.po_number}))

    # ---- line by line: quantity, price, tax -----------------------------------
    lines_out = []
    payable_sub = zero
    for sku, b in sorted(billed.items()):
        po_line = s.po.lines.get(sku) if s.po else None
        prod = s.products.get(sku, {})
        pay_qty = b["qty"]
        pay_price = b["price"]
        if po_line is None and s.po is not None:
            issues.append(Issue("ITEM_NOT_ON_PO", BLOCK, f"{sku} is billed but not on {s.po.po_number}.", {"sku": sku}))
        if po_line is not None:
            po_price = dec(po_line["price"])
            diff = pct_diff(b["price"], po_price)
            if diff > s.price_tolerance_pct:
                issues.append(Issue("PRICE_MISMATCH", BLOCK,
                                    f"{sku}: billed ₹{b['price']} per carton vs PO price ₹{po_price} "
                                    f"({diff}% higher, tolerance {s.price_tolerance_pct}%).",
                                    {"sku": sku, "billed_price": str(b["price"]), "po_price": str(po_price),
                                     "diff_pct": str(diff)}))
                pay_price = po_price
            if b["qty"] > Decimal(po_line["qty"]):
                issues.append(Issue("OVER_ORDER_QTY", BLOCK,
                                    f"{sku}: billed {b['qty']} cartons but only {po_line['qty']} were ordered.",
                                    {"sku": sku, "billed": str(b["qty"]), "ordered": po_line["qty"]}))
                pay_qty = min(pay_qty, Decimal(po_line["qty"]))
        if s.grns:
            got = received.get(sku, Decimal("0"))
            allowed = got * (1 + s.qty_tolerance_pct / 100)
            if b["qty"] > allowed:
                issues.append(Issue("SHORT_SHIPMENT", BLOCK,
                                    f"{sku}: billed {b['qty']} cartons; warehouse received {got}.",
                                    {"sku": sku, "billed": str(b["qty"]), "received": str(got)}))
                pay_qty = min(pay_qty, got)
        if prod and invoice_rate is not None and dec(prod["gst_rate"]) != invoice_rate:
            issues.append(Issue("TAX_RATE_MISMATCH", BLOCK,
                                f"{sku}: invoice charges GST {invoice_rate}% but HSN {prod.get('hsn')} "
                                f"carries {prod['gst_rate']}%.",
                                {"sku": sku, "invoice_rate": str(invoice_rate), "expected_rate": str(prod["gst_rate"])}))
        line_pay = (pay_qty * pay_price).quantize(Decimal("0.01"))
        rate = dec(prod.get("gst_rate", invoice_rate or 0))
        payable_sub += line_pay * (1 + rate / 100)
        lines_out.append({"sku": sku, "billed_qty": b["qty"], "billed_price": b["price"],
                          "received_qty": received.get(sku), "pay_qty": pay_qty, "pay_price": pay_price})

    # ---- cross-document checks ------------------------------------------------
    billed_total_qty = sum((b["qty"] for b in billed.values()), Decimal("0"))
    for pl in _docs(s, "packing_list"):
        packed = dec(pl["data"].get("total_cartons", 0), "1")
        if packed != billed_total_qty:
            issues.append(Issue("PACKING_QTY_MISMATCH", BLOCK,
                                f"Packing list shows {packed} cartons; invoice bills {billed_total_qty}.",
                                {"packed": str(packed), "billed": str(billed_total_qty)}))
    lr_vehicles = set()
    for lr in _docs(s, "lorry_receipt"):
        carried = dec(lr["data"].get("packages", 0), "1")
        lr_vehicles.add(norm_vehicle(lr["data"].get("vehicle_number", "")))
        if carried != billed_total_qty:
            issues.append(Issue("LR_QTY_MISMATCH", INFO if not s.grns else BLOCK,
                                f"Transporter carried {carried} cartons; invoice bills {billed_total_qty}.",
                                {"carried": str(carried), "billed": str(billed_total_qty)}))
    for ewb in _docs(s, "eway_bill"):
        d = ewb["data"]
        diff = abs(pct_diff(dec(d.get("total_value", 0)), invoice_total)) if invoice_total else Decimal("0")
        if diff > s.eway_value_tolerance_pct:
            issues.append(Issue("EWAY_VALUE_MISMATCH", BLOCK,
                                f"E-way bill value ₹{dec(d.get('total_value', 0))} vs invoice total ₹{invoice_total}.",
                                {"eway_value": str(dec(d.get("total_value", 0))), "invoice_total": str(invoice_total)}))
        inv_gstin = invoices[0]["data"].get("supplier_gstin", "").upper()
        if d.get("supplier_gstin") and inv_gstin and d["supplier_gstin"].upper() != inv_gstin:
            issues.append(Issue("EWAY_GSTIN_MISMATCH", BLOCK,
                                f"E-way bill supplier GSTIN {d['supplier_gstin']} differs from invoice {inv_gstin}.", {}))
        veh = norm_vehicle(d.get("vehicle_number", ""))
        if veh and lr_vehicles and veh not in lr_vehicles:
            issues.append(Issue("VEHICLE_MISMATCH", BLOCK,
                                f"E-way bill vehicle {d.get('vehicle_number')} is not the lorry receipt's vehicle.",
                                {"eway_vehicle": d.get("vehicle_number"), "lr_vehicles": sorted(lr_vehicles)}))

    # ---- quality certificates -------------------------------------------------
    coas = _docs(s, "quality_certificate")
    batch_to_sku = {gl["batch"].upper(): sku for g in s.grns for sku, gl in g.lines.items() if gl.get("batch")}
    covered = set()
    for c in coas:
        if c["data"].get("sku"):
            covered.add(c["data"]["sku"].strip().upper())
        if (c["data"].get("batch_number") or "").upper() in batch_to_sku:
            covered.add(batch_to_sku[c["data"]["batch_number"].upper()])
    missing = [sku for sku in billed if s.products.get(sku, {}).get("requires_coa") and sku not in covered]
    if missing:
        issues.append(Issue("MISSING_COA", BLOCK,
                            f"No quality certificate for {', '.join(missing)}, which require one.", {"skus": missing}))
    for c in coas:
        d = c["data"]
        if str(d.get("result", "")).strip().upper() != "PASS":
            issues.append(Issue("COA_FAILED", BLOCK, f"Quality certificate {d.get('certificate_number')} did not pass.", {}))
        exp = parse_date(d.get("expiry_date", ""))
        ref = received_date or date.today()
        if exp and (exp - ref).days < s.min_shelf_life_days:
            issues.append(Issue("SHORT_SHELF_LIFE", BLOCK,
                                f"Batch {d.get('batch_number')} expires {exp.isoformat()}, "
                                f"{(exp - ref).days} days after receipt (minimum {s.min_shelf_life_days}).",
                                {"expiry": exp.isoformat(), "days": (exp - ref).days}))
        if grn_batches and d.get("batch_number") and d["batch_number"].upper() not in grn_batches:
            issues.append(Issue("COA_BATCH_MISMATCH", BLOCK,
                                f"Certificate batch {d['batch_number']} was not received by the warehouse.",
                                {"coa_batch": d["batch_number"], "grn_batches": sorted(grn_batches)}))

    blocking = [i for i in issues if i.severity == BLOCK]
    payable = max(zero, (payable_sub - credit).quantize(Decimal("0.01")))
    if not blocking or abs(invoice_total - credit - payable) < Decimal("1.00"):
        payable = max(zero, invoice_total - credit)  # nothing to dispute: pay what was billed
    debit = max(zero, (invoice_total - credit - payable).quantize(Decimal("0.01")))
    if not blocking:
        route = "auto_approve"
    elif any(i.code in {"SUSPICIOUS_CONTENT", "LOW_CONFIDENCE"} for i in blocking):
        route = "human_review"
    else:
        route = "investigate"
    return MatchResult(not blocking, route, issues, invoice_total, payable, debit, lines_out)
