"""Which identifiers link documents into one shipment pack.

Strong keys (PO, e-way bill, supplier+invoice number, batch number) group documents
automatically. Vehicle numbers are weak - one lorry carries many shipments a month - so
they are only offered to the reconciler agent as hints, never used to group on their own.
"""

from __future__ import annotations

from app.rules.normalize import norm_invoice_no, norm_po, norm_vehicle


def doc_keys(doc_type: str, d: dict) -> tuple[set[str], set[str]]:
    """Returns (strong_keys, weak_keys)."""
    strong: set[str] = set()
    weak: set[str] = set()
    gstin = (d.get("supplier_gstin") or d.get("consignor_gstin") or "").upper()

    def inv(number: str) -> None:
        if number and gstin:
            strong.add(f"inv:{gstin}:{norm_invoice_no(number)}")
        elif number:
            weak.add(f"invno:{norm_invoice_no(number)}")

    if d.get("po_number") and norm_po(d["po_number"]):
        strong.add(f"po:{norm_po(d['po_number'])}")
    if d.get("eway_bill_number"):
        strong.add(f"ewb:{str(d['eway_bill_number']).strip()}")
    if d.get("vehicle_number"):
        weak.add(f"vehicle:{norm_vehicle(d['vehicle_number'])}")

    if doc_type == "invoice":
        inv(d.get("invoice_number", ""))
    elif doc_type in ("packing_list", "lorry_receipt", "eway_bill"):
        inv(d.get("invoice_number", ""))
    elif doc_type in ("credit_note", "debit_note"):
        inv(d.get("original_invoice_number", ""))

    if doc_type == "packing_list":
        for line in d.get("lines") or []:
            if line.get("batch_number"):
                strong.add(f"batch:{line['batch_number'].strip().upper()}")
    if doc_type == "quality_certificate" and d.get("batch_number"):
        strong.add(f"batch:{d['batch_number'].strip().upper()}")
    return strong, weak


class UnionFind:
    def __init__(self):
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra
