"""Renders the same underlying data in every format suppliers really use: digital PDFs
in three different layouts, scans and phone photos, Excel sheets and government JSON."""

from __future__ import annotations

import io
import json
import random

from openpyxl import Workbook
from PIL import Image, ImageFilter
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from datagen.catalog import BUYER

W, H = A4


def _money(x: float) -> str:
    return f"{x:,.2f}"


def _iso_to_dmy(d: str) -> str:
    y, m, dd = d.split("-")
    return f"{dd}/{m}/{y}"


class _Doc:
    def __init__(self):
        self.buf = io.BytesIO()
        self.c = canvas.Canvas(self.buf, pagesize=A4)
        self.y = H - 50

    def text(self, x, txt, size=9, bold=False, right=False, dy=13):
        self.c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        (self.c.drawRightString if right else self.c.drawString)(x, self.y, str(txt))
        self.y -= dy

    def at(self, x, y, txt, size=9, bold=False, right=False):
        self.c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        (self.c.drawRightString if right else self.c.drawString)(x, y, str(txt))

    def line(self):
        self.c.line(40, self.y + 8, W - 40, self.y + 8)
        self.y -= 6

    def table(self, headers, rows, xs, right_cols=()):
        self.c.setFont("Helvetica-Bold", 8.5)
        for h, x in zip(headers, xs, strict=False):
            (self.c.drawRightString if headers.index(h) in right_cols else self.c.drawString)(x, self.y, h)
        self.c.line(40, self.y - 5, W - 40, self.y - 5)
        self.y -= 18
        self.c.setFont("Helvetica", 8.5)
        for r in rows:
            for i, (v, x) in enumerate(zip(r, xs, strict=False)):
                (self.c.drawRightString if i in right_cols else self.c.drawString)(x, self.y, str(v))
            self.y -= 13
        self.line()

    def done(self) -> bytes:
        self.c.showPage()
        self.c.save()
        return self.buf.getvalue()


# ----------------------------------------------------------------------------- invoices
def invoice_pdf(inv: dict, layout: str = "A", injection: str | None = None) -> bytes:
    d = _Doc()
    sup = inv["supplier"]
    if layout == "A":
        d.text(40, sup["name"], 14, bold=True, dy=15)
        d.text(40, f"GSTIN: {inv['supplier_gstin']}   State code: {inv['supplier_gstin'][:2]}")
        d.text(40, sup["address"], dy=22)
        d.text(W / 2, "TAX INVOICE", 13, bold=True, dy=20)
        top = d.y
        d.at(40, top, f"Invoice No: {inv['invoice_number']}", bold=True)
        d.at(40, top - 13, f"Invoice Date: {_iso_to_dmy(inv['invoice_date'])}")
        d.at(40, top - 26, f"Buyer PO: {inv['po_number']}")
        d.at(330, top, f"Bill to: {BUYER['name']}")
        d.at(330, top - 13, f"GSTIN: {inv['buyer_gstin']}")
        d.at(330, top - 26, f"E-Way Bill: {inv['eway_bill_number']}   Vehicle: {inv['vehicle_number']}")
        d.y = top - 50
        rows = [(i + 1, line["sku"], line["description"], line["hsn"], int(line["qty_cartons"]),
                 _money(line["price_per_carton"]), _money(line["amount"])) for i, line in enumerate(inv["lines"])]
        d.table(["#", "Item Code", "Description", "HSN", "Cartons", "Rate/Carton", "Amount (Rs)"], rows,
                [40, 60, 130, 330, 400, 480, W - 45], right_cols=(4, 5, 6))
    elif layout == "B":
        d.text(W - 40, "INVOICE", 18, bold=True, right=True, dy=22)
        d.text(W - 40, f"Bill No. {inv['invoice_number']}", right=True)
        d.text(W - 40, f"Dated {inv['invoice_date']}", right=True)
        d.text(W - 40, f"Your Order Ref: {inv['po_number']}", right=True, dy=20)
        d.text(40, f"From: {sup['name']}", bold=True)
        d.text(40, f"Seller GSTIN {inv['supplier_gstin']}")
        d.text(40, f"Consignee: {BUYER['name']}, GSTIN {inv['buyer_gstin']}")
        d.text(40, f"Transport: vehicle {inv['vehicle_number']}, EWB {inv['eway_bill_number']}", dy=22)
        rows = [(line["description"], line["sku"], line["hsn"], _money(line["price_per_carton"]),
                 int(line["qty_cartons"]), _money(line["amount"])) for line in inv["lines"]]
        d.table(["Particulars", "Code", "HSN/SAC", "Price per case", "No. of Cases", "Value"], rows,
                [40, 230, 300, 420, 480, W - 45], right_cols=(3, 4, 5))
    else:  # layout C: compact, labels differ again
        d.text(40, f"{sup['name']} | GST {inv['supplier_gstin']}", 11, bold=True, dy=18)
        d.text(40, f"TAX INVOICE  Ref {inv['invoice_number']}  Date {_iso_to_dmy(inv['invoice_date'])}  "
                   f"P.O. {inv['po_number']}", dy=18)
        d.text(40, f"Recipient GSTIN {inv['buyer_gstin']}  EWB No {inv['eway_bill_number']}", dy=20)
        rows = [(line["sku"], f"{line['description']} (HSN {line['hsn']})", f"{int(line['qty_cartons'])} ctn",
                 _money(line["price_per_carton"]), _money(line["amount"])) for line in inv["lines"]]
        d.table(["SKU", "Item", "Qty", "Rate", "Taxable"], rows, [40, 110, 380, 470, W - 45], right_cols=(3, 4))
    rate = inv["gst_rate"]
    intra = inv["supplier_gstin"][:2] == BUYER["state_code"]
    d.text(W - 45, f"Taxable value: {_money(inv['subtotal'])}", right=True)
    if intra:
        half = inv["tax_amount"] / 2
        d.text(W - 45, f"CGST @ {rate / 2:g}%: {_money(half)}", right=True)
        d.text(W - 45, f"SGST @ {rate / 2:g}%: {_money(inv['tax_amount'] - half)}", right=True)
    else:
        d.text(W - 45, f"IGST @ {rate:g}%: {_money(inv['tax_amount'])}", right=True)
    d.text(W - 45, f"Invoice Total (Rs): {_money(inv['total'])}", 11, bold=True, right=True, dy=24)
    d.text(40, f"Bank: State Bank of India, A/C No: {inv['bank_account']}, IFSC: {inv['ifsc']}", 8)
    d.text(40, "Goods once sold will not be taken back. Subject to local jurisdiction.", 7)
    if injection:
        d.text(40, injection, 6.5)
    d.text(40, "Authorised Signatory", 8, bold=True)
    return d.done()


