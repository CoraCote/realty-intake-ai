import json

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from backend import db, orchestrator
from backend.config import BROKERAGE_NAME, TEMPLATES_DIR

app = FastAPI(title=f"{BROKERAGE_NAME} — Email Intake AI")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

db.init_db()

STATUS_LABELS = {
    "draft_reply": ("Reply drafted", "ok"),
    "flag_for_review": ("Flagged for review", "warn"),
    "sync_line_items": ("Synced to accounting", "info"),
}


@app.get("/")
def dashboard(request: Request):
    rows = db.list_intake()
    for r in rows:
        r["status_label"], r["status_class"] = STATUS_LABELS.get(
            r["action_type"], (r["action_type"], "warn")
        )
        r["flags"] = json.loads(r["flags_json"])
    counts = {"draft_reply": 0, "flag_for_review": 0, "sync_line_items": 0}
    for r in rows:
        counts[r["action_type"]] = counts.get(r["action_type"], 0) + 1
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "rows": rows,
            "counts": counts,
            "brokerage_name": BROKERAGE_NAME,
        },
    )


@app.post("/process-inbox")
def process_inbox():
    orchestrator.process_inbox()
    return RedirectResponse(url="/", status_code=303)


@app.post("/reset-demo")
def reset_demo():
    db.clear_all()
    return RedirectResponse(url="/", status_code=303)


@app.get("/intake/{intake_id}")
def detail(request: Request, intake_id: int):
    row = db.get_intake(intake_id)
    if row is None:
        return RedirectResponse(url="/", status_code=303)
    row["status_label"], row["status_class"] = STATUS_LABELS.get(
        row["action_type"], (row["action_type"], "warn")
    )
    row["flags"] = json.loads(row["flags_json"])
    row["extraction"] = json.loads(row["extraction_json"])
    return templates.TemplateResponse(
        "detail.html",
        {"request": request, "row": row, "brokerage_name": BROKERAGE_NAME},
    )
