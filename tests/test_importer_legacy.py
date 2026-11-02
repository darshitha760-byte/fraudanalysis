"""Synthetic-only importer tests; no SQL server, record export or target access."""

from argparse import Namespace
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table
from sqlalchemy.dialects import mysql

from scripts import import_mysql_to_mongodb as importer
from scripts import mysql_schema_profiles as profiles


@pytest.fixture
def schema():
    return {
        table: {
            field: {
                "type": "int" if field == "id" else "varchar(255)",
                "nullable": "NO" if field == "id" else "YES",
                "key": "PRI" if field == "id" else "",
            }
            for field in fields.split()
        }
        for table, fields in profiles.LEGACY_COLUMNS.items()
    }


def lookup_for(records):
    def lookup(table, field, value):
        return [row for row in records.get(table, []) if row.get(field) == value][:2]
    return lookup


@pytest.mark.parametrize(
    ("tables", "expected"),
    [
        (list(profiles.LEGACY_TABLES), "legacy_singular_v1"),
        (["customer"], "legacy_singular_v1"),
        (list(importer.TABLES), "modern_plural"),
        (["users", "customer"], "mixed"),
        (list(importer.TABLES) + ["fraud_alert"], "mixed"),
        (["unrelated-private-table"], "modern_plural"),
    ],
)
def test_profile_detection(tables, expected):
    assert profiles.detect_profile(tables, importer.TABLES) == expected


def test_metadata_schema_blockers_and_integer_identity(schema):
    assert not profiles.schema_blockers(schema)
    del schema["user"]["email"]
    schema["customer"]["id"]["type"] = "decimal(10,0)"
    del schema["audit_log"]
    problems = profiles.schema_blockers(schema)
    assert problems["user.email.missing_column"] == 1
    assert problems["customer.id.invalid_integer_primary_key"] == 1
    assert problems["audit_log.missing_table"] == 1


def test_metadata_reader_is_bounded_and_rejects_record_csv(monkeypatch):
    from io import StringIO
    from pathlib import Path

    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: StringIO("email,password\nprivate,secret\n"))
    with pytest.raises(ValueError, match="Unsupported metadata header"):
        profiles.read_schema_csv(Path("synthetic.csv"))
    header = "TABLE_NAME,COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_KEY\n"
    text = header + "".join(f"user,column{i},int,NO,\n" for i in range(1001))
    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: StringIO(text))
    with pytest.raises(ValueError, match="oversized"):
        profiles.read_schema_csv(Path("synthetic.csv"))


def test_metadata_csv_parses_quoted_decimal_and_enum(monkeypatch):
    from io import StringIO
    from pathlib import Path

    text = (
        "TABLE_NAME,COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_KEY\n"
        'fraud_assessment,risk_score,"decimal(5,2)",YES,\n'
        'user,role,"enum(\'Admin\',\'Analyst\',\'Viewer\')",NO,MUL\n'
    )
    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: StringIO(text))
    result = profiles.read_schema_csv(Path("synthetic.csv"))
    assert result["fraud_assessment"]["risk_score"]["type"] == "decimal(5,2)"
    assert result["user"]["role"]["nullable"] == "NO"


@pytest.mark.parametrize("external", [None, ""])
def test_missing_customer_external_id_has_deterministic_table_prefix(external):
    row = {"id": 7, "external_id": external, "first_name": "Test", "last_name": "Fixture"}
    review = profiles.legacy_candidate("customer", row, lookup_for({}))
    assert review.candidate["customer_id"] == "legacy-customer-7"
    assert review.candidate["id"] == 7
    assert review.candidate["name"] == "Test Fixture"
    assert review.candidate["legacy_metadata"]["source_fields"] == row
    assert not review.importable


def test_external_customer_id_is_preserved():
    row = {"id": 7, "external_id": "provided-id", "first_name": "Test", "last_name": "Fixture"}
    assert profiles.legacy_candidate("customer", row, lookup_for({})).candidate["customer_id"] == "provided-id"


@pytest.mark.parametrize("names", [(None, None), ("Test", None), (None, "Fixture"), (" ", "Fixture")])
def test_missing_customer_names_block_without_placeholder(names):
    review = profiles.legacy_candidate(
        "customer", {"id": 1, "first_name": names[0], "last_name": names[1]}, lookup_for({})
    )
    assert "name" not in review.candidate
    assert review.blockers["customer.name.missing_required_value"]


