"""Explicit, conservative schema review for the eight-table legacy export.

Candidate mappings are review artifacts. Reviewed configuration can resolve
individual semantics; source enrichment and live-import preflight remain separate.
"""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from sqlalchemy import String, cast, func, outerjoin, select, text
from bson.decimal128 import Decimal128

from scripts.legacy_mapping_config import (
    ReviewedMapping, convert_timestamps, decimal_text, mapped_value,
)


LEGACY_TABLES = {
    "user": "users",
    "customer": "customers",
    "fraud_rule": "fraud_rules",
    "transaction_record": "transactions",
    "fraud_assessment": "fraud_assessments",
    "triggered_rule": "triggered_rules",
    "fraud_alert": "fraud_alerts",
    "audit_log": "audit_logs",
}
ABSENT_LEGACY_COLLECTIONS = ("investigation_cases", "case_notes")
LEGACY_COLUMNS = {
    "user": "id email password_hash role is_active created_at updated_at",
    "customer": "id external_id first_name last_name email phone created_at updated_at",
    "fraud_rule": (
        "id rule_code rule_name description rule_type threshold_value operator "
        "is_active severity_level risk_weight created_at updated_at"
    ),
    "transaction_record": (
        "id customer_id amount currency merchant_id merchant_name merchant_category "
        "transaction_date transaction_type card_last_four device_id device_type "
        "location_city location_country location_latitude location_longitude "
        "is_synthetic fraud_label created_at updated_at"
    ),
    "fraud_assessment": (
        "id transaction_id risk_score risk_level ml_prediction ml_confidence "
        "rules_triggered assessment_reason created_at updated_at"
    ),
    "triggered_rule": (
        "id transaction_id rule_id triggered_value triggered_reason created_at"
    ),
    "fraud_alert": (
        "id transaction_id alert_status risk_score alert_reason assigned_to "
        "review_notes review_decision reviewed_at created_at updated_at"
    ),
    "audit_log": (
        "id actor_id action target_entity target_id metadata changes_before "
        "changes_after created_at"
    ),
}
# Only representation-equivalent fields are mapped. Everything, including
# unmapped fields, is retained verbatim in legacy_metadata.source_fields.
FIELD_MAPS = {
    "user": {"email": "email", "password_hash": "password_hash"},
    "customer": {"email": "email", "phone": "phone"},
    "fraud_rule": {
        "rule_code": "rule_id", "rule_name": "name", "description": "description",
        "rule_type": "rule_type", "threshold_value": "threshold_value",
    },
    "transaction_record": {
        field: field for field in (
            "customer_id", "amount", "currency", "merchant_id", "merchant_name",
            "merchant_category", "transaction_date", "transaction_type",
            "device_id", "location_city", "location_country",
        )
    },
    "fraud_assessment": {
        "transaction_id": "transaction_id", "assessment_reason": "explanation",
    },
    "triggered_rule": {
        "transaction_id": "transaction_id", "rule_id": "rule_id",
        "triggered_reason": "rule_explanation", "created_at": "trigger_timestamp",
    },
    "fraud_alert": {
        "transaction_id": "transaction_id", "alert_reason": "alert_reason",
        "review_notes": "review_notes", "reviewed_at": "review_timestamp",
        "created_at": "alert_created_at",
    },
    "audit_log": {
        "actor_id": "actor_id", "action": "action", "metadata": "metadata",
        "changes_before": "changes_before", "changes_after": "changes_after",
        "created_at": "action_timestamp",
    },
}
ROLE_MAP = {"Admin": "admin", "Analyst": "analyst", "Viewer": "viewer"}
MANDATORY_SOURCE_FIELDS = {
    "user": ("email", "password_hash", "role", "is_active"),
    "customer": ("first_name", "last_name"),
    "fraud_rule": ("rule_code", "rule_name", "description", "rule_type", "is_active"),
    "transaction_record": (
        "customer_id", "amount", "currency", "transaction_date", "transaction_type",
        "is_synthetic",
    ),
    "fraud_assessment": ("transaction_id", "risk_score", "risk_level"),
    "triggered_rule": ("transaction_id", "rule_id", "created_at"),
    "fraud_alert": ("transaction_id", "alert_status", "created_at"),
    "audit_log": ("action", "created_at"),
}
UNRESOLVED_FIELDS = {
    "user": ("required_mapping.full_name",),
    "customer": ("unverified_default.risk_profile",),
    "transaction_record": ("required_mapping.status", "required_mapping.payment_method"),
    "fraud_rule": (
        "unknown_semantics.severity_level", "unknown_semantics.risk_weight",
        "unknown_semantics.rule_type_operator_threshold",
    ),
    "fraud_assessment": (
        "unknown_semantics.risk_score", "unknown_semantics.risk_level_to_risk_category",
        "unknown_semantics.ml_prediction_ml_confidence",
    ),
    "triggered_rule": ("unverified_mapping.triggered_value",),
    "fraud_alert": (
        "unknown_semantics.risk_score", "required_mapping.alert_severity",
        "unknown_semantics.alert_status_review_decision_assigned_to",
    ),
    "audit_log": (
        "required_mapping.action_category", "required_mapping.target_type",
        "unverified_default.action_status", "unverified_mapping.target_id",
    ),
}
DIRECT_REFERENCES = (
    ("transaction_record", "customer_id", "customer"),
    ("fraud_assessment", "transaction_id", "transaction_record"),
    ("triggered_rule", "transaction_id", "transaction_record"),
    ("triggered_rule", "rule_id", "fraud_rule"),
    ("fraud_alert", "transaction_id", "transaction_record"),
    ("fraud_alert", "assigned_to", "user"),
    ("audit_log", "actor_id", "user"),
)
ID_POLICY = (
    "integer id and integer foreign keys preserved; "
    "customer.customer_id=external_id when nonempty, otherwise legacy-customer-{id}; "
    "transaction_record.transaction_id=legacy-transaction_record-{id}; "
    "fraud_rule.rule_id=rule_code; no synthetic people, assessments, cases or statuses"
)
HISTORICAL_EVIDENCE = (
    "8532e82:scripts/create_schema.py matches singular column names; "
    "severity_level DEFAULT 1 and risk_weight DEFAULT 1.0 are defaults, not conversion definitions; "
    "8532e82:app/models/fraud_rule.py and app/services/risk_engine.py use plural tables; "
    "plural engine 0-100/category definitions do not prove singular score compatibility; "
    "no scoped historical time_zone convention or severity_level evaluator found"
)


