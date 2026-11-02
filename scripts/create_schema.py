#!/usr/bin/env python3
"""Initialize MongoDB indexes for the application (does not create or drop data)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.database import close_db, get_database, initialize_database


if __name__ == "__main__":
    try:
        db = get_database()
        initialize_database(db)
        print("MongoDB indexes initialized; no documents were created or deleted.")
    except Exception:
        print("MongoDB initialization failed; connection details were not logged.", file=sys.stderr)
        raise SystemExit(1)
    finally:
        close_db()
