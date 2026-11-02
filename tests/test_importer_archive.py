"""Archive preparation uses synthetic records and in-memory targets only."""

from argparse import Namespace
from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import Column, Integer, MetaData, Table

from scripts import import_mysql_to_mongodb as importer
from scripts import legacy_archive as archive
from scripts import mysql_schema_profiles as profiles


def test_archive_exact_decimal_and_unknown_datetime_are_not_operational():
    now = datetime(2020, 1, 2, 3, 4, 5, 123456)
    row = {"id": 7, "risk_score": Decimal("0.7500"), "created_at": now,
           "time": timedelta(days=-1, seconds=12, microseconds=34)}
    document, omitted, size = archive.archive_document("fraud_assessment", row)
    assert document["source_fields"]["risk_score"].to_decimal().as_tuple() == row["risk_score"].as_tuple()
    assert document["source_fields"]["created_at"] == {
        "archive_type": "datetime", "exact_text": now.isoformat(), "timezone": "unknown"
    }
    assert document["source_fields"]["time"]["microseconds"] == 34
    assert document["source_timezone"] == "unknown_not_normalized"
    assert "risk_score" not in document and "assessment_timestamp" not in document
    assert document["_id"] == document["source_id"] == 7
    assert size > 0 and not omitted


def test_explicit_offset_and_decimal_outside_bson_preserve_exact_text():
    value = Decimal("0.123456789012345678901234567890123456789")
    now = datetime(2020, 1, 2, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    document, _, _ = archive.archive_document("audit_log", {"id": 1, "number": value, "created_at": now})
    assert document["source_fields"]["number"]["exact_text"] == str(value)
    assert document["source_fields"]["created_at"]["exact_text"].endswith("+05:30")
    assert document["source_fields"]["created_at"]["timezone"] == "source_explicit_offset"


def test_credentials_excluded_recursively_without_hashing_or_echoing_them():
    row = {
        "id": 1, "password_hash": "private-hash", "email": "synthetic@example.test",
        "metadata": {"api-key": "private-key", "nested": [{"Authorization": "private-token"}],
                     "free_text": "password=private-password"},
    }
    document, omitted, _ = archive.archive_document("user", row)
    assert omitted["credential_fields"] == 4
    assert "private" not in str(document)
    assert document["source_fields"]["email"] == "synthetic@example.test"
    row["password_hash"] = "different-private-hash"
    assert archive.archive_document("user", row)[0]["content_sha256"] == document["content_sha256"]


def test_json_text_credentials_and_recognizable_hashes_are_redacted():
    row = {"id": 1, "metadata": '{"password_hash":"private", "approved_field":23}',
           "free_text": "$argon2id$v=19$private"}
    document, omitted, _ = archive.archive_document("audit_log", row)
    assert omitted["credential_fields"] == 2
    assert "private" not in str(document)
    assert document["source_fields"]["metadata"]["sanitized_fields"]["approved_field"] == 23


@pytest.mark.parametrize("name", ["live", "LIVE", "admin", "local", "config", "", "bad.name", "bad/name", None])
def test_dedicated_archive_database_name_is_required(name):
    assert not archive.validate_archive_database(name, "live")
    assert archive.validate_archive_database("legacy_archive", "live")


def test_archive_document_identity_and_unknown_table_validation():
    for value in [True, "1", None]:
        with pytest.raises(ValueError):
            archive.archive_document("customer", {"id": value})
    with pytest.raises(ValueError):
        archive.archive_document("customers", {"id": 1})


def test_archive_bson_size_limit_blocks_before_upload(monkeypatch):
    monkeypatch.setattr(archive, "MAX_DOCUMENT_BYTES", 100)
    with pytest.raises(ValueError, match="BSON limit"):
        archive.archive_document("customer", {"id": 1, "notes": "x" * 100})


def test_digest_is_deterministic_and_content_sensitive_without_source_credentials():
    row = {"id": 1, "password_hash": "private", "role": "Viewer", "email": "synthetic@example.test"}
    first = archive.archive_document("user", row)[0]
    assert first == archive.archive_document("user", dict(reversed(list(row.items()))))[0]
    row["role"] = "Analyst"
    assert first["content_sha256"] != archive.archive_document("user", row)[0]["content_sha256"]


class SyntheticCollection:
    def __init__(self):
        self.documents = {}
        self.inserts = 0

    def find_one(self, query):
        return self.documents.get(query["_id"])

    def insert_many(self, documents, ordered):
        assert ordered is True
        for document in documents:
            assert document["_id"] not in self.documents
            self.documents[document["_id"]] = deepcopy(document)
            self.inserts += 1


class SyntheticTarget:
    def __init__(self):
        self.collections = {name: SyntheticCollection() for name in profiles.LEGACY_TABLES}

    def __getitem__(self, name):
        assert name in profiles.LEGACY_TABLES  # no live collections/index/sequence initialization
        return self.collections[name]

    def list_collection_names(self):
        return list(self.collections)

    def command(self, command):
        assert command == "dbStats"
        return {"dataSize": 100, "indexSize": 100}


@pytest.fixture
def synthetic_source(monkeypatch):
    schema = {
        name: {
            field: {"type": "int" if field == "id" else "varchar(255)",
                    "nullable": "NO" if field == "id" else "YES", "key": "PRI" if field == "id" else ""}
            for field in columns.split()
        }
        for name, columns in profiles.LEGACY_COLUMNS.items()
    }
    metadata = MetaData()
    tables = {name: Table(name, metadata, Column("id", Integer)) for name in schema}
    monkeypatch.setattr(archive, "Table", lambda name, *args, **kwargs: tables[name])
    rows = {
        name: [{"id": 1, "created_at": datetime(2020, 1, 2), "risk_score": Decimal("999.99"),
                "password_hash": "private-hash", "name": None}]
        for name in schema
    }

    class Connection:
        def execute(self, statement):
            # Count-only fake scalar, not a SQL emulation.
            assert str(statement).startswith("SELECT count(")
            table = statement.get_final_froms()[0].name
            return type("Scalar", (), {"scalar_one": lambda self: len(rows[table])})()

    def batches(connection, tables, name, size):
        for index in range(0, len(rows[name]), size):
            yield rows[name][index:index + size]

    return Connection(), tables, schema, rows, batches


def arguments(apply=False):
    return Namespace(
        archive_database="legacy_archive", apply=apply,
        confirm_target="legacy_archive" if apply else None,
        batch_size=2, archive_max_bytes=archive.DEFAULT_BUDGET_BYTES,
        confirm_archive_digest=None, confirm_archive_counts=None,
    )


def run_synthetic(source, args, factory):
    connection, tables, schema, rows, batches = source
    return archive.run_archive(connection, object(), list(schema), args, "live",
                               lambda *args: schema, batches, factory)


def reviewed_args(source):
    args = arguments(True)
    connection, tables, schema, rows, batches = source
    review = archive.review_source(connection, tables, args.batch_size, batches)
    args.confirm_archive_digest = review["digest"]
    args.confirm_archive_counts = ",".join(str(len(rows[name])) for name in profiles.LEGACY_TABLES)
    return args


def test_archive_default_review_does_not_contact_target_or_need_business_semantics(synthetic_source, capsys):
    assert run_synthetic(synthetic_source, arguments(), lambda *args: pytest.fail("No target access")) == 0
    output = capsys.readouterr().out
    assert "archive_dry_run=true; target_access=false; target_writes=0" in output
    assert "archive_credential_fields_omitted=8" in output
    assert "source_count=1; reviewed_count=1" in output
    assert "private" not in output
    assert "999.99" not in output
    assert "archive_content_sha256=" in output


@pytest.mark.parametrize("proof", ["counts", "digest", "target"])
def test_apply_proofs_block_before_target_access(synthetic_source, proof):
    args = reviewed_args(synthetic_source)
    if proof == "counts":
        args.confirm_archive_counts = "0"
    elif proof == "digest":
        args.confirm_archive_digest = "0" * 64
    else:
        args.confirm_target = "wrong"
    assert run_synthetic(synthetic_source, args, lambda *args: pytest.fail("No target access")) == 2


def test_apply_uses_only_dedicated_archive_and_rerun_is_idempotent(synthetic_source):
    target = SyntheticTarget()
    def factory(name):
        assert name == "legacy_archive"
        return target
    args = reviewed_args(synthetic_source)
    assert run_synthetic(synthetic_source, args, factory) == 0
    assert run_synthetic(synthetic_source, args, factory) == 0
    assert all(collection.inserts == 1 for collection in target.collections.values())
    assert all("password_hash" not in collection.documents[1]["source_fields"]
               for collection in target.collections.values())


def test_identity_conflicts_block_all_appends_without_overwrites(synthetic_source):
    target = SyntheticTarget()
    target.collections["audit_log"].documents[1] = {"_id": 1, "different": "old"}
    assert run_synthetic(synthetic_source, reviewed_args(synthetic_source), lambda name: target) == 1
    assert all(collection.inserts == 0 for collection in target.collections.values())
    assert target.collections["audit_log"].documents[1] == {"_id": 1, "different": "old"}


def test_unknown_target_collections_block_no_names_exposed(synthetic_source, capsys):
    target = SyntheticTarget()
    target.collections["private-unexpected-name"] = SyntheticCollection()
    assert run_synthetic(synthetic_source, reviewed_args(synthetic_source), lambda name: target) == 1
    assert "private" not in capsys.readouterr().out
    assert all(collection.inserts == 0 for collection in target.collections.values())


def test_size_budget_blocks_before_target_access(synthetic_source):
    args = arguments()
    args.archive_max_bytes = 1
    assert run_synthetic(synthetic_source, args, lambda name: pytest.fail("No target access")) == 1


def test_changed_content_after_review_blocks_before_target_access(synthetic_source):
    args = reviewed_args(synthetic_source)
    synthetic_source[3]["customer"][0]["name"] = "Changed synthetic fixture"
    assert run_synthetic(synthetic_source, args, lambda name: pytest.fail("No target access")) == 2


def test_apply_capacity_headroom_blocks_all_inserts(synthetic_source):
    target = SyntheticTarget()
    args = reviewed_args(synthetic_source)
    target.command = lambda command: {"dataSize": args.archive_max_bytes, "indexSize": 100}
    assert run_synthetic(synthetic_source, args, lambda name: target) == 1
    assert all(collection.inserts == 0 for collection in target.collections.values())


@pytest.mark.parametrize("flags", [
    ["--archive", "--mapping-config", "synthetic.json"],
    ["--archive-database", "legacy_archive"],
    ["--archive", "--confirm-archive-digest", "bad"],
    ["--archive", "--schema-csv", "synthetic.csv", "--apply"],
])
def test_archive_flag_combinations_are_explicit(monkeypatch, flags):
    import sys
    monkeypatch.setattr(sys, "argv", ["importer", *flags])
    with pytest.raises(SystemExit) as error:
        importer.parse_args()
    assert error.value.code == 2


def test_archive_offline_csv_review_never_loads_settings_or_connects(monkeypatch, capsys, synthetic_source):
    schema = synthetic_source[2]
    monkeypatch.setattr(importer, "parse_args", lambda: Namespace(
        archive=True, schema_csv="synthetic.csv", apply=False, confirm_target=None,
    ))
    monkeypatch.setattr(importer, "read_schema_csv", lambda path: schema)
    monkeypatch.setattr(importer, "get_settings", lambda: pytest.fail("No settings"))
    monkeypatch.setattr(importer, "get_database", lambda: pytest.fail("No live DB"))
    monkeypatch.setattr(importer, "MongoClient", lambda *args, **kwargs: pytest.fail("No archive DB"))
    monkeypatch.setattr(importer, "create_engine", lambda *args, **kwargs: pytest.fail("No SQL"))
    assert importer.run() == 0
    output = capsys.readouterr().out
    assert "archive_counts_and_digest=unavailable" in output
    assert "archive_apply_ready=false" in output


def test_same_live_database_is_rejected_before_source_contact(monkeypatch):
    monkeypatch.setattr(importer, "parse_args", lambda: Namespace(
        archive=True, archive_database="LIVE", schema_csv=None, apply=False, confirm_target=None,
    ))
    monkeypatch.setenv("MYSQL_IMPORT_URL", "private-uri")
    monkeypatch.setattr(importer, "get_settings", lambda: Namespace(mongodb_database="live"))
    monkeypatch.setattr(importer, "create_engine", lambda *args, **kwargs: pytest.fail("No SQL"))
    assert importer.run() == 2


def test_archive_run_uses_read_only_snapshot_never_live_connection(monkeypatch):
    args = arguments()
    args.archive = True
    args.schema_csv = None
    statements = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execution_options(self, **kwargs):
            assert kwargs == {"isolation_level": "REPEATABLE READ"}
            return self

        def execute(self, statement):
            statements.append(str(statement))

    class Engine:
        disposed = False

        def connect(self):
            return Connection()

        def dispose(self):
            self.disposed = True

    class Inspector:
        def get_table_names(self):
            return list(profiles.LEGACY_TABLES)

    engine = Engine()
    monkeypatch.setattr(importer, "parse_args", lambda: args)
    monkeypatch.setenv("MYSQL_IMPORT_URL", "synthetic-source-uri")
    monkeypatch.setattr(importer, "get_settings", lambda: Namespace(mongodb_database="live"))
    monkeypatch.setattr(importer, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(importer, "inspect", lambda *args: Inspector())
    monkeypatch.setattr(importer, "get_database", lambda: pytest.fail("No live connection"))
    monkeypatch.setattr(importer, "initialize_database", lambda *args: pytest.fail("No live schema"))
    monkeypatch.setattr(importer, "MongoClient", lambda *args, **kwargs: pytest.fail("No archive connection in dry run"))
    monkeypatch.setattr(importer, "run_archive", lambda *args: 0)
    assert importer.run() == 0
    assert statements == ["SET TRANSACTION READ ONLY"]
    assert engine.disposed
