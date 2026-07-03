from pathlib import Path

from backend import actions, db, pipeline
from backend.email_parser import parse_eml


def process_one(path: Path) -> int:
    email = parse_eml(path)
    extraction = pipeline.extract(email)
    rules = actions.load_property_rules()
    plan = actions.evaluate(extraction, rules)

    action_subject = action_body = None
    if plan.action_type == "draft_reply":
        draft = actions.draft_reply(extraction, plan)
        action_subject, action_body = draft.subject, draft.body
    elif plan.action_type == "sync_line_items":
        synced = actions.sync_to_accounting(extraction, path.name)
        action_subject = "Synced to accounting export"
        action_body = (
            f"{synced} line item(s) appended to data/accounting_export.csv for "
            f"accounts-payable review (simulated push to accounting software)."
            if synced
            else "No line items were extracted, so nothing was synced."
        )

    record = {
        "source_file": path.name,
        "received_at": email.date_iso,
        "sender_name": extraction.sender_name or email.sender_name,
        "sender_email": extraction.sender_email or email.sender_email,
        "subject": email.subject,
        "request_type": extraction.request_type,
        "confidence": extraction.confidence,
        "property_address": extraction.property_address,
        "summary": extraction.summary,
        "extraction_json": extraction.model_dump_json(indent=2),
        "action_type": plan.action_type,
        "action_subject": action_subject,
        "action_body": action_body,
        "flags": plan.flags,
        "raw_email_text": email.raw_display,
    }
    return db.insert_intake(record)


def process_inbox() -> list[int]:
    new_ids = []
    for path in pipeline.list_fixture_files():
        if db.source_already_processed(path.name):
            continue
        new_ids.append(process_one(path))
    return new_ids