@pytest.mark.parametrize("role,expected", list(profiles.ROLE_MAP.items()))
def test_roles_are_explicit_but_user_full_name_is_not_invented(role, expected):
    review = profiles.legacy_candidate(
        "user", {"id": 4, "role": role, "email": "synthetic@example.test", "is_active": 1},
        lookup_for({}),
    )
    assert review.candidate["role"] == expected
    assert "full_name" not in review.candidate
    assert review.blockers["user.required_mapping.full_name"]


def test_unknown_role_and_boolean_are_blocked_not_coerced():
    review = profiles.legacy_candidate(
        "user", {"id": 4, "role": "Root", "is_active": 2}, lookup_for({})
    )
    assert "role" not in review.candidate
    assert "is_active" not in review.candidate
    assert review.blockers["user.role.unrecognized_enum"]


def test_transaction_preserves_decimal_time_and_reference_without_defaults():
    now = datetime(2020, 3, 4, 5, 6, 7, 123456)
    row = {
        "id": 23, "customer_id": 7, "amount": Decimal("1234567890.12"),
        "transaction_date": now, "location_latitude": Decimal("12.12345678"),
        "currency": "EUR", "is_synthetic": 0, "transaction_type": "source-type",
    }
    review = profiles.legacy_candidate(
        "transaction_record", row, lookup_for({"customer": [{"id": 7}]})
    )
    document = importer.normalize(review.candidate)
    assert document["transaction_id"] == "legacy-transaction_record-23"
    assert document["customer_id"] == 7
    assert document["amount"].to_decimal() == row["amount"]
    assert document["transaction_date"] == now.replace(tzinfo=timezone.utc)
    assert document["legacy_metadata"]["source_timestamps"]["transaction_date"] == now.isoformat()
    assert document["legacy_metadata"]["source_fields"]["location_latitude"].to_decimal() == row["location_latitude"]
    assert "status" not in document and "payment_method" not in document
    assert "transaction_record.customer_id.missing_reference" not in review.blockers
    assert review.blockers["transaction_record.required_mapping.status"]
    assert review.blockers["transaction_record.required_mapping.payment_method"]
    assert importer.precision_issues(row) == 0


@pytest.mark.parametrize("identity", [None, "1", True, Decimal("1")])
def test_non_integer_identity_cannot_generate_id(identity):
    review = profiles.legacy_candidate("transaction_record", {"id": identity}, lookup_for({}))
    assert "transaction_id" not in review.candidate
    assert review.blockers["transaction_record.id.invalid_integer_identity"]


@pytest.mark.parametrize("table", ["fraud_alert", "triggered_rule"])
@pytest.mark.parametrize("assessment_ids", [[], [41, 42]])
def test_missing_or_ambiguous_assessment_join_is_blocked(table, assessment_ids):
    records = {
        "fraud_assessment": [{"id": identity, "transaction_id": 23} for identity in assessment_ids],
        "transaction_record": [{"id": 23, "customer_id": 7}],
        "customer": [{"id": 7}], "fraud_rule": [{"id": 5}],
    }
    review = profiles.legacy_candidate(
        table, {"id": 1, "transaction_id": 23, "rule_id": 5}, lookup_for(records)
    )
    assert "assessment_id" not in review.candidate
    kind = "ambiguous" if assessment_ids else "missing"
    assert review.blockers[f"{table}.assessment_id.{kind}_reference"]


def test_unique_relationships_preserve_integer_ids():
    records = {
        "fraud_assessment": [{"id": 41, "transaction_id": 23}],
        "transaction_record": [{"id": 23, "customer_id": 7}],
        "customer": [{"id": 7}], "fraud_rule": [{"id": 5}],
    }
    alert = profiles.legacy_candidate(
        "fraud_alert", {"id": 9, "transaction_id": 23}, lookup_for(records)
    )
    trigger = profiles.legacy_candidate(
        "triggered_rule", {"id": 10, "transaction_id": 23, "rule_id": 5}, lookup_for(records)
    )
    assert alert.candidate["assessment_id"] == trigger.candidate["assessment_id"] == 41
    assert alert.candidate["customer_id"] == 7
    assert trigger.candidate["rule_id"] == 5
    assert not alert.importable and not trigger.importable


