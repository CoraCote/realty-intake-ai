import re
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class Attachment:
    filename: str
    content_type: str
    data: bytes


@dataclass
class EmailData:
    source_file: str
    subject: str
    sender_name: str
    sender_email: str
    date_iso: Optional[str]
    body_text: str
    attachments: List[Attachment] = field(default_factory=list)

    @property
    def raw_display(self) -> str:
        header = (
            f"From: {self.sender_name} <{self.sender_email}>\n"
            f"Subject: {self.subject}\n"
            f"Date: {self.date_iso or 'unknown'}\n"
            f"Attachments: {', '.join(a.filename for a in self.attachments) or 'none'}\n"
            f"{'-' * 60}\n"
        )
        return header + self.body_text


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?(</\1>)", "", html)
    text = _TAG_RE.sub(" ", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def parse_eml(path: Path) -> EmailData:
    with open(path, "rb") as f:
        msg = BytesParser(policy=policy.default).parse(f)

    name, addr = parseaddr(str(msg.get("From", "")))

    date_iso = None
    if msg.get("Date"):
        try:
            date_iso = parsedate_to_datetime(msg["Date"]).isoformat()
        except (TypeError, ValueError):
            date_iso = None

    body_part = msg.get_body(preferencelist=("plain", "html"))
    if body_part is not None:
        content = body_part.get_content()
        body_text = (
            _strip_html(content)
            if body_part.get_content_type() == "text/html"
            else content.strip()
        )
    else:
        body_text = ""

    attachments = []
    for part in msg.iter_attachments():
        filename = part.get_filename() or "attachment"
        payload = part.get_payload(decode=True) or b""
        attachments.append(
            Attachment(
                filename=filename,
                content_type=part.get_content_type(),
                data=payload,
            )
        )

    return EmailData(
        source_file=path.name,
        subject=str(msg.get("Subject", "")).strip(),
        sender_name=name or addr,
        sender_email=addr,
        date_iso=date_iso,
        body_text=body_text,
        attachments=attachments,
    )
