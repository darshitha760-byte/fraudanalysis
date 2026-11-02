"""Append-only archive preparation, isolated from operational collections.

No business mapping is applied. Credential fields are deliberately excluded.
Dates are represented textually rather than assigning an unverified timezone.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from bson import BSON
from bson.decimal128 import Decimal128
from sqlalchemy import MetaData, Table

from scripts.mysql_schema_profiles import LEGACY_TABLES, schema_blockers


FORMAT = "legacy_singular_archive_v1"
MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
DEFAULT_BUDGET_BYTES = 400 * 1024 * 1024
DATABASE_NAME = re.compile(r"^[A-Za-z0-9_-]{1,63}$")
# Case-insensitive, recursively applied. Never archive credential material,
# including credentials nested in source audit metadata.
CREDENTIAL_KEYS = {
    "password", "password_hash", "passwd", "pwd", "secret", "secret_key",
    "token", "access_token", "refresh_token", "authorization", "api_key",
    "apikey", "credentials", "connection_string", "database_url",
    "mongodb_uri", "mysql_import_url", "private_key",
}
SECRET_TEXT = re.compile(
    r"(?i)(?:[a-z][a-z0-9+.-]*://[^/\s]+@|bearer\s+[a-z0-9._-]+|"
    r"-----BEGIN [^-]*PRIVATE KEY-----|(?:password|secret|api[_-]?key|access[_-]?token)"
    r"\s*[=:]\s*\S+|\beyJ[a-z0-9_-]+\.[a-z0-9_-]+\.[a-z0-9_-]+|"
    r"\$argon2[a-z0-9]*\$|\$2[aby]\$\d{2}\$|AKIA[A-Z0-9]{16})"
)


def validate_archive_database(name: str | None, live_database: str) -> bool:
    return (
        isinstance(name, str) and bool(DATABASE_NAME.fullmatch(name))
        and name.casefold() not in {live_database.casefold(), "admin", "config", "local"}
    )


def archive_value(value: Any, omitted: Counter) -> Any:
    if isinstance(value, Decimal):
        if not value.is_finite():
            return {"archive_type": "decimal", "exact_text": str(value), "bson_decimal": False}
        try:
            converted = Decimal128(value)
            if converted.to_decimal() == value:
                return converted
        except Exception:
            pass
        return {"archive_type": "decimal", "exact_text": str(value), "bson_decimal": False}
    if isinstance(value, (datetime, date, time)):
        return {
            "archive_type": type(value).__name__, "exact_text": value.isoformat(),
            "timezone": (
                "unknown" if not isinstance(value, (datetime, time)) or value.tzinfo is None
                else "source_explicit_offset"
            ),
        }
    if isinstance(value, timedelta):
        return {
            "archive_type": "timedelta", "days": value.days,
            "seconds": value.seconds, "microseconds": value.microseconds,
        }
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("Unsupported archive key")
            normalized = key.casefold().replace("-", "_")
            if normalized in CREDENTIAL_KEYS or normalized.endswith(("_password", "_secret", "_token", "_api_key")):
                omitted["credential_fields"] += 1
                continue
            result[key] = archive_value(item, omitted)
        return result
    if isinstance(value, (tuple, list)):
        return [archive_value(item, omitted) for item in value]
    if isinstance(value, str):
        if value.lstrip().startswith(("{", "[")):
            try:
                structured = json.loads(value)
            except (ValueError, RecursionError):
                structured = None
            if isinstance(structured, (dict, list)):
                before = omitted["credential_fields"]
                cleaned = archive_value(structured, omitted)
                if omitted["credential_fields"] != before:
                    return {
                        "archive_type": "redacted_json_text",
                        "sanitized_fields": cleaned,
                        "reason": "credential_material",
                    }
        if SECRET_TEXT.search(value):
            omitted["credential_fields"] += 1
            return {"archive_type": "redacted", "reason": "credential_material"}
    if value is None or isinstance(value, (str, bytes, bool, int, float)):
        return value
    raise ValueError("Unsupported source archive type")


def canonical(value: Any) -> Any:
    if isinstance(value, Decimal128):
        return {"$archive_decimal128": str(value.to_decimal())}
    if isinstance(value, bytes):
        return {"$archive_binary_hex": value.hex()}
    if isinstance(value, float):
        return {"$archive_float_hex": value.hex()}
    if isinstance(value, dict):
        return {key: canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return [canonical(item) for item in value]
    return value


def archive_document(table: str, row) -> tuple[dict, Counter, int]:
    if table not in LEGACY_TABLES:
        raise ValueError("Unsupported archive table")
    values = dict(row)
    if type(values.get("id")) is not int:
        raise ValueError("Archive requires source integer primary identity")
    omitted: Counter = Counter()
    source = archive_value(values, omitted)
    payload = {
        "format": FORMAT, "source_table": table, "source_id": values["id"],
        "source_fields": source,
        "source_timezone": "unknown_not_normalized",
        "business_semantics": "raw_unverified_not_operational",
        "credential_policy": "credential_fields_excluded",
    }
    encoded = json.dumps(canonical(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(encoded.encode()).hexdigest()
    document = {"_id": values["id"], **payload, "content_sha256": digest}
    size = len(BSON.encode(document))
    if size >= MAX_DOCUMENT_BYTES:
        raise ValueError("Archive document exceeds BSON limit")
    return document, omitted, size


def state(target, table, document) -> str:
    existing = target[table].find_one({"_id": document["_id"]})
    if existing is None:
        return "missing"
    return "identical" if existing == document else "conflict"


def review_source(connection, tables, batch_size, batches, target=None):
    counts: Counter = Counter()
    omitted: Counter = Counter()
    states: Counter = Counter()
    digest = hashlib.sha256(FORMAT.encode())
    total_bytes = 0
    pending_bytes = 0
    for table in LEGACY_TABLES:
        digest.update(b"\x00" + table.encode())
        for batch in batches(connection, tables, table, batch_size):
            for row in batch:
                document, excluded, size = archive_document(table, row)
                counts[table] += 1
                omitted.update(excluded)
                total_bytes += size
                digest.update(bytes.fromhex(document["content_sha256"]))
                if target is not None:
                    status = state(target, table, document)
                    states[status] += 1
                    if status == "missing":
                        pending_bytes += size
    return {
        "counts": {name: counts[name] for name in LEGACY_TABLES},
        "digest": digest.hexdigest(), "omitted": omitted,
        "total_bytes": total_bytes, "pending_bytes": pending_bytes, "states": states,
    }


def report(review, source_counts, target_checked=False):
    print("archive_profile=" + FORMAT)
    print("archive_separation=dedicated_database; no live schema or business mappings")
    print("archive_temporal_policy=exact_text; unknown timezone not normalized")
    print("archive_credential_policy=excluded recursively; contact fields may remain sensitive")
    for table in LEGACY_TABLES:
        print(f"archive_table={table}; source_count={source_counts[table]}; reviewed_count={review['counts'][table]}")
    print("archive_absent_case_tables=investigation_cases,case_notes; no synthesized records")
    print(f"archive_content_sha256={review['digest']}")
    print("archive_count_confirmation=" + ",".join(str(source_counts[name]) for name in LEGACY_TABLES))
    print(f"archive_credential_fields_omitted={review['omitted']['credential_fields']}")
    print(f"archive_estimated_bson_bytes={review['total_bytes']}")
    print("archive_size_policy=estimate excludes index/storage overhead; check actual Atlas remaining quota")
    print(f"archive_target_checked={str(target_checked).lower()}")
    for label in ("missing", "identical", "conflict"):
        value = review["states"][label] if target_checked else "not_checked"
        print(f"archive_target_{label}={value}")


def run_archive(connection, inspector, available, args, live_database, schema_reader,
                batches, target_factory) -> int:
    if not validate_archive_database(getattr(args, "archive_database", None), live_database):
        print("Archive blocked; dedicated --archive-database must differ from the live application database.")
        return 2
    if args.apply and args.confirm_target != args.archive_database:
        print("Archive --apply requires exact --confirm-target matching --archive-database.")
        return 2
    schema = schema_reader(inspector, available)
    blockers = schema_blockers(schema)
    if blockers:
        for label, count in sorted(blockers.items()):
            print(f"archive_schema_blocker={label}; count={count}")
        return 1
    metadata = MetaData()
    tables = {name: Table(name, metadata, autoload_with=connection) for name in LEGACY_TABLES}
    from sqlalchemy import func, select

    def counts():
        return {
            name: int(connection.execute(select(func.count()).select_from(tables[name])).scalar_one())
            for name in LEGACY_TABLES
        }

    source_counts = counts()
    review = review_source(connection, tables, args.batch_size, batches)
    report(review, source_counts)
    if review["counts"] != source_counts or counts() != source_counts:
        print("Archive blocked; source counts changed during review.")
        return 1
    budget = getattr(args, "archive_max_bytes", DEFAULT_BUDGET_BYTES)
    if review["total_bytes"] > budget:
        print("Archive blocked; BSON estimate exceeds --archive-max-bytes budget.")
        return 1
    if not args.apply:
        print("archive_dry_run=true; target_access=false; target_writes=0")
        return 0
    count_proof = ",".join(str(source_counts[name]) for name in LEGACY_TABLES)
    if (
        getattr(args, "confirm_archive_digest", None) != review["digest"]
        or getattr(args, "confirm_archive_counts", None) != count_proof
    ):
        print("Archive blocked; exact --confirm-archive-digest and --confirm-archive-counts from prior review required.")
        return 2
    # This factory accesses only the dedicated archive database, not get_database
    # or initialize_database. Never create live users/rules/indexes/sequences.
    target = target_factory(args.archive_database)
    unexpected = set(target.list_collection_names()) - set(LEGACY_TABLES)
    if unexpected:
        print("Archive blocked; dedicated target contains unexpected collections (names omitted).")
        return 1
    target_review = review_source(connection, tables, args.batch_size, batches, target)
    report(target_review, source_counts, target_checked=True)
    stats = target.command("dbStats")
    if any(
        not isinstance(stats.get(key), (int, float)) or isinstance(stats.get(key), bool) or stats[key] < 0
        for key in ("dataSize", "indexSize")
    ):
        raise RuntimeError("Archive target capacity metadata unavailable")
    used_bytes = int(stats["dataSize"]) + int(stats["indexSize"])
    estimate = used_bytes + target_review["pending_bytes"] * 2
    print(f"archive_target_existing_bytes={used_bytes}; archive_with_headroom_estimated_bytes={estimate}")
    if estimate > budget:
        print("Archive blocked; existing target plus conservative pending headroom exceeds byte budget.")
        return 1
    if (
        target_review["digest"] != review["digest"] or target_review["counts"] != source_counts
        or counts() != source_counts or target_review["states"]["conflict"]
    ):
        print("Archive blocked; source changed or target identity conflict.")
        return 1
    # The caller holds a repeatable-read source transaction for every pass.
    # Partial target insert failures remain explicit and can be rerun safely.
    inserted: Counter = Counter()
    for table in LEGACY_TABLES:
        for batch in batches(connection, tables, table, args.batch_size):
            pending = []
            for row in batch:
                document, _, _ = archive_document(table, row)
                status = state(target, table, document)
                if status == "conflict":
                    raise RuntimeError("Archive target changed after preflight")
                if status == "missing":
                    pending.append(document)
            if pending:
                target[table].insert_many(pending, ordered=True)
                inserted[table] += len(pending)
    final_review = review_source(connection, tables, args.batch_size, batches, target)
    if (
        final_review["digest"] != review["digest"] or final_review["counts"] != source_counts
        or final_review["states"]["conflict"] or final_review["states"]["missing"]
        or counts() != source_counts
    ):
        print("archive_apply_complete=false; source/target changed; partial append may exist; no overwrite attempted")
        return 1
    for table in LEGACY_TABLES:
        print(f"archive_table={table}; inserted={inserted[table]}")
    print("archive_apply_complete=true; application_access=false; database_permission_enforcement=not_provisioned")
    return 0