def invoice_xlsx(inv: dict, variant: int) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Invoice"
    qty_label = ["Qty (cartons)", "Quantity", "No. of Cases"][variant % 3]
    ws.append([inv["supplier"]["name"]])
    ws.append(["GSTIN", inv["supplier_gstin"]])
    ws.append(["Invoice No", inv["invoice_number"], "Date", inv["invoice_date"]])
    ws.append(["PO Ref", inv["po_number"], "EWB", inv["eway_bill_number"], "Vehicle", inv["vehicle_number"]])
    ws.append(["Buyer GSTIN", inv["buyer_gstin"]])
    ws.append([])
    ws.append(["Item Code", "Description", "HSN", qty_label, "Rate", "Amount"])
    for line in inv["lines"]:
        ws.append([line["sku"], line["description"], line["hsn"], line["qty_cartons"], line["price_per_carton"],
                   line["amount"]])
    ws.append([])
    ws.append(["", "", "", "", "Taxable", inv["subtotal"]])
    ws.append(["", "", "", "", f"GST {inv['gst_rate']}%", inv["tax_amount"]])
    ws.append(["", "", "", "", "Total", inv["total"]])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def einvoice_json(inv: dict) -> bytes:
    """Simplified GST e-invoice (INV-01 style) payload."""
    intra = inv["supplier_gstin"][:2] == BUYER["state_code"]
    tax = inv["tax_amount"]
    doc = {
        "Version": "1.1",
        "TranDtls": {"TaxSch": "GST", "SupTyp": "B2B"},
        "DocDtls": {"Typ": "INV", "No": inv["invoice_number"], "Dt": _iso_to_dmy(inv["invoice_date"])},
        "SellerDtls": {"Gstin": inv["supplier_gstin"], "LglNm": inv["supplier"]["name"]},
        "BuyerDtls": {"Gstin": inv["buyer_gstin"], "LglNm": BUYER["name"]},
        "RefDtls": {"PoRef": inv["po_number"]},
        "ItemList": [{"SlNo": str(i + 1), "PrdCd": line["sku"], "PrdDesc": line["description"], "HsnCd": line["hsn"],
                      "Qty": line["qty_cartons"], "Unit": "CTN", "UnitPrice": line["price_per_carton"],
                      "AssAmt": line["amount"], "GstRt": inv["gst_rate"]} for i, line in enumerate(inv["lines"])],
        "ValDtls": {"AssVal": inv["subtotal"], "CgstVal": round(tax / 2, 2) if intra else 0,
                    "SgstVal": round(tax - round(tax / 2, 2), 2) if intra else 0, "IgstVal": 0 if intra else tax,
                    "TotInvVal": inv["total"]},
        "EwbDtls": {"EwbNo": inv["eway_bill_number"], "VehNo": inv["vehicle_number"].replace(" ", "")},
    }
    return json.dumps(doc, indent=2).encode()


