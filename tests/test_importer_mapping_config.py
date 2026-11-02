"""Reviewed mappings tested using synthetic values and scalar-only connections."""

from argparse import Namespace
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from io import StringIO
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, MetaData, Numeric, String, Table
from sqlalchemy.dialects import mysql

from scripts import import_mysql_to_mongodb as importer
from scripts import legacy_mapping_config as configs
from scripts import mysql_schema_profiles as profiles


def config_data(fields=None):
    return {
        "version": 1, "profile": "legacy_singular_v1", "reviewed": True,
        "fields": fields or {},
        "timezone": {"session_offset": "+05:30", "evidence": "Synthetic explicitly reviewed session evidence"},
    }


def decimal_spec(source="risk_score"):
    return {
        "kind": "decimal", "source": source,
        "source_min": "0", "source_max": "1", "target_min": "0", "target_max": "100",
        "multiplier": "100", "offset": "0", "evidence": "Synthetic reviewed test scale only",
    }


def enum_spec(source, values):
    return {"kind": "enum", "source": source, "values": values, "evidence": "Synthetic reviewed enumeration"}


def test_fingerprint_is_canonical_and_changes_with_semantics():
    data = config_data({"fraud_assessment.risk_score": decimal_spec()})
    mapping = configs.validate_mapping(data)
    assert mapping.fingerprint == configs.validate_mapping(dict(reversed(list(data.items())))).fingerprint
    data["fields"]["fraud_assessment.risk_score"]["source_max"] = "0.9"
    assert mapping.fingerprint != configs.validate_mapping(data).fingerprint
    assert len(mapping.fingerprint) == 64


@pytest.mark.parametrize("change", [
    {"reviewed": False}, {"version": True}, {"profile": "modern_plural"},
    {"credentials": "private"}, {"fields": {"user.full_name": {"source": "email", "kind": "enum"}}},
    {"timezone": {"session_offset": "SYSTEM", "evidence": "synthetic"}},
    {"timezone": {"session_offset": "+14:01", "evidence": "synthetic"}},
    {"timezone": {"session_offset": "+05:60", "evidence": "synthetic"}},
])
def test_unreviewed_unknown_and_timezone_config_is_rejected(change):
    data = config_data()
    data.update(change)
    with pytest.raises(ValueError):
        configs.validate_mapping(data)


@pytest.mark.parametrize("change", [
    {"multiplier": 100}, {"offset": "NaN"}, {"source_min": "2"},
    {"target_max": "101"}, {"multiplier": "-1"}, {"offset": "Infinity"},
    {"source": "ml_prediction"}, {"evidence": ""}, {"kind": "eval"}, {"null_policy": "archive"},
])
def test_decimal_config_is_strict(change):
    spec = decimal_spec()
    spec.update(change)
    with pytest.raises(ValueError):
        configs.validate_mapping(config_data({"fraud_assessment.risk_score": spec}))


@pytest.mark.parametrize("source,expected", [
    (Decimal("0"), Decimal("0")), (Decimal("1"), Decimal("100")),
    (Decimal("0.0001"), Decimal("0.0100")), (Decimal("0.9999"), Decimal("99.9900")),
])
def test_explicit_score_mapping_preserves_exact_boundary_values(source, expected):
    spec = decimal_spec()
    with localcontext() as context:
        context.prec = 2
        assert configs.mapped_value("fraud_assessment.risk_score", spec, source) == expected


@pytest.mark.parametrize("value", [
    Decimal("-0.0001"), Decimal("1.0001"), Decimal("NaN"), Decimal("Infinity"),
    "0.5", 0.5, True, None,
])
def test_source_scores_require_finite_exact_decimal_in_reviewed_range(value):
    with pytest.raises(Exception):
        configs.mapped_value("fraud_assessment.risk_score", decimal_spec(), value)


def test_decimal_transform_does_not_silently_clamp_target_range():
    spec = decimal_spec()
    spec["multiplier"] = "101"
    with pytest.raises(ValueError, match="outside reviewed range"):
        configs.mapped_value("fraud_assessment.risk_score", spec, Decimal("1"))


