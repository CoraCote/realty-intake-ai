from typing import List, Literal, Optional

from pydantic import BaseModel, Field

RequestType = Literal[
    "showing_request",
    "rental_application",
    "purchase_offer",
    "vendor_invoice",
    "general_inquiry",
    "unclassified",
]

ActionType = Literal["draft_reply", "flag_for_review", "sync_line_items"]


class LineItem(BaseModel):
    description: str
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    total: Optional[float] = None


class ExtractionResult(BaseModel):
    request_type: RequestType = Field(
        description="Which intake workflow this email belongs to"
    )
    confidence: float = Field(
        description="0-1 confidence in the classification and extraction as a whole"
    )
    summary: str = Field(description="One or two sentence plain-English summary")

    property_address: Optional[str] = None
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None
    sender_phone: Optional[str] = None

    desired_move_in_date: Optional[str] = None

    offer_price: Optional[float] = None
    financing_type: Optional[str] = None
    earnest_money: Optional[float] = None
    closing_date: Optional[str] = None
    contingencies: Optional[List[str]] = None

    monthly_income: Optional[float] = None
    employer: Optional[str] = None
    id_document_present: Optional[bool] = None
    income_document_present: Optional[bool] = None

    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_total: Optional[float] = None
    line_items: Optional[List[LineItem]] = None

    missing_fields: Optional[List[str]] = None


class ActionDraft(BaseModel):
    subject: str
    body: str


class ActionPlan(BaseModel):
    action_type: ActionType
    matched_property: Optional[dict] = None
    flags: List[str] = Field(default_factory=list)