# ----------------------------------------------------------------------------- shipping and quality
def packing_pdf(pl: dict) -> bytes:
    d = _Doc()
    d.text(40, pl["supplier_name"], 12, bold=True)
    d.text(40, f"GSTIN {pl['supplier_gstin']}", dy=20)
    d.text(W / 2 - 40, "PACKING LIST", 13, bold=True, dy=20)
    d.text(40, f"Packing List No: {pl['packing_list_number']}    Against Invoice: {pl['invoice_number']}    "
               f"PO: {pl['po_number']}", dy=20)
    rows = [(line["sku"], line["batch_number"], int(line["qty_cartons"]), f"{line['gross_weight_kg']:.1f}")
            for line in pl["lines"]]
    d.table(["Item Code", "Batch No", "Cartons", "Gross Wt (kg)"], rows, [40, 160, 330, W - 45], right_cols=(2, 3))
    d.text(W - 45, f"Total cartons: {int(pl['total_cartons'])}   Total weight: {pl['total_weight_kg']:.1f} kg",
           bold=True, right=True)
    return d.done()


def packing_xlsx(pl: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Packing List"
    ws.append(["PACKING LIST", pl["packing_list_number"]])
    ws.append(["Supplier GSTIN", pl["supplier_gstin"], "Invoice", pl["invoice_number"], "PO", pl["po_number"]])
    ws.append([])
    ws.append(["SKU", "Batch", "Cases", "Gross kg"])
    for line in pl["lines"]:
        ws.append([line["sku"], line["batch_number"], line["qty_cartons"], line["gross_weight_kg"]])
    ws.append(["Total", "", pl["total_cartons"], pl["total_weight_kg"]])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def lr_pdf(lr: dict) -> bytes:
    d = _Doc()
    d.text(40, lr["transporter_name"].upper(), 14, bold=True)
    d.text(40, "Fleet owners & transport contractors | All India permit", 8, dy=20)
    d.text(W / 2 - 50, "LORRY RECEIPT / CONSIGNMENT NOTE", 11, bold=True, dy=20)
    d.text(40, f"L.R. No: {lr['lr_number']}        Date: {_iso_to_dmy(lr['lr_date'])}")
    d.text(40, f"Vehicle No: {lr['vehicle_number']}", bold=True)
    d.text(40, f"Consignor GSTIN: {lr['consignor_gstin']}")
    d.text(40, f"Consignee: {BUYER['name']}  GSTIN: {lr['consignee_gstin']}")
    d.text(40, f"Invoice No: {lr['invoice_number']}", dy=20)
    d.table(["Packages", "Said to contain", "Actual Wt (kg)", "Freight"],
            [(int(lr["packages"]), "FMCG goods in cartons", f"{lr['weight_kg']:.0f}", "TO PAY")],
            [40, 130, 330, 450])
    d.text(40, "Received the above packages in apparent good order and condition.", 8)
    return d.done()


def eway_pdf(e: dict) -> bytes:
    d = _Doc()
    d.text(W / 2 - 30, "e-Way Bill", 14, bold=True, dy=20)
    d.text(40, f"E-Way Bill No: {e['eway_bill_number']}", bold=True)
    d.text(40, f"E-Way Bill Date: {_iso_to_dmy(e['generated_date'])}   Valid Upto: {_iso_to_dmy(e['valid_until'])}")
    d.text(40, f"GSTIN of Supplier: {e['supplier_gstin']}")
    d.text(40, f"GSTIN of Recipient: {e['recipient_gstin']}")
    d.text(40, f"Document No: {e['invoice_number']}   Vehicle No: {e['vehicle_number']}", dy=20)
    d.table(["HSN Code", "Quantity", "Taxable Amount"],
            [(i["hsn"], f"{int(i['qty_cartons'])} CTN", _money(i["taxable_value"])) for i in e["items"]],
            [40, 200, W - 45], right_cols=(2,))
    d.text(W - 45, f"Total Invoice Value: {_money(e['total_value'])}", bold=True, right=True)
    return d.done()


def eway_json(e: dict) -> bytes:
    doc = {"ewbNo": int(e["eway_bill_number"]), "ewayBillDate": _iso_to_dmy(e["generated_date"]) + " 10:15:00",
           "validUpto": _iso_to_dmy(e["valid_until"]) + " 23:59:00", "fromGstin": e["supplier_gstin"],
           "toGstin": e["recipient_gstin"], "docNo": e["invoice_number"], "docType": "INV",
           "totInvValue": e["total_value"],
           "itemList": [{"hsnCode": i["hsn"], "quantity": i["qty_cartons"], "qtyUnit": "CTN",
                         "taxableAmount": i["taxable_value"]} for i in e["items"]],
           "VehiclListDetails": [{"vehicleNo": e["vehicle_number"].replace(" ", "")}]}
    return json.dumps(doc, indent=2).encode()


def coa_pdf(c: dict) -> bytes:
    d = _Doc()
    d.text(40, c["lab_name"], 12, bold=True)
    d.text(40, f"Supplier GSTIN {c['supplier_gstin']}", dy=22)
    d.text(W / 2 - 60, "CERTIFICATE OF ANALYSIS", 13, bold=True, dy=22)
    d.text(40, f"Certificate No: {c['certificate_number']}")
    d.text(40, f"Product: {c['sku']}   Batch No: {c['batch_number']}")
    d.text(40, f"Mfg. Date: {_iso_to_dmy(c['manufacture_date'])}   Best Before / Expiry: {_iso_to_dmy(c['expiry_date'])}",
           dy=20)
    d.table(["Parameter", "Specification", "Result"],
            [("Appearance", "Conforms", "Conforms"), ("pH / Moisture", "Within limits", "Within limits"),
             ("Microbial count", "< 1000 cfu/g", "Complies" if c["result"] == "PASS" else "Exceeds")],
            [40, 220, 400])
    d.text(40, f"Overall result: {c['result']}", 11, bold=True)
    return d.done()


def note_pdf(n: dict) -> bytes:
    d = _Doc()
    d.text(40, n["supplier_name"], 12, bold=True)
    d.text(40, f"GSTIN {n['supplier_gstin']}", dy=20)
    d.text(W / 2 - 40, f"{n['note_type'].upper()} NOTE", 13, bold=True, dy=20)
    d.text(40, f"Note No: {n['note_number']}    Against Invoice: {n['original_invoice_number']}")
    d.text(40, f"Reason: {n['reason']}")
    d.text(40, f"Amount (incl. GST): Rs {_money(n['amount'])}", bold=True)
    return d.done()


# ----------------------------------------------------------------------------- scans, photos, bundles
def merge_pdfs(parts: list[bytes]) -> bytes:
    w = PdfWriter()
    for p in parts:
        for page in PdfReader(io.BytesIO(p)).pages:
            w.add_page(page)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def _degrade(img: Image.Image, rng: random.Random, heavy: bool) -> Image.Image:
    img = img.convert("L").rotate(rng.uniform(-1.8, 1.8) if heavy else rng.uniform(-0.8, 0.8),
                                  expand=True, fillcolor=255)
    img = img.filter(ImageFilter.GaussianBlur(radius=0.9 if heavy else 0.5))
    px = img.load()
    w, h = img.size
    for _ in range(int(w * h * (0.004 if heavy else 0.0015))):
        px[rng.randrange(w), rng.randrange(h)] = rng.choice((0, 90, 200))
    return img


def scanify(pdf: bytes, rng: random.Random, heavy: bool = False) -> bytes:
    """Image-only PDF: no text layer, slightly crooked, noisy - like an office scanner."""
    import pypdfium2 as pdfium

    pages = []
    for page in pdfium.PdfDocument(pdf):
        pages.append(_degrade(page.render(scale=1.6).to_pil(), rng, heavy).convert("RGB"))
    buf = io.BytesIO()
    pages[0].save(buf, format="PDF", save_all=True, append_images=pages[1:], resolution=115)
    return buf.getvalue()


def photo(pdf: bytes, rng: random.Random) -> bytes:
    """JPEG of the first page, like a delivery driver's phone photo."""
    import pypdfium2 as pdfium

    img = _degrade(pdfium.PdfDocument(pdf)[0].render(scale=1.4).to_pil(), rng, heavy=True)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=70)
    return buf.getvalue()
