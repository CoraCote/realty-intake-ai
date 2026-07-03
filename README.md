# Realty Intake AI

**Email/document intake → AI extraction → structured record → automated action, for residential real estate.**

A brokerage/property-management inbox receives rental inquiries, rental applications (with scanned IDs and pay stubs), purchase offers (PDF letters of intent, purchase agreement summaries), and vendor invoices (Excel). This pipeline reads each email and its attachments, extracts structured data with Claude, applies pricing/eligibility rules, and takes the appropriate next action automatically:

- **Showing request** → drafts an availability/pricing reply using the property's real rent, deposit, and showing link
- **Rental application** → checks income against the 3x-rent rule and required documents, then either drafts an acknowledgement or flags it with the specific reason
- **Purchase offer** → compares the offer to the listing's minimum-acceptable-offer threshold and flags anything below it, missing financing, or missing a closing date
- **Vendor invoice** → parses line items from an attached spreadsheet and pushes them to a CSV "accounting export" for AP approval (never auto-approved)
- **Spam / off-topic / low-confidence** → flagged for human review instead of guessing

All of this runs against a **simulated inbox** of 9 realistic `.eml` fixtures (different senders, layouts, and file types — including a forwarded/quoted-chain email and two purchase-offer PDFs built from two different templates) so the whole thing runs end-to-end with zero external credentials beyond an Anthropic API key.

## Architecture

```
fixtures/sample_emails/*.eml  (or a real IMAP/Gmail inbox — see "Going to production")
              │
              ▼
   backend/email_parser.py   — parses .eml, splits body text vs. attachments
              │
              ▼
   backend/pipeline.py       — builds Claude content blocks:
                                 PDF attachments  -> native "document" blocks
                                 image attachments -> native "image" blocks
                                 .xlsx attachments -> parsed to text table (openpyxl)
              │
              ▼
   Claude (claude-opus-4-8, structured output via output_config.format)
   -> ExtractionResult (Pydantic): request_type, confidence, every field
      the model could find, missing_fields for what it couldn't
              │
              ▼
   backend/actions.py        — rules engine: matches the extracted address
                                against data/property_rules.json, checks
                                income/offer thresholds, decides:
                                  draft_reply | flag_for_review | sync_line_items
              │
              ├─ draft_reply ──────► second Claude call drafts the actual
              │                      subject/body using only the verified
              │                      figures (never invents pricing)
              │
              ├─ sync_line_items ──► appends parsed invoice line items to
              │                      data/accounting_export.csv (stand-in for
              │                      a QuickBooks/Xero export)
              │
              └─ flag_for_review ──► stored with the specific, human-readable
                                     reasons (missing doc, below threshold,
                                     low confidence, unmatched address...)
              │
              ▼
   SQLite (data/intake.db)   — one row per email: raw text, full extraction
                                JSON, action taken, flags
              │
              ▼
   FastAPI + Jinja dashboard — review queue: table of every processed email,
                                confidence, action badge, and a detail view
                                per record (raw email / extracted JSON / draft
                                or flags side by side)
```

## Tech stack

| Layer | Choice |
|---|---|
| Extraction / drafting | Claude (`claude-opus-4-8`) via the official `anthropic` Python SDK, using native PDF + image input and `output_config.format` structured outputs (no OCR step, no separate vision API) |
| Spreadsheet input | `openpyxl` — `.xlsx` attachments are parsed to a text table and included as extra context alongside the email body |
| Email parsing | Python stdlib `email` package (handles multipart, attachments, forwarded/quoted chains) |
| Backend / API | FastAPI |
| Structured data store | SQLite (stdlib `sqlite3`) |
| Review UI | Jinja2 + hand-rolled CSS (no JS framework, no external CDN — renders identically offline) |
| Validation | Pydantic v2 (`ExtractionResult`, `ActionDraft` schemas passed straight into `output_config.format`) |
| Fixture generation | `reportlab` (PDF), `Pillow` (synthetic ID image), `openpyxl` (invoice spreadsheet) |

## Setup

```powershell
cd realty-intake-ai
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

copy .env.example .env
# then edit .env and set ANTHROPIC_API_KEY=sk-ant-...

python fixtures\generate_fixtures.py   # builds the sample inbox (already generated in this repo)
uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000, click **Process Inbox**, then click into any row to see the raw email next to the extracted JSON and the drafted reply or the review flags.

For a terminal-only run (good for a recorded demo):

```powershell
python run_pipeline.py
```

## Sample inbox (`fixtures/sample_emails/`)

| File | Type | What it tests |
|---|---|---|
| `rental_inquiry_1.eml` | showing_request | Plain-text inquiry, no attachment |
| `rental_inquiry_2.eml` | showing_request | Messy forwarded/quoted-chain formatting |
| `rental_application_1.eml` | rental_application | PNG "ID" + PDF pay stub, income passes the 3x-rent check → auto-drafted |
| `rental_application_2.eml` | rental_application | Income too low + missing pay stub → flagged with both specific reasons |
| `purchase_offer_1.eml` | purchase_offer | PDF Letter of Intent, offer above threshold → auto-drafted |
| `purchase_offer_2.eml` | purchase_offer | **Different PDF template/layout**, offer below threshold → flagged |
| `vendor_invoice_1.eml` | vendor_invoice | `.xlsx` invoice with line items → parsed and synced to `accounting_export.csv` |
| `spam_general_1.eml` | unclassified | Off-topic marketing spam → flagged, not misfiled as a real request |
| `general_inquiry_1.eml` | general_inquiry | Legitimate but non-actionable question → flagged for a human reply |

Regenerate anytime with `python fixtures/generate_fixtures.py`. All names, addresses, and documents are synthetic demo data.

## Going to production

This repo intentionally ships with a simulated inbox so it runs anywhere with just an API key. The parts that would change for a live deployment:

- **Trigger**: swap `fixtures/sample_emails/*.eml` for an IMAP/Gmail API poller that drops new messages into the same `EmailData` shape `backend/email_parser.py` already produces — the extraction/action pipeline downstream doesn't change.
- **Sending**: `draft_reply` currently stores the subject/body for human review in the dashboard; wiring it to actually send (Gmail API / SMTP) is a one-function change, gated behind an explicit "send" click rather than fully autonomous sending.
- **Accounting sync**: `sync_to_accounting()` writes to a local CSV as a stand-in; swapping in a QuickBooks/Xero API call is a drop-in replacement for that one function.
- **Multi-tenant**: `data/property_rules.json` would move to a per-brokerage database table.

---

## Notes for reviewers

- Every name, address, dollar figure, and attached document in `fixtures/` is synthetic, generated by `fixtures/generate_fixtures.py` for this demo — nothing here is a real person, property, or financial document.
- The two purchase-offer PDFs and the rental-application ID/pay-stub attachments are deliberately built with different layouts/templates to demonstrate the pipeline handling inconsistent input formats rather than one fixed template.
- No mock mode: extraction and drafting always call the real Claude API (`ANTHROPIC_API_KEY` required) — nothing here fakes a model response.
