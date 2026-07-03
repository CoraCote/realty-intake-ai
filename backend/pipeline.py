import base64
import io
from pathlib import Path

import anthropic
import openpyxl

from backend.config import ANTHROPIC_API_KEY, CLAUDE_MODEL, FIXTURES_DIR
from backend.email_parser import Attachment, EmailData, parse_eml
from backend.schemas import ExtractionResult

_client = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


SYSTEM_PROMPT = """You are the intake assistant for Austin Skyline Realty, a residential \
real estate brokerage and property management company in Austin, TX. You process inbound \
emails and their attachments (PDFs, scanned images, spreadsheets) and extract structured data \
for the back office.

Classify every email into exactly one request_type:
- showing_request: a prospective tenant or buyer asking about availability, price, pet policy, \
or requesting a tour, with no formal application or offer attached.
- rental_application: a rental application, whether or not it is complete, typically mentioning \
income and/or including ID or pay stub attachments.
- purchase_offer: a purchase offer, letter of intent, or purchase agreement for a for-sale property.
- vendor_invoice: an invoice or bill from a contractor or vendor for maintenance or services.
- general_inquiry: a legitimate real-estate-related message that doesn't fit the categories above.
- unclassified: anything unrelated to real estate business (spam, newsletters, unrelated offers).

Rules:
- Extract only what is directly stated in the email body or attachments. Never guess or infer a \
value that isn't present.
- Leave a field null when it is not present.
- Populate missing_fields with the names of fields you would normally expect for this \
request_type but could not find (e.g. "monthly_income", "closing_date").
- property_address should be copied as written in the source (street, and city/state/zip if given) \
- do not invent or complete an address.
- id_document_present / income_document_present should reflect whether an attachment of that kind \
was actually included, not whether the applicant merely mentions having one.
- confidence (0-1) should reflect your overall certainty in both the classification and the \
extracted fields. Lower it for ambiguous, low-quality, or attachment-light messages.
- For vendor_invoice emails, extract every line item you can find with its description, quantity, \
unit price, and line total, plus the invoice's grand total."""


def _xlsx_to_text(data: bytes, filename: str) -> str:
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    lines = [f"Attachment: {filename} (spreadsheet, parsed as table)"]
    for sheet in wb.worksheets:
        lines.append(f"-- sheet: {sheet.title} --")
        for row in sheet.iter_rows(values_only=True):
            cells = ["" if c is None else str(c) for c in row]
            if any(cells):
                lines.append(" | ".join(cells))
    return "\n".join(lines)


_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}
_SPREADSHEET_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
}


def _attachment_to_blocks(att: Attachment) -> list[dict]:
    if att.content_type == "application/pdf":
        return [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": base64.standard_b64encode(att.data).decode("utf-8"),
                },
                "title": att.filename,
            }
        ]
    if att.content_type in _IMAGE_TYPES:
        return [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": att.content_type,
                    "data": base64.standard_b64encode(att.data).decode("utf-8"),
                },
            }
        ]
    if att.content_type in _SPREADSHEET_TYPES:
        return [{"type": "text", "text": _xlsx_to_text(att.data, att.filename)}]
    return [
        {
            "type": "text",
            "text": f"Attachment: {att.filename} ({att.content_type}) — "
            f"binary content not shown, not directly parsable by this pipeline.",
        }
    ]


def build_extraction_content(email: EmailData) -> list[dict]:
    header = (
        f"From: {email.sender_name} <{email.sender_email}>\n"
        f"Subject: {email.subject}\n"
        f"Date: {email.date_iso or 'unknown'}\n\n"
        f"{email.body_text}"
    )
    content: list[dict] = [{"type": "text", "text": header}]
    for att in email.attachments:
        content.extend(_attachment_to_blocks(att))
    return content


def extract(email: EmailData) -> ExtractionResult:
    client = get_client()
    response = client.messages.parse(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        output_config={"effort": "medium"},
        messages=[{"role": "user", "content": build_extraction_content(email)}],
        output_format=ExtractionResult,
    )
    return response.parsed_output


def process_fixture(filename: str) -> tuple[EmailData, ExtractionResult]:
    email = parse_eml(FIXTURES_DIR / filename)
    result = extract(email)
    return email, result


def list_fixture_files() -> list[Path]:
    if not FIXTURES_DIR.exists():
        return []
    return sorted(FIXTURES_DIR.glob("*.eml"))