def detect_profile(available: Sequence[str], modern_tables: Sequence[str]) -> str:
    names = set(available)
    modern = names.intersection(modern_tables)
    legacy = names.intersection(LEGACY_TABLES)
    if modern and legacy:
        return "mixed"
    if legacy:
        return "legacy_singular_v1"
    return "modern_plural"


def read_schema_csv(path: Path) -> dict[str, dict[str, dict[str, str]]]:
    """Read metadata only; reject record exports and never echo input values."""
    schema: dict[str, dict[str, dict[str, str]]] = {}
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != [
            "TABLE_NAME", "COLUMN_NAME", "COLUMN_TYPE", "IS_NULLABLE", "COLUMN_KEY"
        ]:
            raise ValueError("Unsupported metadata header")
        for index, row in enumerate(reader):
            if index >= 1000 or None in row or any(value is None for value in row.values()):
                raise ValueError("Invalid or oversized metadata")
            table, column = row["TABLE_NAME"], row["COLUMN_NAME"]
            if not table or not column or row["IS_NULLABLE"] not in {"YES", "NO"}:
                raise ValueError("Invalid column metadata")
            columns = schema.setdefault(table, {})
            if column in columns:
                raise ValueError("Duplicate column metadata")
            columns[column] = {
                "type": row["COLUMN_TYPE"],
                "nullable": row["IS_NULLABLE"],
                "key": row["COLUMN_KEY"],
            }
    if not schema:
        raise ValueError("Empty metadata")
    return schema


def schema_blockers(schema: Mapping[str, Mapping[str, Mapping[str, str]]]) -> Counter:
    blockers: Counter = Counter()
    for table, expected in LEGACY_COLUMNS.items():
        if table not in schema:
            blockers[f"{table}.missing_table"] += 1
            continue
        columns = schema[table]
        for field in expected.split():
            if field not in columns:
                blockers[f"{table}.{field}.missing_column"] += 1
        identity = columns.get("id", {})
        sql_type = identity.get("type", "").lower()
        if (
            sql_type.split("(")[0].split()[0:1] not in (["int"], ["integer"], ["bigint"], ["smallint"])
            or identity.get("nullable") != "NO"
            or identity.get("key") != "PRI"
        ):
            blockers[f"{table}.id.invalid_integer_primary_key"] += 1
    return blockers


