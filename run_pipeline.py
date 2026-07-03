"""Headless CLI runner - processes every .eml in fixtures/sample_emails through
the real Claude extraction + action pipeline and prints a summary table. Useful
for a terminal-based demo/recording, or for CI-style smoke checks against the
live API. Requires ANTHROPIC_API_KEY (see .env.example).

Usage: python run_pipeline.py
"""

from backend import db, pipeline
from backend.orchestrator import process_one

WIDTH = 100


def main():
    db.init_db()
    files = pipeline.list_fixture_files()
    if not files:
        print("No fixtures found. Run: python fixtures/generate_fixtures.py")
        return

    print(f"Processing {len(files)} email(s) from fixtures/sample_emails ...\n")
    print(f"{'file':<28} {'type':<18} {'action':<16} {'conf':<6} property")
    print("-" * WIDTH)

    for path in files:
        if db.source_already_processed(path.name):
            print(f"{path.name:<28} (already processed - skipping, see dashboard or reset-demo)")
            continue
        intake_id = process_one(path)
        row = db.get_intake(intake_id)
        prop = (row["property_address"] or "-")[:30]
        print(
            f"{row['source_file']:<28} {row['request_type']:<18} "
            f"{row['action_type']:<16} {row['confidence']:<6.2f} {prop}"
        )

    print("\nDone. Run `uvicorn backend.main:app --reload` and open http://127.0.0.1:8000 "
          "to browse full records, drafted replies, and review flags.")


if __name__ == "__main__":
    main()