def test_ambiguous_customer_and_missing_rule_are_blocked():
    records = {
        "transaction_record": [{"id": 23, "customer_id": 7}],
        "customer": [{"id": 7}, {"id": 7}],
        "fraud_assessment": [{"id": 41, "transaction_id": 23}],
    }
    alert = profiles.legacy_candidate("fraud_alert", {"id": 1, "transaction_id": 23}, lookup_for(records))
    assert "customer_id" not in alert.candidate
    assert alert.blockers["fraud_alert.customer_id.ambiguous_reference"]
    trigger = profiles.legacy_candidate(
        "triggered_rule", {"id": 2, "transaction_id": 23, "rule_id": 5}, lookup_for(records)
    )
    assert trigger.blockers["triggered_rule.rule_id.missing_reference"]


@pytest.mark.parametrize(
    "table,row,unmapped",
    [
        ("fraud_rule", {"id": 5, "risk_weight": Decimal("0.250"), "severity_level": 3, "operator": ">"},
         ("risk_weight", "severity")),
        ("fraud_assessment", {"id": 6, "risk_score": Decimal("0.75"), "risk_level": "HIGH"},
         ("risk_score", "risk_category")),
        ("fraud_alert", {"id": 7, "risk_score": Decimal("75.00"), "alert_status": "Closed", "assigned_to": 4},
         ("risk_score", "alert_status", "reviewed_by", "alert_severity")),
    ],
)
def test_unknown_semantics_preserved_only_as_legacy_metadata(table, row, unmapped):
    review = profiles.legacy_candidate(table, row, lookup_for({}))
    assert review.candidate["legacy_metadata"]["source_fields"] == row
    assert all(field not in review.candidate for field in unmapped)
    assert any("unknown_semantics" in issue for issue in review.blockers)
    assert not review.importable


def test_count_review_uses_only_aggregate_sql(schema):
    metadata = MetaData()
    tables = {
        name: Table(
            name, metadata,
            *(Column(field, Integer if field in {"id", "transaction_id", "customer_id", "rule_id", "actor_id", "assigned_to"} else String)
              for field in columns),
        )
        for name, columns in schema.items()
    }

    class AggregateConnection:
        statements = []

        def execute(self, statement):
            sql = str(statement.compile(dialect=mysql.dialect()))
            self.statements.append(sql)
            # Synthetic scalar response, not SQL emulation or a source database.
            value = 2 if "fraud_alert" in sql and "anon_1.n >" in sql else 0
            assert all("count(" in str(column).lower() or "sum(" in str(column).lower()
                       for column in statement.selected_columns)
            return type("Scalar", (), {"scalar_one": lambda self: value})()

    connection = AggregateConnection()
    counts, issues = profiles.count_legacy_issues(connection, tables)
    assert set(counts) == set(profiles.LEGACY_TABLES)
    assert issues["fraud_alert.assessment_id.ambiguous_reference"] == 2
    assert "customer.generated_customer_id.conflicting_records" in issues
    assert "fraud_alert.customer_id.missing_reference" in issues
    assert all("SELECT" in sql and ("count(" in sql or "sum(" in sql) for sql in connection.statements)


