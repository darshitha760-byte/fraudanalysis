"""Nonsecret, explicitly reviewed legacy semantics; no guessed source defaults."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, Inexact, InvalidOperation, Rounded, localcontext
from pathlib import Path
from typing import Any, Mapping

from bson.decimal128 import Decimal128


# A mapping must reference the corresponding source field, not an unrelated
# column that happens to have the right type (email is not a person's name).
FIELDS = {
    "customer.risk_profile": (None, "enum", None),
    "fraud_rule.severity": ("severity_level", "enum", {"low", "medium", "high", "critical"}),
    "fraud_rule.risk_weight": ("risk_weight", "decimal", None),
    "fraud_assessment.risk_score": ("risk_score", "decimal", None),
    "fraud_assessment.risk_category": ("risk_level", "enum", {"LOW", "MEDIUM", "HIGH"}),
    "fraud_assessment.ml_score": ("ml_prediction", "decimal", None),
    "fraud_assessment.ml_confidence": ("ml_confidence", "archive", None),
    "triggered_rule.triggered_value": ("triggered_value", "archive", None),
    "fraud_alert.risk_score": ("risk_score", "decimal", None),
    "fraud_alert.alert_status": ("alert_status", "enum", {"pending", "under_review", "resolved", "dismissed"}),
    "fraud_alert.review_decision": (
        "review_decision", "enum", {"approved", "rejected", "needs_review", "dismissed", "escalated"},
    ),
    "fraud_alert.assigned_to": ("assigned_to", "archive", None),
    "fraud_alert.alert_severity": (None, "enum", {"low", "medium", "high", "critical"}),
    "audit_log.action_category": ("action", "enum", None),
    "audit_log.target_type": ("target_entity", "enum", None),
    "audit_log.action_status": (None, "enum", {"success", "failure"}),
    "audit_log.target_id": ("target_id", "archive", None),
}
RESOLUTIONS = {
    "customer.unverified_default.risk_profile": ("customer.risk_profile",),
    "fraud_rule.unknown_semantics.severity_level": ("fraud_rule.severity",),
    "fraud_rule.unknown_semantics.risk_weight": ("fraud_rule.risk_weight",),
    "fraud_assessment.unknown_semantics.risk_score": ("fraud_assessment.risk_score",),
    "fraud_assessment.unknown_semantics.risk_level_to_risk_category": ("fraud_assessment.risk_category",),
    "fraud_assessment.unknown_semantics.ml_prediction_ml_confidence": (
        "fraud_assessment.ml_score", "fraud_assessment.ml_confidence",
    ),
    "triggered_rule.unverified_mapping.triggered_value": ("triggered_rule.triggered_value",),
    "fraud_alert.unknown_semantics.risk_score": ("fraud_alert.risk_score",),
    "fraud_alert.required_mapping.alert_severity": ("fraud_alert.alert_severity",),
    "fraud_alert.unknown_semantics.alert_status_review_decision_assigned_to": (
        "fraud_alert.alert_status", "fraud_alert.review_decision", "fraud_alert.assigned_to",
    ),
    "audit_log.required_mapping.action_category": ("audit_log.action_category",),
    "audit_log.required_mapping.target_type": ("audit_log.target_type",),
    "audit_log.unverified_default.action_status": ("audit_log.action_status",),
    "audit_log.unverified_mapping.target_id": ("audit_log.target_id",),
}
ARCHIVABLE = {
    "fraud_assessment.ml_score", "fraud_assessment.ml_confidence",
    "fraud_alert.risk_score", "fraud_alert.review_decision", "fraud_alert.assigned_to",
    "triggered_rule.triggered_value", "audit_log.target_id",
}
OFFSET = re.compile(r"^([+-])(\d{2}):(\d{2})$")


def checked_offset(value: Any) -> timezone:
    match = OFFSET.fullmatch(value) if isinstance(value, str) else None
    if not match:
        raise ValueError("A verified numeric session offset is required")
    hours, minutes = int(match[2]), int(match[3])
    if minutes > 59 or hours > 14 or (hours == 14 and minutes):
        raise ValueError("Invalid source timezone offset")
    delta = timedelta(hours=hours, minutes=minutes)
    return timezone(delta if match[1] == "+" else -delta)


def decimal_text(value: Any) -> Decimal:
    if not isinstance(value, str) or len(value) > 100:
        raise ValueError("Exact decimal strings required")
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise ValueError("Invalid decimal mapping") from None
    if not result.is_finite():
        raise ValueError("Nonfinite decimal mapping")
    return result


def proof(value: Any) -> bool:
    # References are never printed. Do not accept an empty assertion as evidence.
    return isinstance(value, str) and 1 <= len(value.strip()) <= 500


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate mapping key")
        result[key] = value
    return result


@dataclass(frozen=True)
class ReviewedMapping:
    fields: Mapping[str, Mapping[str, Any]]
    source_timezone: timezone | None
    timezone_offset: str | None
    fingerprint: str

    def resolves(self, issue: str) -> bool:
        if issue == "legacy.unknown_semantics.source_timezone":
            return self.source_timezone is not None
        required = RESOLUTIONS.get(issue)
        return bool(required) and all(field in self.fields for field in required)


def validate_mapping(data: Any) -> ReviewedMapping:
    if (
        not isinstance(data, dict)
        or set(data) - {"version", "profile", "reviewed", "fields", "timezone"}
        or type(data.get("version")) is not int or data["version"] != 1
        or data.get("profile") != "legacy_singular_v1"
        or data.get("reviewed") is not True
        or not isinstance(data.get("fields"), dict)
    ):
        raise ValueError("Unsupported or unreviewed mapping")
    fields = {}
    for name, spec in data["fields"].items():
        if name not in FIELDS or not isinstance(spec, dict) or not proof(spec.get("evidence")):
            raise ValueError("Unknown mapping field or missing evidence")
        source, kind, allowed = FIELDS[name]
        if spec.get("kind") == "archive" and name in ARCHIVABLE:
            kind = "archive"
        permitted = {"kind", "source", "evidence", "null_policy"}
        if kind == "enum":
            permitted |= {"values"}
        elif kind == "decimal":
            permitted |= {"source_min", "source_max", "target_min", "target_max", "multiplier", "offset"}
        if set(spec) - permitted or spec.get("kind") != kind or spec.get("source") != source:
            raise ValueError("Unsupported mapping operation")
        # Missing source fields cannot be manufactured by a constant mapping.
        if source is None:
            raise ValueError("Field requires source enrichment or separate archival handling")
        if spec.get("null_policy", "block") not in {"block", "archive"}:
            raise ValueError("Unsupported null policy")
        nullable_target = name in {
            "fraud_assessment.ml_score", "fraud_alert.risk_score",
            "fraud_alert.review_decision",
        } or kind == "archive"
        if spec.get("null_policy") == "archive" and not nullable_target:
            raise ValueError("Mandatory target fields cannot discard nulls")
        if kind == "enum":
            values = spec.get("values")
            if (
                not isinstance(values, dict) or not values or len(values) > 100
                or any(not isinstance(key, str) or len(key) > 100 for key in values)
                or any(not isinstance(value, str) or not value.strip() or len(value) > 100
                       for value in values.values())
                or allowed is not None and not set(values.values()).issubset(allowed)
            ):
                raise ValueError("Invalid enum mapping")
        elif kind == "decimal":
            for key in ("source_min", "source_max", "target_min", "target_max", "multiplier", "offset"):
                if key not in spec:
                    raise ValueError("Explicit decimal range and transform required")
                decimal_text(spec[key])
            if (
                decimal_text(spec["source_min"]) > decimal_text(spec["source_max"])
                or decimal_text(spec["target_min"]) > decimal_text(spec["target_max"])
                or decimal_text(spec["multiplier"]) <= 0
            ):
                raise ValueError("Invalid decimal range or multiplier")
            target_low, target_high = decimal_text(spec["target_min"]), decimal_text(spec["target_max"])
            ceiling = Decimal("1") if name == "fraud_assessment.ml_score" else Decimal("100")
            if target_low < 0 or name != "fraud_rule.risk_weight" and target_high > ceiling:
                raise ValueError("Mapping exceeds target scoring range")
        fields[name] = dict(spec)
    zone = data.get("timezone")
    source_timezone, offset = None, None
    if zone is not None:
        if not isinstance(zone, dict) or set(zone) != {"session_offset", "evidence"} or not proof(zone["evidence"]):
            raise ValueError("Invalid timezone mapping")
        offset = zone["session_offset"]
        source_timezone = checked_offset(offset)
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return ReviewedMapping(fields, source_timezone, offset, hashlib.sha256(canonical.encode()).hexdigest())


def read_mapping(path: Path) -> ReviewedMapping:
    # Bounded, non-executable JSON; no interpolated environment variables,
    # credentials, scripts, database addresses, or per-person data supported.
    with path.open(encoding="utf-8-sig") as stream:
        text = stream.read(65537)
    if len(text) > 65536:
        raise ValueError("Oversized mapping")
    data = json.loads(text, object_pairs_hook=no_duplicate_keys)
    return validate_mapping(data)


def mapped_value(name: str, spec: Mapping[str, Any], value: Any):
    if value is None or value == "":
        if spec.get("null_policy") == "archive" or spec["kind"] == "archive":
            return None
        raise ValueError("Missing required mapping value")
    if spec["kind"] == "archive":
        return None
    if spec["kind"] == "enum":
        if type(value) is int:
            key = str(value)
        elif isinstance(value, str):
            key = value
        else:
            raise ValueError("Invalid enum source type")
        if key not in spec["values"]:
            raise ValueError("Unmapped enum value")
        return spec["values"][key]
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("Source score must be finite exact Decimal")
    low, high = decimal_text(spec["source_min"]), decimal_text(spec["source_max"])
    if not low <= value <= high:
        raise ValueError("Source score outside reviewed range")
    # Do not inherit a caller's low-precision context or silently round.
    with localcontext() as context:
        context.prec = 256
        context.traps[Inexact] = True
        context.traps[Rounded] = True
        transformed = value * decimal_text(spec["multiplier"]) + decimal_text(spec["offset"])
    if not decimal_text(spec["target_min"]) <= transformed <= decimal_text(spec["target_max"]):
        raise ValueError("Mapped score outside reviewed range")
    if Decimal128(transformed).to_decimal() != transformed:
        raise ValueError("Mapped score not exactly representable")
    return transformed


def convert_timestamps(value: Any, source_timezone: timezone) -> Any:
    if isinstance(value, datetime):
        aware = value.replace(tzinfo=source_timezone) if value.tzinfo is None else value
        return aware.astimezone(timezone.utc)
    if isinstance(value, dict):
        return {key: convert_timestamps(item, source_timezone) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [convert_timestamps(item, source_timezone) for item in value]
    return value
