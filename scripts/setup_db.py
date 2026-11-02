#!/usr/bin/env python3
"""MongoDB setup check; does not create remote resources or transfer data."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.database import check_database, close_db, get_database, initialize_database


if __name__ == "__main__":
    try:
        check_database()
        initialize_database(get_database())
        print("Configured MongoDB is reachable; indexes initialized.")
    except Exception:
        print("MongoDB setup failed; connection details were not logged.", file=sys.stderr)
        raise SystemExit(1)
    finally:
        close_db()
