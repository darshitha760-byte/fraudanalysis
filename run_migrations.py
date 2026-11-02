#!/usr/bin/env python
"""Initialize non-destructive MongoDB indexes for the application.

The former Alembic/MySQL migration runner has been retired. This command never
modifies or deletes existing documents; application collection validators are
created only for collections that do not already exist.
"""

import argparse
import logging
import sys

from app.db.database import check_database, get_database, initialize_database


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def initialize() -> bool:
    """Verify MongoDB connectivity and ensure application indexes exist."""
    try:
        check_database()
        initialize_database()
        logger.info("MongoDB connectivity verified and indexes initialized.")
        return True
    except Exception:
        logger.exception("MongoDB initialization failed.")
        return False


def show_status() -> bool:
    """Report collection names and index names without reading document data."""
    try:
        check_database()
        database = get_database()
        for collection_name in sorted(database.list_collection_names()):
            indexes = sorted(database[collection_name].index_information())
            print(f"{collection_name}: {', '.join(indexes)}")
        return True
    except Exception:
        logger.exception("Unable to read MongoDB schema status.")
        return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Safe MongoDB schema initialization (no SQL/Alembic migrations)."
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=("initialize", "current", "upgrade", "downgrade", "history"),
        default="initialize",
        help="initialize/current are supported; legacy Alembic commands are rejected",
    )
    args = parser.parse_args(argv)

    if args.command == "initialize":
        return 0 if initialize() else 1
    if args.command == "current":
        return 0 if show_status() else 1

    print(
        "Alembic upgrade/downgrade/history commands are retired. "
        "Use `python run_migrations.py initialize` for non-destructive MongoDB indexes.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
