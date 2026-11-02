#!/usr/bin/env python
"""Create a local Extended-JSON backup of the configured MongoDB database.

Restore is deliberately disabled: a restore could overwrite or duplicate target
documents and requires a separately reviewed procedure.
"""

import argparse
import gzip
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from bson import json_util

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.database import close_db, get_database

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")
logger = logging.getLogger(__name__)


def backup_database(output_dir="backups", compress=True, retention_days=7) -> bool:
    del retention_days  # Existing backups are never deleted automatically.
    database = get_database()
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = ".jsonl.gz" if compress else ".jsonl"
    backup_file = output_path / f"{database.name}_{timestamp}{suffix}"
    created = False
    try:
        # Exclusive creation prevents a timestamp collision from overwriting an
        # existing backup file.
        with backup_file.open("xb") as raw_handle:
            created = True
            if compress:
                stream = gzip.GzipFile(fileobj=raw_handle, mode="wb")
            else:
                stream = raw_handle
            try:
                for name in sorted(database.list_collection_names()):
                    if name.startswith("system."):
                        continue
                    cursor = database[name].find({}).batch_size(500)
                    for document in cursor:
                        line = json_util.dumps({"collection": name, "document": document}) + "\n"
                        stream.write(line.encode("utf-8"))
            finally:
                if compress:
                    stream.close()
        logger.info("Backup written to %s (%s bytes)", backup_file, backup_file.stat().st_size)
        return True
    except Exception:
        if created:
            try:
                backup_file.unlink(missing_ok=True)
            except OSError:
                pass
        logger.error("MongoDB backup failed; connection details and document values were not logged.")
        return False


def restore_backup(_backup_file: str) -> bool:
    logger.error(
        "Restore is disabled to prevent overwriting or duplicating target documents; "
        "use a separately reviewed procedure."
    )
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="MongoDB backup manager")
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup")
    backup.add_argument("--output-dir", default="backups")
    backup.add_argument("--no-compress", action="store_true")
    backup.add_argument("--retention-days", type=int, default=7)
    restore = commands.add_parser("restore")
    restore.add_argument("backup_file")
    listing = commands.add_parser("list")
    listing.add_argument("--output-dir", default="backups")
    args = parser.parse_args()
    try:
        if args.command == "backup":
            return 0 if backup_database(args.output_dir, not args.no_compress, args.retention_days) else 1
        if args.command == "restore":
            return 0 if restore_backup(args.backup_file) else 2
        folder = Path(args.output_dir)
        for path in sorted(folder.glob("*.jsonl*")) if folder.exists() else []:
            print(f"{path.name} ({path.stat().st_size} bytes)")
        return 0
    finally:
        close_db()


if __name__ == "__main__":
    raise SystemExit(main())
