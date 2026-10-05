from __future__ import annotations

from enum import Enum
from typing import Optional, Generic, TypeVar
from pydantic import BaseModel, Field, ConfigDict


class DocumentType(str, Enum):
    PURCHASE_ORDER = "purchase_order"
    INVOICE = "invoice"
    PAYMENT_REQUEST = "payment_request"
    UNKNOWN = "unknown"


class Evidence(BaseModel):
    """Evidence supporting one extracted value."""
    page: Optional[int] = Field(default=None, description="1-based page number")
    quote: Optional[str] = Field(default=None, description="Exact or near-exact source text")
    confidence: Optional[float] = Field(default=None, ge=0, le=1)


T = TypeVar('T')


class ExtractedField(BaseModel, Generic[T]):
    """Value + provenance. Missing/unknown values must remain None."""
    value: Optional[T] = None
    evidence: list[Evidence] = Field(default_factory=list)


class Party(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None


class LineItem(BaseModel):
    sku: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    line_total: Optional[float] = None


class BankDetails(BaseModel):
    account_name: Optional[str] = None
    account_number: Optional[str] = None
    bank_name: Optional[str] = None


class ApprovalStep(BaseModel):
    role: Optional[str] = None
    person: Optional[str] = None
    status: Optional[str] = None
    date: Optional[str] = None


class CommonDocumentData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: DocumentType
    document_number: Optional[str] = None
    document_date: Optional[str] = Field(default=None, description="ISO date YYYY-MM-DD when unambiguous")
    po_number: Optional[str] = None
    invoice_number: Optional[str] = None
    buyer: Optional[Party] = None
    seller: Optional[Party] = None
    currency: Optional[str] = None
    items: list[LineItem] = Field(default_factory=list)
    subtotal: Optional[float] = None
    vat_amount: Optional[float] = None
    total_amount: Optional[float] = None
    payment_terms: Optional[str] = None
    due_date: Optional[str] = None
    bank_details: Optional[BankDetails] = None
    delivery_address: Optional[str] = None
    amount_already_paid: Optional[float] = None
    requested_payment_amount: Optional[float] = None
    desired_payment_date: Optional[str] = None
    requester_name: Optional[str] = None
    requester_department: Optional[str] = None
    approvals: list[ApprovalStep] = Field(default_factory=list)
    attachments: list[str] = Field(default_factory=list)
    # Provenance map: field name -> evidence entries
    field_evidence: dict[str, list[Evidence]] = Field(default_factory=dict)
    extraction_notes: list[str] = Field(default_factory=list)


class PurchaseOrderData(CommonDocumentData):
    document_type: DocumentType = DocumentType.PURCHASE_ORDER


class InvoiceData(CommonDocumentData):
    document_type: DocumentType = DocumentType.INVOICE


class PaymentRequestData(CommonDocumentData):
    document_type: DocumentType = DocumentType.PAYMENT_REQUEST
