#!/usr/bin/env python3
"""Compatibility entry point for the idempotent MongoDB fraud-rule seeder."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.db.database import close_db, get_database, initialize_database
from scripts.seed_rules import seed_fraud_rules


def main() -> int:
    try:
        db = get_database()
        initialize_database(db)
        summary = seed_fraud_rules(db)
        print(
            "Rule seeding complete: "
            f"created={summary['created']}, skipped={summary['skipped']}, "
            f"errors={summary['errors']}"
        )
        return int(summary["errors"] > 0)
    except Exception:
        print("Rule seeding failed; connection details were not logged.", file=sys.stderr)
        return 1
    finally:
        close_db()


if __name__ == "__main__":
    raise SystemExit(main())
