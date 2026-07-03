import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")

DB_PATH = ROOT_DIR / "data" / "intake.db"
PROPERTY_RULES_PATH = ROOT_DIR / "data" / "property_rules.json"
ACCOUNTING_EXPORT_PATH = ROOT_DIR / "data" / "accounting_export.csv"
FIXTURES_DIR = ROOT_DIR / "fixtures" / "sample_emails"
TEMPLATES_DIR = ROOT_DIR / "templates"

BROKERAGE_NAME = "Austin Skyline Realty"
