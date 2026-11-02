#!/usr/bin/env python3
"""Initialize application MongoDB indexes without changing stored documents."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.database import check_database, close_db, get_database, initialize_database


def main() -> int:
    try:
        check_database()
        initialize_database(get_database())
        print("MongoDB connectivity verified and indexes initialized.")
        return 0
    except Exception:
        print("MongoDB initialization failed; connection details were not logged.", file=sys.stderr)
        return 1
    finally:
        close_db()


if __name__ == "__main__":
    raise SystemExit(main())
