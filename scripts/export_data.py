#!/usr/bin/env python
"""Export MongoDB documents to CSV files (read-only; never logs document values)."""

import argparse
import csv
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.database import close_db, from_bson, get_database, to_bson

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")
logger = logging.getLogger(__name__)


def _export(collection_name, fields, output_file, filters):
    database = get_database()
    query = {}
    date_field = filters.pop("_date_field", None)
    if date_field:
        bounds = {}
        if filters.pop("_start_date", None) is not None:
            bounds["$gte"] = to_bson(filters.pop("_start_date"))
        if filters.pop("_end_date", None) is not None:
            bounds["$lte"] = to_bson(filters.pop("_end_date"))
        if bounds:
            query[date_field] = bounds
    query.update({key: value for key, value in filters.items() if value is not None})

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        cursor = database[collection_name].find(query).sort("id", 1).batch_size(500)
        for raw in cursor:
            document = from_bson(raw)
            writer.writerow(
                {
                    field: (
                        document[field].isoformat()
                        if isinstance(document.get(field), datetime)
                        else document.get(field)
                    )
                    for field in fields
                }
            )
            count += 1
    logger.info("Exported %s documents to %s", count, output_path)
    return True


def _date(value):
    if value is None:
        return None
    parsed = datetime.strptime(value, "%Y-%m-%d")
    return parsed.replace(tzinfo=timezone.utc)


def _output(output_dir, name):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return Path(output_dir) / f"{name}_{stamp}.csv"


def export_transactions(output_dir="exports", start_date=None, end_date=None, status_filter=None):
    return _export(
        "transactions",
        [
            "id", "transaction_id", "customer_id", "merchant_id", "merchant_name",
            "transaction_date", "amount", "currency", "transaction_type", "status",
            "location_country", "location_city", "device_id", "channel",
        ],
        _output(output_dir, "transactions"),
        {
            "_date_field": "transaction_date",
            "_start_date": start_date,
            "_end_date": end_date,
            "status": status_filter,
        },
    )


def export_alerts(
    output_dir="exports",
    start_date=None,
    end_date=None,
    status_filter=None,
    severity_filter=None,
):
    return _export(
        "fraud_alerts",
        [
            "id", "transaction_id", "customer_id", "alert_severity",
            "risk_score", "alert_status", "alert_reason", "alert_created_at",
        ],
        _output(output_dir, "alerts"),
        {
            "_date_field": "alert_created_at",
            "_start_date": start_date,
            "_end_date": end_date,
            "alert_status": status_filter,
            "alert_severity": severity_filter,
        },
    )


def export_audit_logs(output_dir="exports", start_date=None, end_date=None, action_filter=None):
    return _export(
        "audit_logs",
        [
            "id", "actor_id", "action", "action_category", "target_type",
            "target_id", "action_status", "action_timestamp", "ip_address",
        ],
        _output(output_dir, "audit_logs"),
        {
            "_date_field": "action_timestamp",
            "_start_date": start_date,
            "_end_date": end_date,
            "action": action_filter,
        },
    )


def main():
    parser = argparse.ArgumentParser(description="MongoDB document export manager")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("transactions", "alerts", "audit_logs"):
        command = commands.add_parser(name)
        command.add_argument("--output-dir", default="exports")
        command.add_argument("--start-date")
        command.add_argument("--end-date")
        if name == "transactions":
            command.add_argument("--status")
        elif name == "alerts":
            command.add_argument("--status")
            command.add_argument("--severity")
        else:
            command.add_argument("--action")
    args = parser.parse_args()
    try:
        start, end = _date(args.start_date), _date(args.end_date)
        if args.command == "transactions":
            return int(not export_transactions(args.output_dir, start, end, args.status))
        if args.command == "alerts":
            return int(not export_alerts(args.output_dir, start, end, args.status, args.severity))
        return int(not export_audit_logs(args.output_dir, start, end, args.action))
    except Exception:
        logger.error("Export failed; database connection details and document values were not logged.")
        return 1
    finally:
        close_db()


if __name__ == "__main__":
    raise SystemExit(main())