def test_unrepresentable_decimal_mapping_is_blocked():
    spec = decimal_spec()
    with pytest.raises(Exception):
        configs.mapped_value(
            "fraud_assessment.risk_score", spec, Decimal("0.123456789012345678901234567890123456789")
        )


def test_severity_mapping_is_explicit_exact_enum_not_heuristic():
    spec = enum_spec("severity_level", {"8": "low", "9": "critical"})
    configs.validate_mapping(config_data({"fraud_rule.severity": spec}))
    assert configs.mapped_value("fraud_rule.severity", spec, 8) == "low"
    for value in [1, 8.0, True, "Low"]:
        with pytest.raises(ValueError):
            configs.mapped_value("fraud_rule.severity", spec, value)
    spec["values"]["1"] = "catastrophic"
    with pytest.raises(ValueError):
        configs.validate_mapping(config_data({"fraud_rule.severity": spec}))


def test_status_and_category_target_enums_are_validated():
    for field, source, target in [
        ("fraud_assessment.risk_category", "risk_level", "critical"),
        ("fraud_alert.alert_status", "alert_status", "completed"),
        ("fraud_alert.review_decision", "review_decision", "maybe"),
    ]:
        with pytest.raises(ValueError):
            configs.validate_mapping(config_data({field: enum_spec(source, {"source": target})}))


def test_optional_unknown_ml_semantics_can_be_archived_explicitly_not_exposed():
    fields = {
        f"fraud_assessment.{target}": {
            "kind": "archive", "source": source, "evidence": "Synthetic reviewed archival-only policy",
        }
        for target, source in [("ml_score", "ml_prediction"), ("ml_confidence", "ml_confidence")]
    }
    mapping = configs.validate_mapping(config_data(fields))
    assert mapping.resolves("fraud_assessment.unknown_semantics.ml_prediction_ml_confidence")
    row = {"id": 1, "transaction_id": 2, "ml_prediction": Decimal("0.75"), "ml_confidence": Decimal("0.9")}
    review = profiles.legacy_candidate(
        "fraud_assessment", row, lambda *args: [{"id": 2}], mapping
    )
    assert "ml_score" not in review.candidate
    assert review.candidate["legacy_metadata"]["source_fields"] == row
    assert not any("ml_prediction_ml_confidence" in field for field in review.blockers)
    assert review.blockers["fraud_assessment.unknown_semantics.risk_score"]


def test_required_score_cannot_be_archived_or_filled_with_constant():
    for spec in [
        {"source": "risk_score", "kind": "archive", "evidence": "synthetic"},
        {"kind": "decimal", "source": "risk_score", "constant": "0", "evidence": "synthetic"},
    ]:
        with pytest.raises(ValueError):
            configs.validate_mapping(config_data({"fraud_assessment.risk_score": spec}))


def test_config_cannot_invent_missing_names_statuses_payment_or_assignment_reviewers():
    for field in ["user.full_name", "customer.name", "transaction_record.status",
                  "transaction_record.payment_method", "fraud_alert.reviewed_by"]:
        with pytest.raises(ValueError):
            configs.validate_mapping(config_data({
                field: {"kind": "enum", "source": "email", "values": {"x": "fake"}, "evidence": "synthetic"}
            }))


def test_mapping_removes_only_resolved_blockers_and_reports_row_failures():
    mapping = configs.validate_mapping(config_data({
        "fraud_assessment.risk_score": decimal_spec(),
        "fraud_assessment.risk_category": enum_spec("risk_level", {"source-high": "HIGH"}),
    }))
    row = {"id": 1, "transaction_id": 2, "risk_score": Decimal("0.75"), "risk_level": "source-high"}
    review = profiles.legacy_candidate("fraud_assessment", row, lambda *args: [{"id": 2}], mapping)
    assert review.candidate["risk_score"] == Decimal("75")
    assert review.candidate["risk_category"] == "HIGH"
    assert "fraud_assessment.unknown_semantics.risk_score" not in review.blockers
    assert review.candidate["legacy_metadata"]["source_fields"]["risk_score"] == Decimal("0.75")
    assert review.candidate["legacy_metadata"]["mapping_sha256"] == mapping.fingerprint
    row["risk_score"] = Decimal("1.5")
    review = profiles.legacy_candidate("fraud_assessment", row, lambda *args: [{"id": 2}], mapping)
    assert review.blockers["fraud_assessment.risk_score.invalid_reviewed_mapping_value"]
    assert not review.importable


