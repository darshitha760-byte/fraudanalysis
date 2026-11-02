import pytest
from pymongo.errors import OperationFailure, ServerSelectionTimeoutError
from sqlalchemy.exc import ArgumentError, NoSuchTableError, OperationalError

from scripts import import_mysql_to_mongodb as importer


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (ArgumentError("private-uri"), "invalid_source_uri"),
        (NoSuchTableError("private-table"), "missing_source_table"),
        (
            OperationalError(
                "private-query", {}, Exception(1045, "private-password")
            ),
            "mysql_authentication_failed",
        ),
        (ServerSelectionTimeoutError("private-host"), "mongodb_unreachable"),
        (OperationFailure("private-user", code=18), "mongodb_authorization_failed"),
        (OperationFailure("private-document", code=121), "mongodb_schema_validation_failed"),
        (RuntimeError("private-data"), "validation_or_configuration_error"),
    ],
)
def test_diagnostics_omit_exception_details(error, reason):
    result = importer.safe_failure_reason(error)
    assert result.startswith(reason + ":")
    assert "private" not in result


def test_connection_failure_is_safe_and_disposes_engine(monkeypatch, capsys):
    class FailingEngine:
        disposed = False

        def connect(self):
            raise OperationalError(
                "private-query", {}, Exception(2003, "private-credentials")
            )

        def dispose(self):
            self.disposed = True

    engine = FailingEngine()
    monkeypatch.setenv("MYSQL_IMPORT_URL", "private-uri")
    monkeypatch.setattr(
        importer,
        "parse_args",
        lambda: type("Args", (), {"apply": False, "confirm_target": None})(),
    )
    monkeypatch.setattr(importer, "get_settings", lambda: object())
    monkeypatch.setattr(importer, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(
        importer, "get_database", lambda: pytest.fail("Target must not be accessed")
    )

    assert importer.run() == 1
    output = capsys.readouterr().err
    assert "stage=source_connection" in output
    assert "mysql_unreachable" in output
    assert "private" not in output
    assert engine.disposed


def test_missing_tables_stop_before_target_access(monkeypatch, capsys):
    class SourceConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class SourceEngine:
        disposed = False

        def connect(self):
            return SourceConnection()

        def dispose(self):
            self.disposed = True

    class SourceInspector:
        def get_table_names(self):
            return ["users", "transactions", "private_unrelated_table"]

    engine = SourceEngine()
    monkeypatch.setenv("MYSQL_IMPORT_URL", "private-uri")
    monkeypatch.setattr(
        importer,
        "parse_args",
        lambda: type("Args", (), {"apply": False, "confirm_target": None})(),
    )
    monkeypatch.setattr(importer, "get_settings", lambda: object())
    monkeypatch.setattr(importer, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(importer, "inspect", lambda connection: SourceInspector())
    monkeypatch.setattr(
        importer, "get_database", lambda: pytest.fail("Target must not be accessed")
    )

    assert importer.run() == 1
    output = capsys.readouterr().err
    assert "present_application_tables=users,transactions" in output
    missing = next(
        line for line in output.splitlines()
        if line.startswith("missing_application_tables=")
    )
    assert missing == "missing_application_tables=" + ",".join(
        name for name in importer.TABLES if name not in {"users", "transactions"}
    )
    assert "private" not in output
    assert engine.disposed


def test_complete_source_schema_passes(monkeypatch, capsys):
    class SourceInspector:
        def get_table_names(self):
            return list(importer.TABLES)

    monkeypatch.setattr(importer, "inspect", lambda connection: SourceInspector())
    assert importer.check_source_tables(object())
    assert capsys.readouterr().err == ""
