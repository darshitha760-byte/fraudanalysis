"""MongoDB client lifecycle and BSON conversion utilities."""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Generator, Optional

from bson.decimal128 import Decimal128
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database
from pymongo.errors import CollectionInvalid, DuplicateKeyError, PyMongoError
from pymongo import ReturnDocument

from app.core.config import get_settings

_client: Optional[MongoClient] = None
_database_override: Optional[Database] = None


_INTEGER = ["int", "long"]
_DOCUMENT_VALIDATORS = {
    "users": {
        "required": ["id", "email", "full_name", "password_hash", "role", "is_active"],
        "properties": {
            "id": {"bsonType": _INTEGER},
            "email": {"bsonType": "string"},
            "full_name": {"bsonType": "string"},
            "password_hash": {"bsonType": "string"},
            "role": {"bsonType": "string"},
            "is_active": {"bsonType": "bool"},
        },
    },
    "customers": {
        "required": ["id", "customer_id", "name"],
        "properties": {
            "id": {"bsonType": _INTEGER},
            "customer_id": {"bsonType": "string"},
            "name": {"bsonType": "string"},
        },
    },
    "transactions": {
        "required": ["id", "transaction_id", "customer_id", "transaction_date", "amount"],
        "properties": {
            "id": {"bsonType": _INTEGER},
            "transaction_id": {"bsonType": "string"},
            "customer_id": {"bsonType": _INTEGER},
            "transaction_date": {"bsonType": "date"},
            "amount": {"bsonType": "decimal"},
        },
    },
    "fraud_rules": {
        "required": ["id", "rule_id", "name", "description", "rule_type"],
        "properties": {
            "id": {"bsonType": _INTEGER},
            "rule_id": {"bsonType": "string"},
            "name": {"bsonType": "string"},
            "description": {"bsonType": "string"},
            "rule_type": {"bsonType": "string"},
        },
    },
    "fraud_assessments": {
        "required": ["id", "transaction_id", "risk_score", "risk_category"],
        "properties": {
            "id": {"bsonType": _INTEGER},
            "transaction_id": {"bsonType": _INTEGER},
            "risk_score": {"bsonType": "decimal"},
            "risk_category": {"bsonType": "string"},
        },
    },
    "triggered_rules": {
        "required": ["id", "assessment_id", "transaction_id", "rule_id"],
        "properties": {
            "id": {"bsonType": _INTEGER},
            "assessment_id": {"bsonType": _INTEGER},
            "transaction_id": {"bsonType": _INTEGER},
            "rule_id": {"bsonType": _INTEGER},
        },
    },
    "fraud_alerts": {
        "required": ["id", "transaction_id", "customer_id", "assessment_id", "alert_status"],
        "properties": {
            "id": {"bsonType": _INTEGER},
            "transaction_id": {"bsonType": _INTEGER},
            "customer_id": {"bsonType": _INTEGER},
            "assessment_id": {"bsonType": _INTEGER},
            "alert_status": {"bsonType": "string"},
        },
    },
    "investigation_cases": {
        "required": ["id", "alert_id", "transaction_id", "customer_id", "case_type"],
        "properties": {
            "id": {"bsonType": _INTEGER},
            "alert_id": {"bsonType": _INTEGER},
            "transaction_id": {"bsonType": _INTEGER},
            "customer_id": {"bsonType": _INTEGER},
            "case_type": {"bsonType": "string"},
        },
    },
    "case_notes": {
        "required": ["id", "case_id", "analyst_id", "note_text"],
        "properties": {
            "id": {"bsonType": _INTEGER},
            "case_id": {"bsonType": _INTEGER},
            "analyst_id": {"bsonType": _INTEGER},
            "note_text": {"bsonType": "string"},
        },
    },
    "audit_logs": {
        "required": ["id", "action", "action_category", "target_type", "action_status"],
        "properties": {
            "id": {"bsonType": _INTEGER},
            "action": {"bsonType": "string"},
            "action_category": {"bsonType": "string"},
            "target_type": {"bsonType": "string"},
            "action_status": {"bsonType": "string"},
        },
    },
}


def get_client() -> MongoClient:
    """Return the one reusable thread-safe client and its standard connection pools."""
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.mongodb_uri.strip():
            raise RuntimeError("MONGODB_URI must be configured")
        # Retain PyMongo defaults; no workload data justifies custom pool sizing.
        _client = MongoClient(settings.mongodb_uri, tz_aware=True)
    return _client


def get_database() -> Database:
    """Return the configured database without exposing the connection URI."""
    if _database_override is not None:
        return _database_override
    return get_client()[get_settings().mongodb_database]


def get_db() -> Generator[Database, None, None]:
    """Yield the shared MongoDB database handle for request dependencies."""
    yield get_database()


def check_database() -> None:
    """Fail startup on connectivity errors instead of silently falling back."""
    try:
        get_database().command("ping")
    except PyMongoError as exc:
        raise RuntimeError("MongoDB connection check failed") from exc


