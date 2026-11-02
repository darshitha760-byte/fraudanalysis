#!/usr/bin/env python3
"""Non-interactive MongoDB index initialization; no SQL database/user is created."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.database import check_database, close_db, get_database, initialize_database


def main() -> bool:
    try:
        check_database()
        initialize_database(get_database())
        print("MongoDB connectivity verified and indexes initialized.")
        return True
    except Exception:
        print("MongoDB initialization failed; connection details were not logged.", file=sys.stderr)
        return False
    finally:
        close_db()


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