def mapping_blockers(
    mapping: ReviewedMapping | None = None, counts: Mapping[str, int] | None = None
) -> Counter:
    blockers = Counter({
        f"{table}.{issue}": 1
        for table, issues in UNRESOLVED_FIELDS.items()
        for issue in issues
    })
    blockers["legacy.unknown_semantics.source_timezone"] = 1
    return Counter({
        issue: count for issue, count in blockers.items()
        if (mapping is None or not mapping.resolves(issue))
        and not (
            counts is not None
            and (
                counts.get(issue.split(".", 1)[0]) == 0
                or issue.startswith("legacy.") and counts and not any(counts.values())
            )
        )
    })


@dataclass
class MappingReview:
    collection: str
    candidate: dict[str, Any]
    blockers: Counter

    @property
    def importable(self) -> bool:
        return not self.blockers


Lookup = Callable[[str, str, Any], Sequence[Mapping[str, Any]]]


def legacy_candidate(
    table: str, row: Mapping[str, Any], lookup: Lookup,
    mapping: ReviewedMapping | None = None,
) -> MappingReview:
    """Prepare a non-writing candidate; lookups must expose at most two matches.

    No timestamps, names, scores or statuses are manufactured. The caller must
    not persist a candidate with blockers or without full live-import preflight.
    """
    if table not in LEGACY_TABLES:
        raise ValueError("Unsupported source table")
    blockers = Counter({
        issue: count for issue, count in mapping_blockers(mapping).items()
        if issue.startswith(table + ".") or issue.startswith("legacy.")
    })
    identity = row.get("id")
    if type(identity) is not int:
        blockers[f"{table}.id.invalid_integer_identity"] += 1
    candidate = {
        target: row[source] for source, target in FIELD_MAPS[table].items()
        if source in row
    }
    candidate["id"] = identity
    for field in ("created_at", "updated_at"):
        if field in row:
            candidate[field] = row[field]
    candidate["legacy_metadata"] = {
        "profile": "legacy_singular_v1", "source_table": table,
        "source_id": identity, "source_fields": dict(row),
        # BSON dates have millisecond precision. Keep original temporal text
        # (including microseconds and a naive/offset distinction) for review.
        "source_timestamps": {
            field: value.isoformat() for field, value in row.items()
            if isinstance(value, datetime)
        },
    }
    mapped_sources = {
        spec["source"] for name, spec in (mapping.fields.items() if mapping else ())
        if name.startswith(table + ".") and spec.get("null_policy") == "archive"
    }
    for field in MANDATORY_SOURCE_FIELDS[table]:
        if field in mapped_sources:
            continue
        if row.get(field) is None or row.get(field) == "":
            blockers[f"{table}.{field}.missing_required_value"] += 1

    def unique(source: str, field: str, value: Any, label: str):
        if type(value) is not int:
            blockers[f"{label}.missing_or_invalid_reference"] += 1
            return None
        matches = lookup(source, field, value)
        if len(matches) != 1 or type(matches[0].get("id")) is not int:
            blockers[f"{label}.{'ambiguous' if len(matches) > 1 else 'missing'}_reference"] += 1
            return None
        return matches[0]

    resolved = {}
    for source, field, target in DIRECT_REFERENCES:
        if source == table and row.get(field) is not None:
            resolved[field] = unique(target, "id", row[field], f"{table}.{field}")
    if table == "customer":
        external = row.get("external_id")
        if external not in (None, "") and not isinstance(external, str):
            blockers["customer.external_id.invalid_value"] += 1
        elif external not in (None, ""):
            candidate["customer_id"] = external
        elif type(identity) is int:
            candidate["customer_id"] = f"legacy-customer-{identity}"
        if all(isinstance(row.get(field), str) and row[field].strip() for field in ("first_name", "last_name")):
            candidate["name"] = f"{row['first_name']} {row['last_name']}"
        else:
            blockers["customer.name.missing_required_value"] += 1
    elif table == "transaction_record" and type(identity) is int:
        candidate["transaction_id"] = f"legacy-transaction_record-{identity}"
    elif table == "user":
        if row.get("role") in ROLE_MAP:
            candidate["role"] = ROLE_MAP[row["role"]]
        else:
            blockers["user.role.unrecognized_enum"] += 1
    if table in {"user", "fraud_rule", "transaction_record"}:
        source, target = {
            "user": ("is_active", "is_active"),
            "fraud_rule": ("is_active", "is_enabled"),
            "transaction_record": ("is_synthetic", "is_synthetic"),
        }[table]
        if row.get(source) in (0, 1) and isinstance(row.get(source), (bool, int)):
            candidate[target] = bool(row[source])
        else:
            blockers[f"{table}.{source}.unrecognized_boolean"] += 1
    if table in {"triggered_rule", "fraud_alert"}:
        assessment = unique(
            "fraud_assessment", "transaction_id", row.get("transaction_id"),
            f"{table}.assessment_id",
        )
        if assessment is not None:
            candidate["assessment_id"] = assessment["id"]
        if table == "fraud_alert":
            transaction = resolved.get("transaction_id")
            if transaction is not None:
                customer = unique(
                    "customer", "id", transaction.get("customer_id"),
                    "fraud_alert.customer_id",
                )
                if customer is not None:
                    candidate["customer_id"] = customer["id"]
    if mapping:
        for name, spec in mapping.fields.items():
            source_table, target_field = name.split(".", 1)
            if source_table != table:
                continue
            try:
                value = mapped_value(name, spec, row.get(spec["source"]))
                if spec["kind"] != "archive":
                    candidate[target_field] = value
            except Exception:
                # Validation errors are labels only, never offending values.
                blockers[f"{name}.invalid_reviewed_mapping_value"] += 1
        if mapping.source_timezone is not None:
            # Keep source_fields and timestamp strings in their original form;
            # convert only candidate target fields using the reviewed offset.
            candidate = {
                key: value if key == "legacy_metadata" else convert_timestamps(value, mapping.source_timezone)
                for key, value in candidate.items()
            }
        candidate["legacy_metadata"]["mapping_sha256"] = mapping.fingerprint
        if table == "fraud_assessment" and isinstance(candidate.get("risk_score"), Decimal):
            score = candidate["risk_score"]
            # Target RiskEngine.calculate_risk_level uses these exact boundaries.
            # This verifies a reviewed category mapping; it never manufactures one.
            expected = "LOW" if score <= 30 else "MEDIUM" if score <= 70 else "HIGH"
            if candidate.get("risk_category") is not None and candidate["risk_category"] != expected:
                blockers["fraud_assessment.risk_category.conflicts_with_target_score"] += 1

    def check_precision(value):
        if isinstance(value, Decimal):
            try:
                if Decimal128(value).to_decimal() != value or not value.is_finite():
                    blockers[f"{table}.decimal_precision.invalid_value"] += 1
            except Exception:
                blockers[f"{table}.decimal_precision.invalid_value"] += 1
        elif isinstance(value, Mapping):
            for item in value.values():
                check_precision(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                check_precision(item)

    check_precision(candidate)
    if not blockers:
        from app.models.audit_log import AuditLog
        from app.models.customer import Customer
        from app.models.fraud_alert import FraudAlert, FraudAssessment, TriggeredRule
        from app.models.fraud_rule import FraudRule
        from app.models.transaction import Transaction
        from app.models.user import User

        models = {
            "user": User, "customer": Customer, "fraud_rule": FraudRule,
            "transaction_record": Transaction, "fraud_assessment": FraudAssessment,
            "triggered_rule": TriggeredRule, "fraud_alert": FraudAlert, "audit_log": AuditLog,
        }
        try:
            # Validation only: never serialize inferred model defaults into the
            # candidate or initialize any target collection.
            models[table].model_validate(candidate)
        except Exception:
            blockers[f"{table}.target_model.invalid_document"] += 1
    return MappingReview(LEGACY_TABLES[table], candidate, blockers)


def count_legacy_issues(connection, tables) -> tuple[dict[str, int], Counter]:
    """Aggregate-only source review: no source record values leave MySQL."""
    counts = {}
    issues: Counter = Counter()

    def count(statement):
        return int(connection.execute(statement).scalar_one())

    for name, table in tables.items():
        counts[name] = count(select(func.count()).select_from(table))
        for field in ("id", *MANDATORY_SOURCE_FIELDS[name]):
            if field in table.c:
                column = table.c[field]
                condition = column.is_(None)
                if isinstance(column.type, String):
                    condition = condition | (func.trim(column) == "")
                issues[f"{name}.{field}.missing_required_value"] = count(
                    select(func.count()).select_from(table).where(condition)
                )
        unique_field = {
            "user": "email", "customer": "external_id", "fraud_rule": "rule_code",
            "fraud_assessment": "transaction_id", "fraud_alert": "transaction_id",
        }.get(name)
        expressions = {"id": table.c.id} if "id" in table.c else {}
        if unique_field and unique_field in table.c:
            expressions[unique_field] = table.c[unique_field]
        if name == "customer" and {"id", "external_id"}.issubset(table.c.keys()):
            issues["customer.customer_id.generated_records"] = count(
                select(func.count()).select_from(table)
                .where(table.c.external_id.is_(None) | (table.c.external_id == ""))
            )
            expressions["generated_customer_id"] = func.coalesce(
                func.nullif(table.c.external_id, ""),
                func.concat("legacy-customer-", cast(table.c.id, String)),
            )
        for field, expression in expressions.items():
            duplicates = (
                select(func.count().label("n")).select_from(table)
                .where(expression.is_not(None)).group_by(expression)
                .having(func.count() > 1).subquery()
            )
            issues[f"{name}.{field}.conflicting_records"] = count(
                select(func.coalesce(func.sum(duplicates.c.n), 0))
            )
    for source, field, target in DIRECT_REFERENCES:
        if source not in tables or target not in tables:
            continue
        left, right = tables[source], tables[target]
        if field not in left.c or "id" not in right.c:
            continue
        issues[f"{source}.{field}.missing_reference"] = count(
            select(func.count()).select_from(outerjoin(left, right, left.c[field] == right.c.id))
            .where(left.c[field].is_not(None), right.c.id.is_(None))
        )
    assessment = tables.get("fraud_assessment")
    if assessment is not None and "transaction_id" in assessment.c:
        grouped = (
            select(assessment.c.transaction_id, func.count().label("n"))
            .group_by(assessment.c.transaction_id).subquery()
        )
        for name in ("triggered_rule", "fraud_alert"):
            table = tables.get(name)
            if table is None or "transaction_id" not in table.c:
                continue
            joined = outerjoin(table, grouped, table.c.transaction_id == grouped.c.transaction_id)
            for label, condition in (
                ("missing", grouped.c.n.is_(None)), ("ambiguous", grouped.c.n > 1)
            ):
                issues[f"{name}.assessment_id.{label}_reference"] = count(
                    select(func.count()).select_from(joined).where(condition)
                )
    alert, transaction, customer = (
        tables.get("fraud_alert"), tables.get("transaction_record"), tables.get("customer")
    )
    if (
        alert is not None and transaction is not None and customer is not None
        and "transaction_id" in alert.c and {"id", "customer_id"}.issubset(transaction.c.keys())
        and "id" in customer.c
    ):
        joined = outerjoin(alert, transaction, alert.c.transaction_id == transaction.c.id)
        joined = outerjoin(joined, customer, transaction.c.customer_id == customer.c.id)
        issues["fraud_alert.customer_id.missing_reference"] = count(
            select(func.count()).select_from(joined).where(customer.c.id.is_(None))
        )
    if "transaction_record" in counts:
        issues["transaction_record.transaction_id.generated_records"] = counts["transaction_record"]
    return counts, issues


def reflected_schema(inspector, available) -> dict:
    schema = {}
    for name in LEGACY_TABLES:
        if name not in available:
            continue
        primary = set(inspector.get_pk_constraint(name).get("constrained_columns", []))
        schema[name] = {
            column["name"]: {
                "type": str(column["type"]),
                "nullable": "YES" if column["nullable"] else "NO",
                "key": "PRI" if column["name"] in primary else "",
            }
            for column in inspector.get_columns(name)
        }
    return schema


def count_mapping_issues(connection, tables, mapping: ReviewedMapping) -> Counter:
    """Validate configured enums/ranges with counts, never retrieve row values."""
    issues: Counter = Counter()
    for name, spec in mapping.fields.items():
        table_name = name.split(".", 1)[0]
        table = tables.get(table_name)
        if table is None or spec["source"] not in table.c:
            issues[f"{name}.missing_mapping_source_column"] += 1
            continue
        column = table.c[spec["source"]]
        conditions = []
        if spec["kind"] == "enum":
            expression = column if isinstance(column.type, String) else cast(column, String)
            conditions.append(expression.not_in(list(spec["values"])))
        elif spec["kind"] == "decimal":
            conditions.append(
                (column < decimal_text(spec["source_min"])) | (column > decimal_text(spec["source_max"]))
            )
            transformed = column * decimal_text(spec["multiplier"]) + decimal_text(spec["offset"])
            conditions.append(
                (transformed < decimal_text(spec["target_min"])) | (transformed > decimal_text(spec["target_max"]))
            )
        if spec.get("null_policy", "block") == "block" and spec["kind"] != "archive":
            conditions.append(column.is_(None))
        if not conditions:
            continue
        condition = conditions[0]
        for extra in conditions[1:]:
            condition = condition | extra
        issues[f"{name}.invalid_reviewed_mapping_values"] = int(
            connection.execute(select(func.count()).select_from(table).where(condition)).scalar_one()
        )
    return issues


def check_session_timezone(connection, mapping: ReviewedMapping) -> str:
    if mapping.source_timezone is None:
        return "missing_mapping"
    # MySQL TIMESTAMP is returned in the *session* zone. Global/system timezone
    # alone cannot establish the offset of historical naive timestamp values.
    metadata = connection.execute(
        text("SELECT @@session.time_zone AS session_zone, "
             "@@global.time_zone AS global_zone, @@system_time_zone AS system_zone")
    ).mappings().one()
    return "verified" if metadata["session_zone"] == mapping.timezone_offset else "unverified_session_offset"


def report_legacy(schema, counts=None, issues=None, mapping=None, timezone_status=None) -> None:
    """Print only allowlisted schema labels, policies and aggregate counts."""
    print("schema_profile=legacy_singular_v1")
    print("historical_evidence=" + HISTORICAL_EVIDENCE)
    print("legacy_absent_case_tables=" + ",".join(ABSENT_LEGACY_COLLECTIONS))
    print("case_policy=no records synthesized; absent is not a source count of zero")
    print("generated_id_policy=" + ID_POLICY)
    print("relationship_policy=integer references; assessment/customer joins only if exactly one match")
    print("preservation_policy=legacy_metadata.source_fields; exact Decimal/time values; no scale conversion")
    for source, target in LEGACY_TABLES.items():
        value = "unavailable" if counts is None or source not in counts else counts[source]
        print(f"{source}->{target}: source_count={value}")
    for label, value in sorted(schema_blockers(schema).items()):
        print(f"schema_blocker={label}; count={value}")
    if mapping:
        print(f"reviewed_mapping_sha256={mapping.fingerprint}")
        print("configured_mapping_fields=" + ",".join(sorted(mapping.fields)))
        print("configuration_policy=explicitly reviewed; source values must pass enum/range/precision checks")
    print("source_timezone_verification=" + (timezone_status or "not_performed"))
    for label, value in sorted(mapping_blockers(mapping, counts).items()):
        table = label.split(".", 1)[0]
        affected = "unavailable" if counts is None else counts.get(table, "unavailable")
        print(f"mapping_blocker={label}; count={affected}; schema_level={value}")
    for table, fields in MANDATORY_SOURCE_FIELDS.items():
        for field in fields:
            if schema.get(table, {}).get(field, {}).get("nullable") == "YES":
                print(f"nullable_required_field={table}.{field}")
    if issues is None:
        print("record_missing_conflicting_reference_counts=unavailable (metadata only)")
    else:
        for label, value in sorted(issues.items()):
            print(f"source_issue={label}; count={value}")
    print("target_identity_conflicts=not_checked; target_access=false")
    print("decimal_precision_and_timestamp_validation=not_performed (count-only review)")
    print("apply_preflight=requires approved record review, exact mapping hash, precision/model validation and target conflicts")
    print("mode=blocked; legacy_apply=false; dry_run=true; target_writes=0")