def initialize_database(database: Optional[Database] = None) -> None:
    """Create fresh validated collections and indexes required by API access patterns."""
    db = get_database() if database is None else database
    indexes: dict[str, list[Any]] = {
        "users": [("email", ASCENDING), ("role", ASCENDING), ("is_active", ASCENDING)],
        "customers": [("customer_id", ASCENDING), ("email", ASCENDING), ("risk_profile", ASCENDING)],
        "transactions": [
            ("transaction_id", ASCENDING), ("customer_id", ASCENDING),
            ("transaction_date", DESCENDING), ("status", ASCENDING),
            ("amount", ASCENDING), ("merchant_id", ASCENDING),
            [("transaction_date", DESCENDING), ("customer_id", ASCENDING)],
        ],
        "fraud_rules": [("rule_id", ASCENDING), ("is_enabled", ASCENDING), ("rule_type", ASCENDING)],
        "fraud_assessments": [("transaction_id", ASCENDING), ("risk_category", ASCENDING), ("assessment_timestamp", DESCENDING)],
        "triggered_rules": [("assessment_id", ASCENDING), ("transaction_id", ASCENDING), ("rule_id", ASCENDING)],
        "fraud_alerts": [("transaction_id", ASCENDING), ("customer_id", ASCENDING), ("alert_status", ASCENDING), ("alert_created_at", DESCENDING)],
        "investigation_cases": [("alert_id", ASCENDING), ("assigned_to", ASCENDING), ("case_status", ASCENDING), ("case_created_at", DESCENDING)],
        "case_notes": [("case_id", ASCENDING), ("created_at", DESCENDING)],
        "audit_logs": [("actor_id", ASCENDING), ("action_category", ASCENDING), ("target_type", ASCENDING), ("target_id", ASCENDING), ("action_timestamp", DESCENDING)],
    }
    unique_keys = {
        "users": "email",
        "customers": "customer_id",
        "transactions": "transaction_id",
        "fraud_rules": "rule_id",
        "fraud_assessments": "transaction_id",
        "fraud_alerts": "transaction_id",
        "investigation_cases": "alert_id",
    }
    existing_collections = set(db.list_collection_names())
    for name, schema in _DOCUMENT_VALIDATORS.items():
        if name in existing_collections:
            # Existing collections are never rewritten with collMod; their
            # documents remain untouched and Pydantic validates new app writes.
            continue
        validator = {"$jsonSchema": {"bsonType": "object", **schema}}
        try:
            db.create_collection(
                name,
                validator=validator,
                validationLevel="strict",
                validationAction="error",
            )
        except NotImplementedError:
            # mongomock cannot enforce server-side validators; production
            # MongoDB always receives them on newly-created collections.
            db.create_collection(name)
        except CollectionInvalid:
            # Another process may have created the collection concurrently.
            pass
    for name, keys in indexes.items():
        target = db[name]
        unique_field = unique_keys.get(name)
        for index in keys:
            if isinstance(index, tuple) and index[0] == unique_field:
                continue
            target.create_index(index if isinstance(index, list) else [index])
        target.create_index([("id", ASCENDING)], unique=True)
        if unique_field:
            target.create_index([(unique_field, ASCENDING)], unique=True)


def next_id(
    db: Database,
    collection_name: str,
    session: Optional[Any] = None,
) -> int:
    """Allocate monotonically increasing IDs to retain the public integer-ID contract."""
    sequences = db["_id_sequences"]
    operation_options = {"session": session} if session is not None else {}
    if sequences.find_one({"_id": collection_name}, **operation_options) is None:
        latest = db[collection_name].find_one(
            {"id": {"$type": "number"}},
            projection={"id": 1},
            sort=[("id", DESCENDING)],
            **operation_options,
        )
        try:
            sequences.insert_one(
                {"_id": collection_name, "value": int(latest["id"]) if latest else 0},
                **operation_options,
            )
        except DuplicateKeyError:
            # Another request initialized this sequence concurrently.
            pass
    sequence = sequences.find_one_and_update(
        {"_id": collection_name},
        {"$inc": {"value": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
        **operation_options,
    )
    return int(sequence["value"])


def to_bson(value: Any) -> Any:
    """Convert Decimal values recursively to BSON Decimal128 without float rounding."""
    if isinstance(value, Decimal):
        return Decimal128(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: to_bson(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_bson(item) for item in value]
    return value


def from_bson(value: Any) -> Any:
    """Decode Decimal128 recursively and hide MongoDB's internal _id field."""
    if isinstance(value, Decimal128):
        return value.to_decimal()
    if isinstance(value, dict):
        return {key: from_bson(item) for key, item in value.items() if key != "_id"}
    if isinstance(value, list):
        return [from_bson(item) for item in value]
    return value


def insert_document(
    db: Database,
    collection_name: str,
    values: dict[str, Any],
    session: Optional[Any] = None,
) -> dict[str, Any]:
    """Insert a document with integer ID and UTC timestamps, optionally transactionally."""
    document = dict(values)
    now = datetime.now(timezone.utc)
    if document.get("id") is None:
        document["id"] = next_id(db, collection_name, session=session)
    document.setdefault("created_at", now)
    document.setdefault("updated_at", now)
    encoded = to_bson(document)
    operation_options = {"session": session} if session is not None else {}
    db[collection_name].insert_one(encoded, **operation_options)
    return from_bson(encoded)


def close_db() -> None:
    """Close the shared client during process shutdown."""
    global _client
    if _client is not None:
        _client.close()
        _client = None


def set_database(database: Optional[Database]) -> None:
    """Inject an isolated database in tests."""
    global _database_override
    _database_override = database