@pytest.mark.parametrize("score,category", [
    ("0", "LOW"), ("30", "LOW"), ("30.01", "MEDIUM"),
    ("31", "MEDIUM"), ("70", "MEDIUM"), ("70.01", "HIGH"),
    ("71", "HIGH"), ("100", "HIGH"),
])
def test_reviewed_score_category_mapping_agrees_with_target_boundaries(score, category):
    spec = decimal_spec()
    spec.update(source_max="100", multiplier="1")
    mapping = configs.validate_mapping(config_data({
        "fraud_assessment.risk_score": spec,
        "fraud_assessment.risk_category": enum_spec("risk_level", {category: category}),
    }))
    row = {"id": 1, "transaction_id": 2, "risk_score": Decimal(score), "risk_level": category}
    review = profiles.legacy_candidate("fraud_assessment", row, lambda *args: [{"id": 2}], mapping)
    assert "fraud_assessment.risk_category.conflicts_with_target_score" not in review.blockers
    row["risk_score"] = Decimal("100") if category != "HIGH" else Decimal("0")
    review = profiles.legacy_candidate("fraud_assessment", row, lambda *args: [{"id": 2}], mapping)
    assert review.blockers["fraud_assessment.risk_category.conflicts_with_target_score"]


def test_preserved_source_decimal_must_also_fit_bson_without_rounding():
    row = {"id": 1, "triggered_value": Decimal("0.123456789012345678901234567890123456789")}
    review = profiles.legacy_candidate("triggered_rule", row, lambda *args: [])
    assert review.blockers["triggered_rule.decimal_precision.invalid_value"]


def test_fully_reviewed_trigger_candidate_is_valid_without_target_writes(monkeypatch):
    mapping = configs.validate_mapping(config_data({
        "triggered_rule.triggered_value": {
            "kind": "archive", "source": "triggered_value", "evidence": "Synthetic reviewed archival decision",
        },
    }))
    row = {"id": 1, "transaction_id": 2, "rule_id": 3, "created_at": datetime(2020, 1, 2)}
    def lookup(table, field, value):
        return [{"id": 4}] if table == "fraud_assessment" else [{"id": value}]
    monkeypatch.setattr(importer, "get_database", lambda: pytest.fail("No target writes"))
    review = profiles.legacy_candidate("triggered_rule", row, lookup, mapping)
    assert review.importable
    assert review.candidate["assessment_id"] == 4
    assert "rule_explanation" not in review.candidate  # no model defaults serialized


def test_verified_timezone_converts_only_target_fields_preserving_source_precision():
    mapping = configs.validate_mapping(config_data())
    source = datetime(2020, 1, 2, 5, 30, 0, 123456)
    review = profiles.legacy_candidate(
        "transaction_record", {"id": 1, "transaction_date": source}, lambda *args: [], mapping
    )
    assert review.candidate["transaction_date"] == datetime(2020, 1, 2, 0, 0, 0, 123456, tzinfo=timezone.utc)
    metadata = review.candidate["legacy_metadata"]
    assert metadata["source_fields"]["transaction_date"] == source
    assert metadata["source_timestamps"]["transaction_date"] == source.isoformat()


