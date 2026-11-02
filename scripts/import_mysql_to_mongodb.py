#!/usr/bin/env python
"""Dry-run-first, append-only MySQL to MongoDB importer.

The importer is intentionally not invoked by application startup or deployment.
It reads only allowlisted application tables, never drops or updates target data,
and requires both ``--apply`` and an exact target-database confirmation to write.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from bson.decimal128 import Decimal128
from pymongo.errors import OperationFailure, ServerSelectionTimeoutError
from pymongo import MongoClient
from sqlalchemy import MetaData, Table, create_engine, func, inspect, outerjoin, select
from sqlalchemy.exc import ArgumentError, DBAPIError, NoSuchTableError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.db.database import get_database, initialize_database, to_bson  # noqa: E402
from scripts.mysql_schema_profiles import (  # noqa: E402
    LEGACY_TABLES,
    count_legacy_issues,
    count_mapping_issues,
    check_session_timezone,
    detect_profile,
    read_schema_csv,
    reflected_schema,
    report_legacy,
    schema_blockers,
)
from scripts.legacy_mapping_config import read_mapping  # noqa: E402
from scripts.legacy_archive import (  # noqa: E402
    DEFAULT_BUDGET_BYTES, run_archive, validate_archive_database,
)


# Source order follows the original SQL foreign-key dependencies.
TABLES = (
    "users",
    "customers",
    "fraud_rules",
    "transactions",
    "fraud_assessments",
    "triggered_rules",
    "fraud_alerts",
    "investigation_cases",
    "case_notes",
    "audit_logs",
)

FOREIGN_KEYS = (
    ("transactions", "customer_id", "customers"),
    ("fraud_assessments", "transaction_id", "transactions"),
    ("triggered_rules", "assessment_id", "fraud_assessments"),
    ("triggered_rules", "transaction_id", "transactions"),
    ("triggered_rules", "rule_id", "fraud_rules"),
    ("fraud_alerts", "transaction_id", "transactions"),
    ("fraud_alerts", "customer_id", "customers"),
    ("fraud_alerts", "assessment_id", "fraud_assessments"),
    ("fraud_alerts", "reviewed_by", "users"),
    ("investigation_cases", "alert_id", "fraud_alerts"),
    ("investigation_cases", "transaction_id", "transactions"),
    ("investigation_cases", "customer_id", "customers"),
    ("investigation_cases", "assigned_to", "users"),
    ("investigation_cases", "created_by", "users"),
    ("case_notes", "case_id", "investigation_cases"),
    ("case_notes", "analyst_id", "users"),
    ("audit_logs", "actor_id", "users"),
)

UNIQUE_FIELDS = {
    "users": "email",
    "customers": "customer_id",
    "fraud_rules": "rule_id",
    "transactions": "transaction_id",
    "fraud_assessments": "transaction_id",
    "fraud_alerts": "transaction_id",
    "investigation_cases": "alert_id",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive", action="store_true",
        help="Prepare raw singular legacy archive in a separate database; dry-run unless --apply.",
    )
    parser.add_argument("--archive-database", help="Dedicated archive database, never the application database.")
    parser.add_argument("--confirm-archive-digest", help="Exact prior archive content SHA-256 required for apply.")
    parser.add_argument("--confirm-archive-counts", help="Exact comma-separated counts from archive review required for apply.")
    parser.add_argument("--archive-max-bytes", type=int, default=DEFAULT_BUDGET_BYTES,
                        help="Maximum estimated archive BSON bytes (default 400 MiB; excludes indexes).")
    parser.add_argument(
        "--confirm-mapping",
        help="Exact reviewed mapping SHA-256 required with legacy --apply (not permission to read records).",
    )
    parser.add_argument(
        "--mapping-config",
        type=Path,
        help="Bounded nonsecret reviewed JSON semantics for the singular legacy profile.",
    )
    parser.add_argument(
        "--schema-csv",
        type=Path,
        help="Review a metadata-only INFORMATION_SCHEMA CSV offline; no database access.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Insert missing source documents; omitted by default (dry-run only).",
    )
    parser.add_argument(
        "--confirm-target",
        help="Must exactly match MONGODB_DATABASE to enable --apply.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=250,
        help="Bounded source and target batch size (1-1000; default: 250).",
    )
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 1000:
        parser.error("--batch-size must be between 1 and 1000")
    if args.schema_csv and (args.apply or args.confirm_target):
        parser.error("--schema-csv is offline review only; cannot be used with apply/confirmation")
    if args.confirm_mapping and (not args.mapping_config or not args.apply or args.schema_csv):
        parser.error("--confirm-mapping requires --mapping-config and --apply without --schema-csv")
    if args.archive and (args.mapping_config or args.confirm_mapping):
        parser.error("--archive preserves raw semantics and cannot use operational mapping flags")
    if not args.archive and (args.archive_database or args.confirm_archive_digest or args.confirm_archive_counts):
        parser.error("Archive database/proof flags require --archive")
    if args.archive_max_bytes <= 0:
        parser.error("--archive-max-bytes must be positive")
    if (args.confirm_archive_digest or args.confirm_archive_counts) and (not args.apply or args.schema_csv):
        parser.error("Archive proof flags require --archive --apply without --schema-csv")
    return args


def normalize(value: Any) -> Any:
    """Normalize SQL values to BSON-safe values without float conversion."""
    if isinstance(value, Decimal):
        return Decimal128(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, dict):
        return {key: normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize(item) for item in value]
    return value


def source_batches(connection, tables: dict[str, Table], name: str, size: int):
    table = tables[name]
    if "id" not in table.c:
        raise RuntimeError("Source schema is missing the required integer identity column")
    last_id = None
    while True:
        statement = select(table).order_by(table.c.id).limit(size)
        if last_id is not None:
            statement = statement.where(table.c.id > last_id)
        rows = list(connection.execute(statement).mappings())
        if not rows:
            return
        yield rows
        last_id = rows[-1]["id"]


def source_counts(connection, tables: dict[str, Table]) -> dict[str, int]:
    return {
        name: int(connection.execute(select(func.count()).select_from(tables[name])).scalar_one())
        for name in TABLES
    }


def check_source_tables(connection) -> bool:
    """Report only allowlisted application table names before reflection."""
    available = set(inspect(connection).get_table_names())
    missing = [name for name in TABLES if name not in available]
    if not missing:
        return True
    present = [name for name in TABLES if name in available]
    print(f"present_application_tables={','.join(present) or '(none)'}", file=sys.stderr)
    print(f"missing_application_tables={','.join(missing)}", file=sys.stderr)
    print(
        "Import stopped; stage=source_schema; reason=missing_source_table: "
        "check MYSQL_IMPORT_URL selects the existing application database; "
        "do not create empty tables to bypass this check.",
        file=sys.stderr,
    )
    return False


def check_references(connection, tables: dict[str, Table]) -> dict[str, int]:
    problems: dict[str, int] = {}
    for source_name, source_field, target_name in FOREIGN_KEYS:
        source = tables[source_name]
        target = tables[target_name]
        if source_field not in source.c:
            continue
        source_column = source.c[source_field]
        missing = (
            select(func.count())
            .select_from(outerjoin(source, target, source_column == target.c.id))
            .where(source_column.is_not(None), target.c.id.is_(None))
        )
        count = int(connection.execute(missing).scalar_one())
        if count:
            problems[f"{source_name}.{source_field}->{target_name}.id"] = count
    return problems


def row_document(row) -> dict[str, Any]:
    document = {key: normalize(value) for key, value in dict(row).items()}
    if not isinstance(document.get("id"), int):
        raise RuntimeError("Source rows must have integer IDs to preserve public identity")
    return document


def precision_issues(value: Any) -> int:
    if isinstance(value, Decimal):
        try:
            return int(Decimal128(value).to_decimal() != value)
        except Exception:
            return 1
    if isinstance(value, dict):
        return sum(precision_issues(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return sum(precision_issues(item) for item in value)
    return 0


def canonical_document(document: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in document.items() if key != "_id"}


def inspect_target(target, collection: str, document: dict[str, Any]) -> str:
    """Return missing, identical, or conflict without modifying target data."""
    existing = target[collection].find_one({"id": document["id"]})
    unique_field = UNIQUE_FIELDS.get(collection)
    unique_match = None
    if unique_field and document.get(unique_field) is not None:
        unique_match = target[collection].find_one({unique_field: document[unique_field]})

    if existing is None and unique_match is None:
        return "missing"
    if existing is not None and canonical_document(existing) == document:
        return "identical"
    return "conflict"


def report_summary(
    counts: dict[str, int],
    target_counts: dict[str, int],
    references: dict[str, int],
    precision_count: int,
    conflicts: int,
    mode: str,
) -> None:
    print("MySQL to MongoDB import review (no data values or connection strings shown)")
    for name in TABLES:
        print(
            f"{name}: source={counts[name]}, existing_target={target_counts[name]}"
        )
    print(f"source_reference_violations={sum(references.values())}")
    print(f"decimal_precision_issues={precision_count}")
    print(f"target_identity_conflicts={conflicts}")
    print(f"mode={mode}" if conflicts == 0 else "mode=blocked by conflicts")


def safe_failure_reason(error: Exception) -> str:
    """Classify failures without including driver messages or connection details."""
    if isinstance(error, ArgumentError):
        return "invalid_source_uri: check the MySQL URI format and URL-encoding"
    if isinstance(error, NoSuchTableError):
        return "missing_source_table: verify the selected legacy database schema"
    if isinstance(error, DBAPIError):
        arguments = getattr(error.orig, "args", ())
        code = arguments[0] if arguments and isinstance(arguments[0], int) else None
        return {
            1045: "mysql_authentication_failed: check the local username and password",
            1049: "mysql_database_missing: check the existing database name",
            1146: "missing_source_table: verify the selected legacy database schema",
            2003: "mysql_unreachable: check MySQL is running and the host/port",
            2005: "mysql_host_invalid: check the configured host",
        }.get(code, "mysql_driver_error: check source access and schema compatibility")
    if isinstance(error, ServerSelectionTimeoutError):
        return "mongodb_unreachable: check Atlas network access and local MongoDB settings"
    if isinstance(error, OperationFailure):
        if error.code in (13, 18):
            return "mongodb_authorization_failed: check Atlas database-user permissions"
        if error.code == 121:
            return "mongodb_schema_validation_failed: review source field compatibility"
        return "mongodb_operation_failed: check target permissions and schema"
    if isinstance(error, ModuleNotFoundError):
        return "missing_dependency: install requirements-importer.txt"
    return "validation_or_configuration_error: check importer dependencies and schema"


def run() -> int:
    args = parse_args()
    archive = getattr(args, "archive", False)
    mapping = None
    mapping_path = getattr(args, "mapping_config", None)
    if mapping_path:
        try:
            mapping = read_mapping(mapping_path)
        except Exception as error:
            print(
                f"Import stopped; stage=mapping_configuration; reason={safe_failure_reason(error)}",
                file=sys.stderr,
            )
            return 1
    schema_csv = getattr(args, "schema_csv", None)
    if schema_csv:
        # Guard here as well as in argparse: offline review must never become
        # a way around apply confirmation or contact either database.
        if args.apply or args.confirm_target:
            print("--schema-csv is offline review only.", file=sys.stderr)
            return 2
        try:
            schema = read_schema_csv(schema_csv)
            profile = detect_profile(list(schema), TABLES)
            if profile == "legacy_singular_v1":
                if archive:
                    from scripts.legacy_archive import FORMAT
                    print("archive_profile=" + FORMAT + "; metadata_only=true")
                    for label, count in sorted(schema_blockers(schema).items()):
                        print(f"archive_schema_blocker={label}; count={count}")
                    print("archive_case_policy=no synthetic cases; business_semantics=raw_unverified")
                    print("archive_credentials=excluded; timestamps=exact_text_unknown_timezone")
                    print("archive_counts_and_digest=unavailable; target_access=false; target_writes=0")
                    print("archive_apply_ready=false; authorized source record review required")
                    return 1 if schema_blockers(schema) else 0
                report_legacy(schema, mapping=mapping)
                return 1
            if profile == "mixed":
                print("schema_profile=mixed; schema_blocker=mixed_application_schemas; target_access=false")
                return 1
            missing = [name for name in TABLES if name not in schema]
            if mapping or archive:
                print("schema_blocker=legacy_mapping_on_modern_schema; target_access=false")
                return 1
            print("schema_profile=modern_plural; metadata_only=true; target_access=false")
            print("missing_application_tables=" + (",".join(missing) or "(none)"))
            print("record_validation=not_performed; target_writes=0; apply_ready=not_verified")
            return 1 if missing else 0
        except Exception as error:
            print(
                f"Import stopped; stage=metadata_schema; reason={safe_failure_reason(error)}",
                file=sys.stderr,
            )
            return 1
    source_uri = os.environ.get("MYSQL_IMPORT_URL", "")
    if not source_uri:
        print("Set MYSQL_IMPORT_URL in the environment; no connection was attempted.", file=sys.stderr)
        return 2

    try:
        settings = get_settings()
    except Exception as error:
        print(
            f"Import stopped; stage=configuration; reason={safe_failure_reason(error)}",
            file=sys.stderr,
        )
        return 1
    if archive and not validate_archive_database(getattr(args, "archive_database", None), settings.mongodb_database):
        print("Archive requires a dedicated --archive-database distinct from MONGODB_DATABASE.", file=sys.stderr)
        return 2
    if args.apply:
        confirmation_database = args.archive_database if archive else settings.mongodb_database
        if args.confirm_target != confirmation_database:
            print("--apply requires --confirm-target to exactly match the selected target database.", file=sys.stderr)
            return 2
    if not args.apply and args.confirm_target:
        print("--confirm-target is accepted only together with --apply.", file=sys.stderr)
        return 2

    engine = None
    archive_client = None
    stage = "source_uri"
    try:
        # Do not log engine URLs, exception text, row contents, or credentials.
        engine = create_engine(source_uri, hide_parameters=True, pool_pre_ping=True)
        stage = "source_connection"
        with engine.connect() as connection:
            if archive:
                # A stable read-only source snapshot binds all count/digest
                # passes. This changes no records, schema or timezone.
                connection = connection.execution_options(isolation_level="REPEATABLE READ")
                from sqlalchemy import text
                connection.execute(text("SET TRANSACTION READ ONLY"))
            stage = "source_schema"
            inspector = inspect(connection)
            available = inspector.get_table_names()
            profile = detect_profile(available, TABLES)
            if profile == "mixed":
                print("schema_profile=mixed; schema_blocker=mixed_application_schemas; target_access=false")
                return 1
            if profile == "legacy_singular_v1":
                if archive:
                    def archive_target(database_name):
                        nonlocal archive_client, stage
                        stage = "archive_target_connection"
                        archive_uri = os.environ.get("MONGODB_ARCHIVE_URI", "")
                        if not archive_uri:
                            raise RuntimeError("Dedicated archive URI required")
                        archive_client = MongoClient(archive_uri, tz_aware=True, serverSelectionTimeoutMS=10000)
                        return archive_client[database_name]

                    stage = "archive_review"
                    return run_archive(
                        connection, inspector, available, args, settings.mongodb_database,
                        reflected_schema, source_batches, archive_target,
                    )
                schema = reflected_schema(inspector, available)
                if schema_blockers(schema):
                    report_legacy(schema, mapping=mapping)
                    return 1
                if args.apply and (
                    mapping is None or getattr(args, "confirm_mapping", None) != mapping.fingerprint
                ):
                    report_legacy(schema, mapping=mapping)
                    print("Import blocked; --apply requires exact --confirm-mapping SHA-256 from reviewed configuration.")
                    return 1
                metadata = MetaData()
                tables = {
                    name: Table(name, metadata, autoload_with=connection)
                    for name in LEGACY_TABLES
                }
                stage = "source_count_review"
                counts, issues = count_legacy_issues(connection, tables)
                timezone_status = None
                if mapping or archive:
                    issues.update(count_mapping_issues(connection, tables, mapping))
                    timezone_status = check_session_timezone(connection, mapping)
                    if timezone_status != "verified" and any(counts.values()):
                        issues["legacy.source_timezone.unverified_session_offset"] += 1
                report_legacy(schema, counts, issues, mapping, timezone_status)
                print("Import blocked; obtain verified legacy field definitions/mappings before apply.")
                return 1
            if mapping:
                print("schema_blocker=legacy_mapping_on_modern_schema; target_access=false")
                return 1
            if not check_source_tables(connection):
                return 1
            metadata = MetaData()
            tables = {
                name: Table(name, metadata, autoload_with=connection)
                for name in TABLES
            }
            stage = "source_integrity"
            counts = source_counts(connection, tables)
            reference_issues = check_references(connection, tables)

            stage = "target_connection"
            target = get_database()
            target_counts = {
                name: int(target[name].count_documents({}))
                for name in TABLES
            }
            stage = "document_validation"
            decimal_issues = 0
            conflicts = 0
            for name in TABLES:
                for batch in source_batches(connection, tables, name, args.batch_size):
                    for row in batch:
                        document = row_document(row)
                        decimal_issues += precision_issues(dict(row))
                        if inspect_target(target, name, document) == "conflict":
                            conflicts += 1

            report_summary(
                counts,
                target_counts,
                reference_issues,
                decimal_issues,
                conflicts,
                "apply_requested" if args.apply else "dry_run",
            )
            if reference_issues or decimal_issues or conflicts:
                print("Import blocked; resolve integrity/precision/identity issues before review.")
                return 1
            if not args.apply:
                print("dry_run=true; no target documents were written.")
                return 0

            stage = "target_initialization"
            initialize_database(target)
            # Re-scan in bounded batches. Inserts are append-only and use
            # integer IDs plus unique keys for safe reruns; never update/delete.
            stage = "target_insert"
            inserted = Counter()
            for name in TABLES:
                for batch in source_batches(connection, tables, name, args.batch_size):
                    pending = []
                    for row in batch:
                        document = row_document(row)
                        state = inspect_target(target, name, document)
                        if state == "identical":
                            continue
                        if state == "conflict":
                            raise RuntimeError("Target changed during preflight; import stopped")
                        pending.append(to_bson(document))
                    if pending:
                        target[name].insert_many(pending, ordered=True)
                        inserted[name] += len(pending)
            print("apply_complete=true")
            stage = "target_sequences"
            for name in TABLES:
                highest = target[name].find_one(
                    {"id": {"$type": "number"}},
                    projection={"id": 1},
                    sort=[("id", -1)],
                )
                if highest:
                    target["_id_sequences"].update_one(
                        {"_id": name},
                        {"$max": {"value": int(highest["id"])}},
                        upsert=True,
                    )
                print(f"{name}_inserted={inserted[name]}")
            return 0
    except Exception as error:
        # Errors intentionally omit exception text because driver errors may
        # contain endpoint details or credentials.
        if archive and args.apply:
            print(
                "archive_apply_complete=false; review dedicated target for possible partial appends; "
                "no overwrite attempted",
                file=sys.stderr,
            )
        print(
            f"Import stopped; stage={stage}; reason={safe_failure_reason(error)}",
            file=sys.stderr,
        )
        return 1
    finally:
        if archive_client is not None:
            archive_client.close()
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(run())
