"""Generates a realistic, messy sample inbox for the demo: plain-text inquiries,
a forwarded/quoted-chain email, rental applications with scanned-ID + pay-stub
attachments, purchase offers in two different PDF templates, a vendor invoice
as an Excel attachment, and one piece of off-topic spam to exercise the
"unclassified / flag for review" path. Run with: python fixtures/generate_fixtures.py
"""

import io
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path

import openpyxl
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

OUT_DIR = Path(__file__).resolve().parent / "sample_emails"
OUT_DIR.mkdir(parents=True, exist_ok=True)

NOW = datetime(2026, 7, 2, 9, 0, tzinfo=timezone.utc)


def _dt(days_ago: float, hour: int, minute: int) -> datetime:
    d = NOW - timedelta(days=days_ago)
    return d.replace(hour=hour, minute=minute, second=0, microsecond=0)


def make_email(
    from_name: str,
    from_addr: str,
    subject: str,
    date: datetime,
    body: str,
    attachments: list[tuple[str, str, bytes]] | None = None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = f"{from_name} <{from_addr}>"
    msg["To"] = "leasing@austinskylinerealty.com"
    msg["Subject"] = subject
    msg["Date"] = format_datetime(date)
    msg.set_content(body)
    for filename, mime_type, data in attachments or []:
        maintype, subtype = mime_type.split("/", 1)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
    return msg


def save(msg: EmailMessage, filename: str) -> None:
    with open(OUT_DIR / filename, "wb") as f:
        f.write(bytes(msg))
    print(f"wrote {filename}")


def make_pdf(title: str, lines: list[str]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    width, height = LETTER
    y = height - 72
    c.setFont("Helvetica-Bold", 15)
    c.drawString(72, y, title)
    y -= 30
    c.setFont("Helvetica", 10.5)
    for line in lines:
        if y < 72:
            c.showPage()
            y = height - 72
            c.setFont("Helvetica", 10.5)
        if line.startswith("## "):
            y -= 6
            c.setFont("Helvetica-Bold", 11.5)
            c.drawString(72, y, line[3:])
            c.setFont("Helvetica", 10.5)
            y -= 18
        else:
            c.drawString(72, y, line)
            y -= 16
    c.showPage()
    c.save()
    return buf.getvalue()


def make_id_card_png(name: str, dob: str, id_number: str) -> bytes:
    img = Image.new("RGB", (600, 380), "#f2efe8")
    draw = ImageDraw.Draw(img)
    draw.rectangle([8, 8, 591, 371], outline="#a3552e", width=6)
    try:
        font_bold = ImageFont.truetype("arialbd.ttf", 22)
        font = ImageFont.truetype("arial.ttf", 18)
        font_small = ImageFont.truetype("arial.ttf", 13)
    except OSError:
        font_bold = ImageFont.load_default()
        font = ImageFont.load_default()
        font_small = ImageFont.load_default()
    draw.text((30, 30), "STATE OF TEXAS — SPECIMEN / DEMO ONLY", font=font_small, fill="#a3401b")
    draw.text((30, 60), "NOT A VALID GOVERNMENT DOCUMENT", font=font_small, fill="#a3401b")
    draw.rectangle([30, 100, 200, 250], outline="#666", width=2)
    draw.text((60, 165), "PHOTO", font=font, fill="#999")
    draw.text((230, 105), "NAME", font=font_small, fill="#666")
    draw.text((230, 122), name, font=font_bold, fill="#232019")
    draw.text((230, 165), "DATE OF BIRTH", font=font_small, fill="#666")
    draw.text((230, 182), dob, font=font, fill="#232019")
    draw.text((230, 225), "ID NUMBER", font=font_small, fill="#666")
    draw.text((230, 242), id_number, font=font, fill="#232019")
    draw.text((30, 330), "This is synthetic demo data generated for a software test fixture.", font=font_small, fill="#999")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_paystub_pdf(employer: str, name: str, gross_monthly: float, period: str) -> bytes:
    net = gross_monthly * 0.76
    lines = [
        f"Employee: {name}",
        f"Pay Period: {period}",
        "## Earnings",
        f"Gross Pay (Monthly): ${gross_monthly:,.2f}",
        f"Federal & State Withholding: ${gross_monthly * 0.18:,.2f}",
        f"FICA: ${gross_monthly * 0.06:,.2f}",
        f"Net Pay: ${net:,.2f}",
        "",
        "This is a demo/specimen document generated for a software test fixture.",
    ]
    return make_pdf(f"{employer} — Earnings Statement", lines)


def make_invoice_xlsx(vendor: str, invoice_number: str, property_address: str, items: list[tuple[str, float, float]]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Invoice"
    ws.append([vendor])
    ws.append(["Invoice #", invoice_number])
    ws.append(["Property", property_address])
    ws.append(["Date", NOW.strftime("%Y-%m-%d")])
    ws.append([])
    ws.append(["Description", "Qty", "Unit Price", "Total"])
    total = 0.0
    for desc, qty, unit_price in items:
        line_total = round(qty * unit_price, 2)
        total += line_total
        ws.append([desc, qty, unit_price, line_total])
    ws.append([])
    ws.append(["", "", "TOTAL DUE", round(total, 2)])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build():
    # 1. Casual showing-request email, no attachment
    save(
        make_email(
            "Marcus Webb", "marcus.webb82@gmail.com",
            "Is 123 Oak Street still available?",
            _dt(4, 14, 22),
            "Hi there,\n\n"
            "I saw the listing for 123 Oak Street Unit 2B on Zillow. Is it still available? "
            "What's the security deposit, and could I come see it this weekend?\n\n"
            "Thanks,\nMarcus\n(512) 555-0142",
        ),
        "rental_inquiry_1.eml",
    )

    # 2. Messy forwarded/quoted-chain showing-request
    save(
        make_email(
            "Priya Nandakumar", "p.nandakumar@outlook.com",
            "RE: 456 Maple Ave rental",
            _dt(3, 9, 47),
            "Hi again,\n\n"
            "Sorry for the slow reply, been swamped at work. A couple more questions before I apply -- "
            "do you allow pets, and what's the earliest move-in date you can do? Budget-wise we're "
            "hoping to keep it under $1900/mo so 456 Maple Avenue looked good.\n\n"
            "Best,\nPriya\n\n"
            "On Wed, Jun 24, 2026 at 3:12 PM Leasing Team <leasing@austinskylinerealty.com> wrote:\n"
            "> Thanks for reaching out! Let us know if you have any other questions about the Maple Ave unit.\n"
            ">\n"
            "> On Wed, Jun 24, 2026, Priya Nandakumar wrote:\n"
            "> > Hi, is 456 Maple Ave still on the market?\n",
        ),
        "rental_inquiry_2.eml",
    )

    # 3. Rental application that PASSES (123 Oak St, rent 2200 -> needs 6600/mo, income 7500)
    save(
        make_email(
            "Jordan Alvarez", "jordan.alvarez91@yahoo.com",
            "Rental application - 123 Oak Street Unit 2B",
            _dt(2, 11, 5),
            "Hello,\n\n"
            "Please find my application info below for 123 Oak Street Unit 2B. I've attached my ID "
            "and most recent pay stub. I work at Meridian Health Systems and would like to move in "
            "August 1st if possible.\n\n"
            "Name: Jordan Alvarez\nMonthly income: $7,500\nEmployer: Meridian Health Systems\n\n"
            "Let me know if you need anything else.\n\nJordan",
            attachments=[
                ("jordan_alvarez_id.png", "image/png", make_id_card_png("JORDAN ALVAREZ", "03/14/1994", "TX-88213456")),
                ("paystub_june2026.pdf", "application/pdf", make_paystub_pdf("Meridian Health Systems", "Jordan Alvarez", 7500, "06/01/2026 - 06/30/2026")),
            ],
        ),
        "rental_application_1.eml",
    )

    # 4. Rental application that FAILS (456 Maple Ave, rent 1800 -> needs 5400/mo, income only 2900, no paystub)
    save(
        make_email(
            "Casey Fitzgerald", "caseyf.tx@gmail.com",
            "application for the maple ave place",
            _dt(1, 16, 40),
            "hi! wanted to apply for 456 Maple Avenue. i just started a new part-time job at a "
            "coffee shop downtown, make about $2,900/month right now but picking up more shifts soon. "
            "attached my id. can send more docs if needed\n\nCasey",
            attachments=[
                ("casey_id.png", "image/png", make_id_card_png("CASEY FITZGERALD", "11/02/1999", "TX-77410982")),
            ],
        ),
        "rental_application_2.eml",
    )

    # 5. Purchase offer that PASSES (789 Birchwood Lane, list 615000, min 95% = 584250, offer 600000)
    loi_lines = [
        "Property: 789 Birchwood Lane, Austin, TX 78704",
        "Buyer: Renee & Marcus Okafor",
        "Buyer's Agent: Lila Chen, Compass Realty",
        "## Offer Terms",
        "Purchase Price: $600,000.00",
        "Financing: Cash",
        "Earnest Money Deposit: $6,000.00",
        "Proposed Closing Date: 08/01/2026",
        "## Contingencies",
        "- Home inspection (10 days)",
        "- Clear title",
        "",
        "This letter of intent is submitted in good faith and is non-binding until a formal",
        "purchase agreement is executed by both parties.",
    ]
    save(
        make_email(
            "Lila Chen", "lila.chen@compassrealty-demo.com",
            "Letter of Intent - 789 Birchwood Lane",
            _dt(2, 13, 15),
            "Hi team,\n\nPlease see the attached Letter of Intent on behalf of my buyers for "
            "789 Birchwood Lane. They're prepared to move quickly - let me know if you need "
            "anything further to present this to the seller.\n\nBest,\nLila Chen\nCompass Realty",
            attachments=[("LOI_789_Birchwood.pdf", "application/pdf", make_pdf("Letter of Intent to Purchase", loi_lines))],
        ),
        "purchase_offer_1.eml",
    )

    # 6. Purchase offer that FAILS - different PDF template/layout (22 Sunset Ridge Ct, list 449000, min 97% = 435530, offer 410000)
    pa_lines = [
        "Subject Property:  22 Sunset Ridge Court, Austin, TX 78745",
        "Prepared By:       Buyer's Agent — Trent Okafor, HomeFirst Brokers",
        "Date Prepared:     " + NOW.strftime("%m/%d/%Y"),
        "",
        "## Section 1 - Purchase Price & Financing",
        "Offer Amount .................. $410,000.00",
        "Financing Type ................ Conventional Loan",
        "Loan Pre-Approval ............. Attached separately",
        "",
        "## Section 2 - Key Dates",
        "Target Closing Date ........... 09/15/2026",
        "Option Period .................. 10 days",
        "",
        "## Section 3 - Contingencies",
        "- Financing contingency",
        "- Appraisal contingency",
        "- Inspection contingency",
        "",
        "This summary reflects the material terms of the accompanying Residential",
        "Purchase Agreement and is provided for the listing broker's initial review.",
    ]
    save(
        make_email(
            "Trent Okafor", "trent@homefirstbrokers-demo.com",
            "Offer submission for 22 Sunset Ridge Ct",
            _dt(1, 10, 30),
            "Good morning,\n\nAttached is my buyer's offer summary for 22 Sunset Ridge Court. "
            "They're first-time buyers and this is close to the top of their pre-approval, "
            "but they really love the house. Happy to discuss.\n\nThanks,\nTrent",
            attachments=[("Purchase_Agreement_Summary_SunsetRidge.pdf", "application/pdf", make_pdf("Residential Purchase Agreement — Summary", pa_lines))],
        ),
        "purchase_offer_2.eml",
    )

    # 7. Vendor invoice as an Excel attachment
    invoice_bytes = make_invoice_xlsx(
        "Reliable Roofing Co.",
        "RR-20264471",
        "123 Oak Street, Unit 2B, Austin, TX 78701",
        [
            ("Roof inspection", 1, 150.0),
            ("Shingle repair - 12 sq", 12, 175.0),
            ("Labor (4 hrs @ $75/hr)", 4, 75.0),
        ],
    )
    save(
        make_email(
            "Billing", "billing@reliableroofing-demo.com",
            "Invoice RR-20264471 - 123 Oak Street roof repair",
            _dt(0.6, 8, 12),
            "Hello,\n\nAttached is our invoice for the roof repair completed at 123 Oak Street, "
            "Unit 2B earlier this week. Payment terms are net 15. Let us know if you have any "
            "questions.\n\nReliable Roofing Co.",
            attachments=[("invoice_RR-20264471.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", invoice_bytes)],
        ),
        "vendor_invoice_1.eml",
    )

    # 8. Off-topic spam - should be classified unclassified / flagged
    save(
        make_email(
            "Prime Credit Solutions", "offers@primecredit-deals.net",
            "Boost Your Credit Score By 100+ Points - Limited Time!!!",
            _dt(0.3, 7, 5),
            "CONGRATULATIONS! You've been PRE-SELECTED for our exclusive credit repair program. "
            "Act now to boost your score by 100+ points in just 30 days! Click below to claim your "
            "free consultation before this offer expires.\n\nUnsubscribe: click here",
        ),
        "spam_general_1.eml",
    )

    # 9. Legitimate but non-actionable general inquiry
    save(
        make_email(
            "Helen Zhao", "helen.zhao88@icloud.com",
            "Do you manage properties outside Austin too?",
            _dt(1.8, 17, 20),
            "Hi,\n\nI love what I've seen of Austin Skyline Realty's listings, but I'm actually "
            "relocating to Round Rock. Do you manage or list properties there as well, or could "
            "you point me to someone who does?\n\nThanks so much,\nHelen",
        ),
        "general_inquiry_1.eml",
    )


if __name__ == "__main__":
    build()
