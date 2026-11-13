"""Format detection and reading. Plain rules, no AI.

Every format ends up as a list of page texts, except government JSON (e-invoice,
e-way bill), which is already structured and is mapped straight to a schema.
Scanned pages are rendered to images here; transcribing them is a vision-model
call done per page by the reading workers (see app/agents/vision.py).
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from pathlib import PurePath

import pandas as pd
from pypdf import PdfReader

MIN_TEXT_CHARS_PER_PAGE = 40


class Fmt:
    DIGITAL_PDF = "digital_pdf"
    SCANNED_PDF = "scanned_pdf"
    IMAGE = "image"
    SPREADSHEET = "spreadsheet"
    GOV_JSON = "gov_json"
    UNKNOWN = "unknown"


@dataclass
class ReadResult:
    fmt: str
    page_texts: list[str] = field(default_factory=list)
    pages_needing_vision: list[int] = field(default_factory=list)  # 0-based
    structured: dict | None = None  # for gov JSON: {"doc_type": ..., "data": {...}}


def detect_format(filename: str, data: bytes) -> str:
    ext = PurePath(filename).suffix.lower()
    if ext == ".json":
        return Fmt.GOV_JSON
    if ext in {".xlsx", ".xls", ".csv"}:
        return Fmt.SPREADSHEET
    if ext in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}:
        return Fmt.IMAGE
    if ext == ".pdf" or data[:5] == b"%PDF-":
        try:
            reader = PdfReader(io.BytesIO(data))
            texts = [(p.extract_text() or "") for p in reader.pages]
        except Exception:
            return Fmt.SCANNED_PDF
        if texts and all(len(t.strip()) >= MIN_TEXT_CHARS_PER_PAGE for t in texts):
            return Fmt.DIGITAL_PDF
        return Fmt.SCANNED_PDF
    return Fmt.UNKNOWN


def read_document(filename: str, data: bytes, max_pages: int = 60) -> ReadResult:
    fmt = detect_format(filename, data)
    if fmt == Fmt.GOV_JSON:
        return ReadResult(fmt=fmt, structured=parse_gov_json(data))
    if fmt == Fmt.SPREADSHEET:
        return ReadResult(fmt=fmt, page_texts=spreadsheet_to_text(filename, data))
    if fmt == Fmt.IMAGE:
        return ReadResult(fmt=fmt, page_texts=[""], pages_needing_vision=[0])
    if fmt in (Fmt.DIGITAL_PDF, Fmt.SCANNED_PDF):
        reader = PdfReader(io.BytesIO(data))
        pages = reader.pages[:max_pages]
        texts = [(p.extract_text() or "").strip() for p in pages]
        needs = [i for i, t in enumerate(texts) if len(t) < MIN_TEXT_CHARS_PER_PAGE]
        return ReadResult(fmt=fmt, page_texts=texts, pages_needing_vision=needs)
    raise ValueError(f"Unsupported file type: {filename}")


def render_page_png(filename: str, data: bytes, page_index: int, scale: float = 2.0) -> bytes:
    """PNG bytes for one page (PDF) or the image itself."""
    fmt = detect_format(filename, data)
    if fmt == Fmt.IMAGE:
        return data
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    page = pdf[page_index]
    image = page.render(scale=scale).to_pil()
    buf = io.BytesIO()
    image.convert("L").save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def spreadsheet_to_text(filename: str, data: bytes) -> list[str]:
    """One 'page' per sheet, as CSV text the extractor agent can read."""
    if filename.lower().endswith(".csv"):
        frames = {"Sheet1": pd.read_csv(io.BytesIO(data), dtype=str)}
    else:
        frames = pd.read_excel(io.BytesIO(data), sheet_name=None, dtype=str, header=None)
    pages = []
    for name, df in frames.items():
        df = df.fillna("")
        pages.append(f"[sheet: {name}]\n" + df.to_csv(index=False, header=False))
    return pages


def spreadsheet_rows(filename: str, data: bytes, max_rows: int = 200, max_cols: int = 30) -> list[dict]:
    """Cells as strings, sheet by sheet, so the web screen can show the original (browsers cannot render Excel)."""
    if filename.lower().endswith(".csv"):
        frames = {"Sheet1": pd.read_csv(io.BytesIO(data), dtype=str, header=None)}
    else:
        frames = pd.read_excel(io.BytesIO(data), sheet_name=None, dtype=str, header=None)
    sheets = []
    for name, df in frames.items():
        df = df.fillna("")
        sheets.append({"name": str(name), "rows": df.iloc[:max_rows, :max_cols].values.tolist(),
                       "truncated": df.shape[0] > max_rows or df.shape[1] > max_cols})
    return sheets


# --- Government JSON (GST e-invoice / e-way bill) -------------------------------
def parse_gov_json(data: bytes) -> dict:
    """Map NIC-style e-invoice / e-way bill JSON to our schemas. No AI involved.

    Field names follow the public GST e-invoice (INV-01) and e-way bill JSON layouts in
    simplified form; real payloads have more fields, which are ignored.
    """
    doc = json.loads(data)
    if "ItemList" in doc and "DocDtls" in doc:
        seller, buyer, dd, val = doc["SellerDtls"], doc.get("BuyerDtls", {}), doc["DocDtls"], doc["ValDtls"]
        lines = []
        for item in doc["ItemList"]:
            qty = float(item["Qty"])
            price = float(item["UnitPrice"])
            lines.append(
                {
                    "sku": item.get("PrdCd") or item.get("PrdDesc", ""),
                    "description": item.get("PrdDesc", ""),
                    "hsn": str(item.get("HsnCd", "")),
                    "qty_cartons": qty,
                    "price_per_carton": price,
                    "amount": float(item.get("AssAmt", qty * price)),
                }
            )
        rate = float(doc["ItemList"][0].get("GstRt", 0)) if doc["ItemList"] else 0.0
        tax = float(val.get("IgstVal", 0)) + float(val.get("CgstVal", 0)) + float(val.get("SgstVal", 0))
        data_out = {
            "supplier_name": seller.get("LglNm", ""),
            "supplier_gstin": seller["Gstin"],
            "buyer_gstin": buyer.get("Gstin", ""),
            "invoice_number": dd["No"],
            "invoice_date": _ddmmyyyy_to_iso(dd["Dt"]),
            "po_number": (doc.get("RefDtls", {}).get("PrecDocDtls") or [{}])[0].get("InvNo", "")
            or doc.get("RefDtls", {}).get("PoRef", ""),
            "eway_bill_number": str(doc.get("EwbDtls", {}).get("EwbNo", "") or ""),
            "vehicle_number": doc.get("EwbDtls", {}).get("VehNo", ""),
            "lines": lines,
            "subtotal": float(val["AssVal"]),
            "gst_rate": rate,
            "tax_amount": tax,
            "total": float(val["TotInvVal"]),
            "bank_account_present": bool(doc.get("PayDtls")),
            "confidence": 1.0,
            "uncertain_fields": [],
        }
        return {"doc_type": "invoice", "data": data_out}
    if "ewbNo" in doc:
        items = [
            {
                "hsn": str(i.get("hsnCode", "")),
                "qty_cartons": float(i.get("quantity", 0)),
                "taxable_value": float(i.get("taxableAmount", 0)),
            }
            for i in doc.get("itemList", [])
        ]
        veh = (doc.get("VehiclListDetails") or [{}])[0].get("vehicleNo", "") or doc.get("vehicleNo", "")
        data_out = {
            "eway_bill_number": str(doc["ewbNo"]),
            "generated_date": _ddmmyyyy_to_iso(doc.get("ewayBillDate", "").split(" ")[0]),
            "valid_until": _ddmmyyyy_to_iso(doc.get("validUpto", "").split(" ")[0]),
            "supplier_gstin": doc["fromGstin"],
            "recipient_gstin": doc.get("toGstin", ""),
            "invoice_number": doc.get("docNo", ""),
            "vehicle_number": veh,
            "items": items,
            "total_value": float(doc["totInvValue"]),
            "confidence": 1.0,
            "uncertain_fields": [],
        }
        return {"doc_type": "eway_bill", "data": data_out}
    raise ValueError("JSON is neither a GST e-invoice nor an e-way bill")


def _ddmmyyyy_to_iso(value: str) -> str:
    if not value:
        return ""
    parts = value.replace("-", "/").split("/")
    if len(parts) == 3 and len(parts[2]) == 4:
        return f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
    return value
