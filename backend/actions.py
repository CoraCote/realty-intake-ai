import csv
import json
import re
from datetime import datetime, timezone

from backend.config import ACCOUNTING_EXPORT_PATH, BROKERAGE_NAME, CLAUDE_MODEL, PROPERTY_RULES_PATH
from backend.pipeline import get_client
from backend.schemas import ActionDraft, ActionPlan, ExtractionResult

_ABBREV = {
    "st": "street",
    "ave": "avenue",
    "ct": "court",
    "ln": "lane",
    "dr": "drive",
    "rd": "road",
    "blvd": "boulevard",
}


def _normalize(address: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", address.lower())
    return [_ABBREV.get(w, w) for w in words]


def load_property_rules() -> list[dict]:
    with open(PROPERTY_RULES_PATH) as f:
        return json.load(f)


def find_property(rules: list[dict], address: str | None) -> dict | None:
    """Matches on street number + at least one shared street-name word, so
    'Suite/Unit', city, state, and zip differences (or omissions) don't block
    a match — real inbound addresses are rarely formatted identically to the
    listing record."""
    if not address:
        return None
    tokens = _normalize(address)
    if not tokens or not tokens[0].isdigit():
        return None
    number, name_tokens = tokens[0], set(tokens[1:])
    for rule in rules:
        rtoks = _normalize(rule["address"])
        if rtoks and rtoks[0] == number and name_tokens & set(rtoks[1:]):
            return rule
    return None


def evaluate(extraction: ExtractionResult, rules: list[dict]) -> ActionPlan:
    property_ = find_property(rules, extraction.property_address)
    flags: list[str] = []
    action_type = "flag_for_review"

    if extraction.request_type == "showing_request":
        if not property_:
            flags.append(f"No listing found matching address '{extraction.property_address}'")
        elif property_["type"] != "rental":
            flags.append("Matched address is a for-sale listing, not a rental — inquiry may be misrouted")
        action_type = "flag_for_review" if flags else "draft_reply"

    elif extraction.request_type == "rental_application":
        if not property_:
            flags.append("No matching rental listing found for this application")
        else:
            rent = property_["rent"]
            min_income = rent * property_.get("min_income_multiplier", 3)
            if extraction.monthly_income is None:
                flags.append("Monthly income not found in the application or attachments")
            elif extraction.monthly_income < min_income:
                flags.append(
                    f"Stated income ${extraction.monthly_income:,.0f}/mo is below the required "
                    f"${min_income:,.0f}/mo ({property_.get('min_income_multiplier', 3)}x rent of ${rent:,.0f})"
                )
            if not extraction.id_document_present:
                flags.append("No government ID attached")
            if not extraction.income_document_present:
                flags.append("No income verification document (pay stub) attached")
        action_type = "flag_for_review" if flags else "draft_reply"

    elif extraction.request_type == "purchase_offer":
        if not property_:
            flags.append("No matching for-sale listing found for this offer")
        else:
            listing_price = property_["listing_price"]
            min_pct = property_.get("min_acceptable_offer_pct", 0.95)
            min_offer = listing_price * min_pct
            if extraction.offer_price is None:
                flags.append("Offer price could not be extracted from the document")
            elif extraction.offer_price < min_offer:
                flags.append(
                    f"Offer ${extraction.offer_price:,.0f} is below the ${min_offer:,.0f} minimum "
                    f"acceptable threshold ({min_pct * 100:.0f}% of list price ${listing_price:,.0f})"
                )
            if not extraction.financing_type:
                flags.append("Financing type not specified in the offer")
            if not extraction.closing_date:
                flags.append("Closing date not specified in the offer")
        action_type = "flag_for_review" if flags else "draft_reply"

    elif extraction.request_type == "vendor_invoice":
        action_type = "sync_line_items"
        if extraction.invoice_total is None:
            flags.append("Could not extract an invoice total")
        if not extraction.line_items:
            flags.append("No line items could be extracted")
        if not flags:
            flags.append("Routed to accounts payable for approval — invoices are never auto-approved")

    else:
        flags.append("Could not classify this email into a known workflow — needs manual triage")
        action_type = "flag_for_review"

    if extraction.confidence < 0.6:
        flags.append(f"Low extraction confidence ({extraction.confidence:.0%}) — verify fields before acting")
        action_type = "flag_for_review"

    return ActionPlan(action_type=action_type, matched_property=property_, flags=flags)


DRAFT_SYSTEM = f"""You draft outbound email replies on behalf of {BROKERAGE_NAME}'s leasing and \
sales team. Write in a professional, warm, concise tone. Use only the figures and facts given in \
the context below — never invent pricing, dates, policies, or names that are not provided. Keep \
the body under 180 words. Sign off as "The {BROKERAGE_NAME} Team"."""


def draft_reply(extraction: ExtractionResult, plan: ActionPlan) -> ActionDraft:
    client = get_client()
    context = {
        "request_type": extraction.request_type,
        "sender_name": extraction.sender_name,
        "property_address": extraction.property_address,
        "matched_property": plan.matched_property,
        "extracted_fields": extraction.model_dump(exclude={"summary", "missing_fields"}),
    }
    response = client.messages.parse(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=DRAFT_SYSTEM,
        output_config={"effort": "medium"},
        messages=[
            {
                "role": "user",
                "content": (
                    "Draft the reply email for this intake record. Context (JSON):\n\n"
                    f"{json.dumps(context, indent=2, default=str)}"
                ),
            }
        ],
        output_format=ActionDraft,
    )
    return response.parsed_output


def sync_to_accounting(extraction: ExtractionResult, source_file: str) -> int:
    if not extraction.line_items:
        return 0
    ACCOUNTING_EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    is_new = not ACCOUNTING_EXPORT_PATH.exists()
    with open(ACCOUNTING_EXPORT_PATH, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(
                [
                    "synced_at",
                    "source_file",
                    "vendor_name",
                    "invoice_number",
                    "property_address",
                    "description",
                    "quantity",
                    "unit_price",
                    "total",
                ]
            )
        for item in extraction.line_items:
            writer.writerow(
                [
                    datetime.now(timezone.utc).isoformat(),
                    source_file,
                    extraction.vendor_name or "",
                    extraction.invoice_number or "",
                    extraction.property_address or "",
                    item.description,
                    item.quantity if item.quantity is not None else "",
                    item.unit_price if item.unit_price is not None else "",
                    item.total if item.total is not None else "",
                ]
            )
    return len(extraction.line_items)
