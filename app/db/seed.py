"""Load master data (suppliers, products, POs, GRNs, past resolutions) - what the ERP
would already hold. Idempotent: safe to run more than once.

    python -m app.db.seed data/generated/master.json
    python -m app.db.seed --demo 60      (the GKE migrate job: generate it, empty database only)
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.db.models import GoodsReceipt, GRNLine, POLine, Product, PurchaseOrder, Resolution, Supplier
from app.db.session import init_db, session_scope


def seed(path: str) -> dict:
    data = json.loads(open(path).read())
    counts = {"suppliers": 0, "products": 0, "purchase_orders": 0, "goods_receipts": 0, "resolutions": 0}
    with session_scope() as s:
        by_code = {}
        for sp in data["suppliers"]:
            row = s.scalars(select(Supplier).where(Supplier.code == sp["code"])).first()
            if row is None:
                row = Supplier(code=sp["code"], name=sp["name"], gstin=sp["gstin"], email=sp["email"],
                               state_code=sp["state_code"], uses_einvoice=sp["uses_einvoice"],
                               price_tolerance_pct=Decimal(str(sp["price_tolerance_pct"])))
                s.add(row)
                counts["suppliers"] += 1
            by_code[sp["code"]] = row
        for p in data["products"]:
            if s.scalars(select(Product).where(Product.sku == p["sku"])).first() is None:
                s.add(Product(sku=p["sku"], name=p["name"], hsn=p["hsn"], gst_rate=Decimal(str(p["gst_rate"])),
                              units_per_carton=p["units_per_carton"],
                              carton_weight_kg=Decimal(str(p["carton_weight_kg"])), requires_coa=p["requires_coa"]))
                counts["products"] += 1
        s.flush()
        pos = {}
        for po in data["purchase_orders"]:
            row = s.scalars(select(PurchaseOrder).where(PurchaseOrder.po_number == po["po_number"])).first()
            if row is None:
                row = PurchaseOrder(po_number=po["po_number"], supplier_id=by_code[po["supplier_code"]].id,
                                    order_date=date.fromisoformat(po["order_date"]),
                                    lines=[POLine(sku=line["sku"], qty_cartons=line["qty_cartons"],
                                                  price_per_carton=Decimal(str(line["price_per_carton"])))
                                           for line in po["lines"]])
                s.add(row)
                counts["purchase_orders"] += 1
            pos[po["po_number"]] = row
        s.flush()
        for g in data["goods_receipts"]:
            if s.scalars(select(GoodsReceipt).where(GoodsReceipt.grn_number == g["grn_number"])).first() is None:
                s.add(GoodsReceipt(grn_number=g["grn_number"], po_id=pos[g["po_number"]].id,
                                   received_date=date.fromisoformat(g["received_date"]), vehicle_no=g["vehicle_no"],
                                   lines=[GRNLine(sku=line["sku"], qty_cartons=line["qty_cartons"], batch_no=line["batch_no"])
                                          for line in g["lines"]]))
                counts["goods_receipts"] += 1
        if s.scalars(select(Resolution).where(Resolution.pack_id.is_(None))).first() is None:
            from app.agents.llm import embed_text

            for r in data.get("past_resolutions", []):
                s.add(Resolution(pack_id=None, supplier_gstin=r["supplier_gstin"], issue_codes=r["issue_codes"],
                                 summary=r["summary"], resolution=r["resolution"],
                                 debit_note_amount=Decimal(str(r["debit_note_amount"])), decided_by="history",
                                 embedding=embed_text(f"{r['summary']}\n{r['resolution']}"),
                                 created_at=datetime.now(UTC) - timedelta(days=r["days_ago"])))
                counts["resolutions"] += 1
    return counts


def seed_demo(shipments: int) -> dict | None:
    """The demo master data, generated exactly as scripts\\demo-data.cmd does (same seed), so it
    matches the files uploaded from data\\generated. Only into a database without suppliers:
    master data already there, demo or real, is never touched. Returns None when skipped."""
    with session_scope() as s:
        if s.scalars(select(Supplier)).first() is not None:
            return None
    with tempfile.TemporaryDirectory() as out:
        subprocess.run([sys.executable, "-m", "datagen.generate", "--shipments", str(shipments),
                        "--ensure-each-problem", "--out", out], check=True, stdout=subprocess.DEVNULL)
        return seed(str(Path(out) / "master.json"))


if __name__ == "__main__":
    init_db()
    if sys.argv[1:2] == ["--demo"]:
        counts = seed_demo(int(sys.argv[2]))
        print(counts if counts is not None else "Master data already present: demo data not loaded.")
    else:
        print(seed(sys.argv[1] if len(sys.argv) > 1 else "data/generated/master.json"))