def forbid_target(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("No target access, initialization or writes permitted")
    monkeypatch.setattr(importer, "get_database", forbidden)
    monkeypatch.setattr(importer, "initialize_database", forbidden)


def test_offline_schema_review_has_no_connections_or_settings(monkeypatch, capsys, schema):
    monkeypatch.setattr(importer, "parse_args", lambda: Namespace(
        schema_csv="synthetic.csv", apply=False, confirm_target=None
    ))
    monkeypatch.setattr(importer, "read_schema_csv", lambda path: schema)
    forbid_target(monkeypatch)
    monkeypatch.setattr(importer, "get_settings", lambda: pytest.fail("No settings loading"))
    monkeypatch.setattr(importer, "create_engine", lambda *args, **kwargs: pytest.fail("No SQL access"))
    assert importer.run() == 1
    output = capsys.readouterr().out
    assert "schema_profile=legacy_singular_v1" in output
    assert "legacy_absent_case_tables=investigation_cases,case_notes" in output
    assert "record_missing_conflicting_reference_counts=unavailable" in output
    assert "unknown_semantics.risk_score" in output
    assert "target_writes=0" in output
    assert "mode=blocked" in output


@pytest.mark.parametrize("apply", [False, True])
def test_live_legacy_review_is_count_only_and_always_blocks_apply(monkeypatch, capsys, schema, apply):
    from scripts.legacy_mapping_config import validate_mapping

    mapping = validate_mapping({
        "version": 1, "profile": "legacy_singular_v1", "reviewed": True,
        "fields": {}, "timezone": {"session_offset": "+00:00", "evidence": "synthetic session metadata"},
    })
    class Inspector:
        def get_table_names(self):
            return list(schema)

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class Engine:
        disposed = False

        def connect(self):
            return Connection()

        def dispose(self):
            self.disposed = True

    engine = Engine()
    monkeypatch.setattr(importer, "parse_args", lambda: Namespace(
        schema_csv=None, apply=apply, confirm_target="synthetic" if apply else None, batch_size=2,
        mapping_config="synthetic.json" if apply else None, confirm_mapping=mapping.fingerprint if apply else None,
    ))
    monkeypatch.setattr(importer, "read_mapping", lambda *args: mapping)
    monkeypatch.setattr(importer, "count_mapping_issues", lambda *args: Counter())
    monkeypatch.setattr(importer, "check_session_timezone", lambda *args: "verified")
    monkeypatch.setenv("MYSQL_IMPORT_URL", "private-uri")
    monkeypatch.setattr(importer, "get_settings", lambda: Namespace(mongodb_database="synthetic"))
    monkeypatch.setattr(importer, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(importer, "inspect", lambda connection: Inspector())
    monkeypatch.setattr(importer, "reflected_schema", lambda *args: schema)
    monkeypatch.setattr(importer, "Table", lambda name, *args, **kwargs: name)
    monkeypatch.setattr(importer, "count_legacy_issues", lambda *args: (
        {table: 3 for table in schema}, Counter({"fraud_alert.assessment_id.ambiguous_reference": 2})
    ))
    monkeypatch.setattr(importer, "source_batches", lambda *args: pytest.fail("No record reads"))
    forbid_target(monkeypatch)
    assert importer.run() == 1
    output = capsys.readouterr()
    assert "source_count=3" in output.out
    assert "ambiguous_reference; count=2" in output.out
    assert "legacy_apply=false" in output.out
    assert "private" not in output.out + output.err
    assert engine.disposed


def test_offline_bad_metadata_failure_omits_private_details(monkeypatch, capsys):
    monkeypatch.setattr(importer, "parse_args", lambda: Namespace(
        schema_csv="private-path.csv", apply=False, confirm_target=None
    ))
    def fail(path):
        raise ValueError("private-source-record")
    monkeypatch.setattr(importer, "read_schema_csv", fail)
    forbid_target(monkeypatch)
    assert importer.run() == 1
    error = capsys.readouterr().err
    assert "stage=metadata_schema" in error
    assert "private" not in error


def test_reports_never_echo_unallowlisted_metadata(schema, capsys):
    schema["private-table"] = {"private-column": {"type": "private-content"}}
    profiles.report_legacy(schema)
    assert "private" not in capsys.readouterr().out


def test_missing_legacy_table_is_reported_not_silently_skipped(schema, capsys):
    del schema["audit_log"]
    profiles.report_legacy(schema)
    output = capsys.readouterr().out
    assert "schema_blocker=audit_log.missing_table; count=1" in output
    assert "audit_log->audit_logs: source_count=unavailable" in output
    assert "mode=blocked" in output


def test_offline_apply_cannot_bypass_confirmation(monkeypatch):
    monkeypatch.setattr(importer, "parse_args", lambda: Namespace(
        apply=True, confirm_target="synthetic", schema_csv="synthetic.csv"
    ))
    monkeypatch.setattr(importer, "read_schema_csv", lambda path: pytest.fail("Cannot start review"))
    forbid_target(monkeypatch)
    assert importer.run() == 2


@pytest.mark.parametrize("apply,confirmation", [(True, None), (False, "synthetic")])
def test_existing_confirmation_gate_blocks_before_source_access(monkeypatch, apply, confirmation):
    monkeypatch.setattr(importer, "parse_args", lambda: Namespace(
        apply=apply, confirm_target=confirmation, schema_csv=None
    ))
    monkeypatch.setenv("MYSQL_IMPORT_URL", "private-uri")
    monkeypatch.setattr(importer, "get_settings", lambda: Namespace(mongodb_database="synthetic"))
    monkeypatch.setattr(importer, "create_engine", lambda *args, **kwargs: pytest.fail("No source access"))
    forbid_target(monkeypatch)
    assert importer.run() == 2


def test_modern_dry_run_preserves_documents_and_never_initializes(monkeypatch, capsys):
    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class Engine:
        def connect(self):
            return Connection()

        def dispose(self):
            pass

    class Inspector:
        def get_table_names(self):
            return list(importer.TABLES)

    class Collection:
        def count_documents(self, query):
            return 0

        def find_one(self, query):
            return None

        def insert_many(self, *args, **kwargs):
            pytest.fail("Dry run must never write")

    class Target:
        def __getitem__(self, name):
            return Collection()

    monkeypatch.setattr(importer, "parse_args", lambda: Namespace(
        apply=False, confirm_target=None, schema_csv=None, batch_size=2
    ))
    monkeypatch.setenv("MYSQL_IMPORT_URL", "private-uri")
    monkeypatch.setattr(importer, "get_settings", lambda: Namespace(mongodb_database="synthetic"))
    monkeypatch.setattr(importer, "create_engine", lambda *args, **kwargs: Engine())
    monkeypatch.setattr(importer, "inspect", lambda *args: Inspector())
    monkeypatch.setattr(importer, "Table", lambda name, *args, **kwargs: name)
    monkeypatch.setattr(importer, "source_counts", lambda *args: {name: 1 for name in importer.TABLES})
    monkeypatch.setattr(importer, "check_references", lambda *args: {})
    monkeypatch.setattr(importer, "source_batches", lambda *args: [[{"id": 1, "amount": Decimal("1.20")}]])
    monkeypatch.setattr(importer, "get_database", lambda: Target())
    monkeypatch.setattr(importer, "initialize_database", lambda *args: pytest.fail("No initialization"))
    assert importer.run() == 0
    assert "dry_run=true; no target documents were written." in capsys.readouterr().out


def test_modern_apply_and_rerun_remain_append_only_with_synthetic_target(monkeypatch):
    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class Engine:
        def connect(self):
            return Connection()

        def dispose(self):
            pass

    class Inspector:
        def get_table_names(self):
            return list(importer.TABLES)

    class Collection:
        def __init__(self):
            self.documents = []
            self.inserts = 0
            self.sequence_updates = 0

        def count_documents(self, query):
            return len(self.documents)

        def find_one(self, query, **kwargs):
            if kwargs.get("sort"):
                return max(self.documents, key=lambda doc: doc["id"]) if self.documents else None
            return next((doc for doc in self.documents if all(doc.get(key) == value for key, value in query.items())), None)

        def insert_many(self, documents, **kwargs):
            assert kwargs == {"ordered": True}
            self.documents.extend(documents)
            self.inserts += len(documents)

        def update_one(self, query, update, **kwargs):
            assert set(update) == {"$max"}
            assert kwargs == {"upsert": True}
            self.sequence_updates += 1

    target = {name: Collection() for name in (*importer.TABLES, "_id_sequences")}
    initialized = []
    monkeypatch.setattr(importer, "parse_args", lambda: Namespace(
        apply=True, confirm_target="synthetic", schema_csv=None, batch_size=2
    ))
    monkeypatch.setenv("MYSQL_IMPORT_URL", "synthetic-uri")
    monkeypatch.setattr(importer, "get_settings", lambda: Namespace(mongodb_database="synthetic"))
    monkeypatch.setattr(importer, "create_engine", lambda *args, **kwargs: Engine())
    monkeypatch.setattr(importer, "inspect", lambda *args: Inspector())
    monkeypatch.setattr(importer, "Table", lambda name, *args, **kwargs: name)
    monkeypatch.setattr(importer, "source_counts", lambda *args: {name: 1 for name in importer.TABLES})
    monkeypatch.setattr(importer, "check_references", lambda *args: {})
    monkeypatch.setattr(importer, "source_batches", lambda *args: [[{"id": 1, "amount": Decimal("1.20")}]])
    monkeypatch.setattr(importer, "get_database", lambda: target)
    monkeypatch.setattr(importer, "initialize_database", lambda db: initialized.append(db))
    assert importer.run() == 0
    assert importer.run() == 0
    assert len(initialized) == 2
    assert all(target[name].inserts == 1 for name in importer.TABLES)
    assert target["_id_sequences"].sequence_updates == 20