@pytest.mark.parametrize("session,expected", [
    ("+05:30", "verified"), ("SYSTEM", "unverified_session_offset"),
    ("UTC", "unverified_session_offset"), ("+00:00", "unverified_session_offset"),
])
def test_session_offset_must_match_not_global_or_host_timezone(session, expected):
    class Connection:
        def execute(self, statement):
            assert str(statement) == (
                "SELECT @@session.time_zone AS session_zone, "
                "@@global.time_zone AS global_zone, @@system_time_zone AS system_zone"
            )
            return self

        def mappings(self):
            return self

        def one(self):
            return {"session_zone": session, "global_zone": "+05:30", "system_zone": "private-host-zone"}

    assert profiles.check_session_timezone(Connection(), configs.validate_mapping(config_data())) == expected


def test_empty_tables_do_not_have_irrelevant_semantic_blockers():
    counts = {table: 0 for table in profiles.LEGACY_TABLES}
    assert not profiles.mapping_blockers(counts=counts)
    counts["customer"] = 1
    issues = profiles.mapping_blockers(counts=counts)
    assert set(issues) == {"customer.unverified_default.risk_profile", "legacy.unknown_semantics.source_timezone"}
    assert profiles.mapping_blockers(counts=None)["fraud_rule.unknown_semantics.risk_weight"]


def test_mapping_review_queries_are_aggregate_only():
    metadata = MetaData()
    table = Table("fraud_assessment", metadata, Column("id", Integer),
                  Column("risk_score", Numeric(5, 2)), Column("risk_level", String))
    mapping = configs.validate_mapping(config_data({
        "fraud_assessment.risk_score": decimal_spec(),
        "fraud_assessment.risk_category": enum_spec("risk_level", {"source-high": "HIGH"}),
    }))

    class Connection:
        statements = []

        def execute(self, statement):
            sql = str(statement.compile(dialect=mysql.dialect()))
            assert sql.startswith("SELECT count(")
            self.statements.append(sql)
            return type("Scalar", (), {"scalar_one": lambda self: 2})()

    connection = Connection()
    issues = profiles.count_mapping_issues(connection, {"fraud_assessment": table}, mapping)
    assert issues["fraud_assessment.risk_score.invalid_reviewed_mapping_values"] == 2
    assert issues["fraud_assessment.risk_category.invalid_reviewed_mapping_values"] == 2
    assert any("NOT IN" in sql for sql in connection.statements)
    assert any("risk_score *" in sql for sql in connection.statements)


def test_mapping_reader_rejects_duplicate_keys_and_oversize_without_files(monkeypatch):
    for text in ['{"version":1,"version":1}', " " * 65537]:
        monkeypatch.setattr(Path, "open", lambda *args, text=text, **kwargs: StringIO(text))
        with pytest.raises(ValueError):
            configs.read_mapping(Path("synthetic.json"))


def test_mapping_errors_never_echo_values_paths_or_evidence(monkeypatch, capsys):
    monkeypatch.setattr(importer, "parse_args", lambda: Namespace(mapping_config="private-path.json"))
    def failure(path):
        raise ValueError("private-reference-source-content")
    monkeypatch.setattr(importer, "read_mapping", failure)
    monkeypatch.setattr(importer, "get_database", lambda: pytest.fail("No database access"))
    monkeypatch.setattr(importer, "create_engine", lambda *args, **kwargs: pytest.fail("No source access"))
    assert importer.run() == 1
    output = capsys.readouterr().err
    assert "stage=mapping_configuration" in output
    assert "private" not in output


def test_partial_mapping_report_has_fingerprint_and_only_remaining_unknowns(capsys):
    mapping = configs.validate_mapping(config_data({"fraud_rule.severity": enum_spec("severity_level", {"8": "low"})}))
    profiles.report_legacy({}, counts={"fraud_rule": 2}, mapping=mapping)
    output = capsys.readouterr().out
    assert "reviewed_mapping_sha256=" + mapping.fingerprint in output
    assert "mapping_blocker=fraud_rule.unknown_semantics.severity_level" not in output
    assert "mapping_blocker=fraud_rule.unknown_semantics.risk_weight; count=2" in output
    assert "Synthetic" not in output
    assert "target_writes=0" in output
    assert "mode=blocked" in output
