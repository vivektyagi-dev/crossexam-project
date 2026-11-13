"""The fixed forms each agent must fill. One schema per document family.

Amounts are floats in the AI-facing schema (models handle them reliably); every
calculation on them is done with Decimal in app/rules.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class DocType(StrEnum):
    invoice = "invoice"
    packing_list = "packing_list"
    lorry_receipt = "lorry_receipt"  # bill of lading / lorry receipt
    eway_bill = "eway_bill"
    quality_certificate = "quality_certificate"
    credit_note = "credit_note"
    debit_note = "debit_note"
    other = "other"


DOC_FAMILY = {
    DocType.invoice: "invoice",
    DocType.packing_list: "shipping",
    DocType.lorry_receipt: "shipping",
    DocType.eway_bill: "shipping",
    DocType.quality_certificate: "quality",
    DocType.credit_note: "adjustment",
    DocType.debit_note: "adjustment",
}


class _Base(BaseModel):
    confidence: float = Field(
        ge=0, le=1, description="Your overall confidence that every field is correct (0-1). Be honest."
    )
    uncertain_fields: list[str] = Field(
        default_factory=list, description="Names of fields you could not read clearly."
    )


# --- classifier ---------------------------------------------------------------
class Segment(BaseModel):
    doc_type: DocType
    start_page: int = Field(ge=1, description="First page (1-based) of this document")
    end_page: int = Field(ge=1, description="Last page (1-based, inclusive)")
    reason: str = Field(description="Short reason, e.g. 'title says TAX INVOICE'")


class Classification(BaseModel):
    segments: list[Segment] = Field(description="Every page must belong to exactly one segment, in order.")
    confidence: float = Field(ge=0, le=1)


# --- invoice --------------------------------------------------------------------
class InvoiceLine(BaseModel):
    sku: str = Field(description="Item code / SKU exactly as printed")
    description: str = ""
    hsn: str = ""
    qty_cartons: float = Field(description="Quantity in cartons/cases")
    price_per_carton: float
    amount: float = Field(description="Line amount before tax")


class InvoiceData(_Base):
    supplier_name: str
    supplier_gstin: str = Field(description="15-character GSTIN of the seller")
    buyer_gstin: str = ""
    invoice_number: str
    invoice_date: str = Field(description="ISO date YYYY-MM-DD")
    po_number: str = Field(default="", description="Buyer purchase order number, e.g. PO-12345")
    eway_bill_number: str = ""
    vehicle_number: str = ""
    lines: list[InvoiceLine]
    subtotal: float
    gst_rate: float = Field(description="GST rate in percent, e.g. 18")
    tax_amount: float
    total: float
    bank_account_present: bool = Field(default=False, description="True if bank details are printed")


# --- shipping documents ----------------------------------------------------------
class PackingLine(BaseModel):
    sku: str
    qty_cartons: float
    batch_number: str = ""
    gross_weight_kg: float = 0


class PackingListData(_Base):
    supplier_gstin: str = ""
    packing_list_number: str
    invoice_number: str = ""
    po_number: str = ""
    lines: list[PackingLine]
    total_cartons: float
    total_weight_kg: float = 0


class LorryReceiptData(_Base):
    transporter_name: str
    lr_number: str = Field(description="Lorry receipt / bill of lading number")
    lr_date: str = ""
    vehicle_number: str
    consignor_gstin: str = ""
    consignee_gstin: str = ""
    invoice_number: str = ""
    packages: float = Field(description="Number of packages/cartons carried")
    weight_kg: float = 0


class EwayItem(BaseModel):
    hsn: str
    qty_cartons: float = 0
    taxable_value: float = 0


class EwayBillData(_Base):
    eway_bill_number: str = Field(description="12-digit e-way bill number")
    generated_date: str = ""
    valid_until: str = ""
    supplier_gstin: str
    recipient_gstin: str = ""
    invoice_number: str = ""
    vehicle_number: str = ""
    items: list[EwayItem] = Field(default_factory=list)
    total_value: float = Field(description="Total invoice value including tax")


# --- quality ---------------------------------------------------------------------
class QualityCertificateData(_Base):
    certificate_number: str
    supplier_gstin: str = ""
    sku: str = ""
    batch_number: str
    manufacture_date: str = ""
    expiry_date: str = Field(description="ISO date YYYY-MM-DD")
    result: str = Field(description="PASS or FAIL")


# --- adjustments -----------------------------------------------------------------
class AdjustmentNoteData(_Base):
    note_number: str
    note_type: str = Field(description="credit or debit")
    supplier_gstin: str
    original_invoice_number: str
    amount: float = Field(description="Total adjustment including tax")
    reason: str = ""


SCHEMA_BY_TYPE: dict[DocType, type[_Base]] = {
    DocType.invoice: InvoiceData,
    DocType.packing_list: PackingListData,
    DocType.lorry_receipt: LorryReceiptData,
    DocType.eway_bill: EwayBillData,
    DocType.quality_certificate: QualityCertificateData,
    DocType.credit_note: AdjustmentNoteData,
    DocType.debit_note: AdjustmentNoteData,
}


# --- reconciliation / exceptions -------------------------------------------------
class ReconciliationReport(BaseModel):
    decision: str = Field(description="'clean' if nothing needs a person, otherwise 'exception'")
    summary: str = Field(description="Two or three plain-English sentences a finance clerk understands")
    linked_document_ids: list[str] = Field(default_factory=list, description="Orphan documents you linked")


class SupervisorDecision(BaseModel):
    route: str = Field(description="'auto_approve', 'investigate' or 'human_review'")
    summary: str
    confidence: float = Field(ge=0, le=1)


class ExceptionFinding(BaseModel):
    finding: str = Field(description="What is wrong, in plain words, citing the documents")
    root_cause: str = Field(description="Most likely cause, e.g. 'short loading at supplier'")
    recommended_action: str
    similar_case_ids: list[int] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
