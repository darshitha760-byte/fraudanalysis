"""Bounded, authenticated model artifact storage in MongoDB GridFS.

Only artifacts created by the application's training pipeline are deserialized.
Every manifest and binary is authenticated before joblib is allowed to load it.
GridFS uploads complete before the small registry document is inserted; that
document is the publication point. Failed publications remove their unreferenced
GridFS files, and readers never see incomplete models.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import logging
import re
import threading
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

import joblib
from bson import ObjectId
from gridfs import GridFSBucket
from pymongo.errors import DuplicateKeyError
from pymongo.database import Database

logger = logging.getLogger(__name__)

BUCKET_NAME = "model_artifacts"
REGISTRY_NAME = "model_registry"
MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
MAX_MODEL_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_PUBLISHED_MODELS = 200
MAX_METADATA_BYTES = 128 * 1024
MAX_CACHE_ENTRIES = 4
MAX_CACHE_BYTES = 64 * 1024 * 1024
_MODEL_TYPES = {"logistic_regression", "random_forest", "isolation_forest", "test"}
_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,159}$")
_CACHE: OrderedDict[tuple[str, str, str], tuple[Any, Any, dict, int]] = OrderedDict()
_CACHE_BYTES = 0
_CACHE_LOCK = threading.RLock()


class ArtifactError(ValueError):
    """Artifact is missing, invalid, unauthenticated, or outside safe limits."""


def _sign(key: str, message: bytes) -> str:
    if not isinstance(key, str) or len(key.encode("utf-8")) < 32:
        raise ArtifactError("A model artifact signing key of at least 32 bytes is required.")
    return hmac.new(key.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str
    ).encode("utf-8")


def _manifest_payload(record: dict) -> bytes:
    created_at = record["created_at"]
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return _json_bytes({
        "schema_version": record["schema_version"],
        "model_id": record["_id"],
        "model_type": record["model_type"],
        "metadata": record["metadata"],
        "model_file_id": str(record["model_file_id"]),
        "model_sha256": record["model_sha256"],
        "model_hmac": record["model_hmac"],
        "scaler_file_id": str(record["scaler_file_id"]) if record.get("scaler_file_id") else None,
        "scaler_sha256": record.get("scaler_sha256"),
        "scaler_hmac": record.get("scaler_hmac"),
        "total_bytes": record["total_bytes"],
        # Compare the exact BSON millisecond timestamp regardless of driver
        # timezone decoding (PyMongo may return a naive UTC datetime).
        "created_at_ms": int(created_at.timestamp() * 1000),
    })


def _serialize(value: Any) -> bytes:
    stream = io.BytesIO()
    joblib.dump(value, stream, compress=3)
    return stream.getvalue()


def _check_size(data: bytes, label: str) -> None:
    if not data or len(data) > MAX_ARTIFACT_BYTES:
        raise ArtifactError(f"{label} artifact exceeds the configured size limit.")


def _read_file(bucket: GridFSBucket, file_id: ObjectId, digest: str, signature: str,
               key: str, model_id: str, kind: str) -> bytes:
    stream = bucket.open_download_stream(file_id)
    if stream.length <= 0 or stream.length > MAX_ARTIFACT_BYTES:
        raise ArtifactError(f"{kind} artifact has an invalid stored size.")
    data = stream.read(MAX_ARTIFACT_BYTES + 1)
    if len(data) != stream.length or len(data) > MAX_ARTIFACT_BYTES:
        raise ArtifactError(f"{kind} artifact was truncated or exceeds its size limit.")
    actual_digest = hashlib.sha256(data).hexdigest()
    if not hmac.compare_digest(actual_digest, digest):
        raise ArtifactError(f"{kind} artifact checksum verification failed.")
    expected_signature = _sign(key, f"fraud-model:{model_id}:{kind}:".encode() + data)
    if not hmac.compare_digest(expected_signature, signature):
        raise ArtifactError(f"{kind} artifact authentication failed.")
    return data


def save_model_artifacts(
    database: Database,
    model: Any,
    metadata: dict,
    name: str,
    model_id: str,
    signing_key: str,
    scaler: Any = None,
) -> str:
    """Publish immutable model/scaler blobs with one authenticated manifest."""
    if not _MODEL_ID.fullmatch(model_id):
        raise ArtifactError("Invalid model artifact identifier.")
    if name not in _MODEL_TYPES:
        raise ArtifactError("Unsupported model type.")
    if metadata.get("model_type") != name:
        raise ArtifactError("Model type does not match artifact metadata.")
    metadata_bytes = _json_bytes(metadata)
    if len(metadata_bytes) > MAX_METADATA_BYTES:
        raise ArtifactError("Model metadata exceeds the configured size limit.")
    model_bytes = _serialize(model)
    _check_size(model_bytes, "Model")
    scaler_bytes = _serialize(scaler) if scaler is not None else None
    if scaler_bytes is not None:
        _check_size(scaler_bytes, "Scaler")
    total_bytes = len(model_bytes) + (len(scaler_bytes) if scaler_bytes else 0)
    if total_bytes > MAX_MODEL_BYTES:
        raise ArtifactError("Combined model artifacts exceed the per-model size limit.")

    registry = database[REGISTRY_NAME]
    existing_sizes = list(registry.find({}, {"total_bytes": 1}).limit(MAX_PUBLISHED_MODELS + 1))
    if len(existing_sizes) >= MAX_PUBLISHED_MODELS:
        raise ArtifactError("Model artifact registry is at its configured capacity.")
    stored_bytes = sum(int(item.get("total_bytes", 0)) for item in existing_sizes)
    if stored_bytes + total_bytes > MAX_TOTAL_BYTES:
        raise ArtifactError("Model artifact storage is at its configured capacity.")

    now = datetime.now(timezone.utc)
    # BSON Date stores millisecond precision; sign the value that will roundtrip.
    now = now.replace(microsecond=(now.microsecond // 1000) * 1000)
    model_id_object = ObjectId()
    scaler_id_object = ObjectId() if scaler_bytes is not None else None
    record = {
        "_id": model_id,
        "schema_version": 1,
        "model_type": name,
        "metadata": metadata,
        "model_file_id": model_id_object,
        "model_sha256": hashlib.sha256(model_bytes).hexdigest(),
        "model_hmac": _sign(signing_key, f"fraud-model:{model_id}:model:".encode() + model_bytes),
        "scaler_file_id": scaler_id_object,
        "scaler_sha256": hashlib.sha256(scaler_bytes).hexdigest() if scaler_bytes else None,
        "scaler_hmac": (
            _sign(signing_key, f"fraud-model:{model_id}:scaler:".encode() + scaler_bytes)
            if scaler_bytes else None
        ),
        "total_bytes": total_bytes,
        "created_at": now,
    }
    record["manifest_hmac"] = _sign(signing_key, _manifest_payload(record))
    bucket = GridFSBucket(database, bucket_name=BUCKET_NAME)
    uploaded: list[ObjectId] = []
    try:
        # Track the ID before each upload so a partially failed GridFS write
        # can still be cleaned up on a definitive publication failure.
        uploaded.append(model_id_object)
        bucket.upload_from_stream_with_id(
            model_id_object, f"{model_id}.joblib", io.BytesIO(model_bytes),
            metadata={"model_id": model_id, "kind": "model", "sha256": record["model_sha256"]},
        )
        if scaler_bytes is not None and scaler_id_object is not None:
            uploaded.append(scaler_id_object)
            bucket.upload_from_stream_with_id(
                scaler_id_object, f"{model_id}.scaler", io.BytesIO(scaler_bytes),
                metadata={"model_id": model_id, "kind": "scaler", "sha256": record["scaler_sha256"]},
            )
        registry.insert_one(record)
    except Exception as exc:
        try:
            published = registry.find_one({"_id": model_id})
            if published is not None:
                # The insert may have succeeded even if its acknowledgement
                # was lost. Keep the referenced files intact.
                _validate_manifest(published, signing_key)
                return model_id
        except Exception:
            # An ambiguous network failure is not safe grounds to delete files.
            logger.warning("Model publication status is ambiguous; retaining artifacts for recovery.")
            raise ArtifactError("Model artifact publication status is unknown; inspect the registry.") from None
        for file_id in uploaded:
            try:
                bucket.delete(file_id)
            except Exception:
                logger.warning("Unable to clean an unpublished model artifact.")
        if isinstance(exc, DuplicateKeyError):
            raise ArtifactError("Model artifact identifier already exists.") from None
        raise ArtifactError("Model artifact publication failed; no model was published.") from None
    return model_id


def get_model_metadata(database: Database, model_id: str, signing_key: str) -> dict | None:
    if not _MODEL_ID.fullmatch(model_id):
        return None
    record = database[REGISTRY_NAME].find_one({"_id": model_id})
    if record is None:
        return None
    _validate_manifest(record, signing_key)
    return dict(record["metadata"])


def _validate_manifest(record: dict, signing_key: str) -> None:
    if (
        not isinstance(record, dict)
        or record.get("schema_version") != 1
        or record.get("model_type") not in _MODEL_TYPES
        or not isinstance(record.get("metadata"), dict)
        or not isinstance(record.get("total_bytes"), int)
        or not 0 < record.get("total_bytes", 0) <= MAX_MODEL_BYTES
        or not isinstance(record.get("model_file_id"), ObjectId)
        or (record.get("scaler_file_id") is not None
            and not isinstance(record.get("scaler_file_id"), ObjectId))
        or not isinstance(record.get("created_at"), datetime)
    ):
        raise ArtifactError("Model artifact manifest has an unsupported schema.")
    if not _MODEL_ID.fullmatch(str(record.get("_id", ""))):
        raise ArtifactError("Model artifact manifest identifier is invalid.")
    if record.get("metadata", {}).get("model_type") != record.get("model_type"):
        raise ArtifactError("Model artifact manifest metadata is inconsistent.")
    for field in ("model_sha256", "model_hmac", "manifest_hmac"):
        if not isinstance(record.get(field), str) or len(record[field]) != 64:
            raise ArtifactError("Model artifact manifest is incomplete.")
    if record.get("scaler_file_id") is not None:
        for field in ("scaler_sha256", "scaler_hmac"):
            if not isinstance(record.get(field), str) or len(record[field]) != 64:
                raise ArtifactError("Model scaler manifest is incomplete.")
    try:
        expected = _sign(signing_key, _manifest_payload(record))
    except (KeyError, AttributeError, TypeError, ValueError):
        raise ArtifactError("Model artifact manifest is incomplete.") from None
    if not hmac.compare_digest(expected, str(record.get("manifest_hmac", ""))):
        raise ArtifactError("Model artifact manifest authentication failed.")


def list_model_metadata(database: Database, signing_key: str) -> list[dict]:
    records = database[REGISTRY_NAME].find().sort(
        [("created_at", -1), ("_id", -1)]
    ).limit(MAX_PUBLISHED_MODELS)
    items = []
    for record in records:
        _validate_manifest(record, signing_key)
        items.append({"id": record["_id"], **dict(record["metadata"])})
    return items


def latest_model_id(database: Database, signing_key: str) -> tuple[str, str] | None:
    for name in ("random_forest", "logistic_regression", "isolation_forest"):
        record = database[REGISTRY_NAME].find({
            "model_type": name,
            "metadata.evaluation_only": {"$ne": True},
            "metadata.data_source": {"$ne": "synthetic"},
        }).sort([("created_at", -1), ("_id", -1)]).limit(1)
        for item in record:
            _validate_manifest(item, signing_key)
            return item["_id"], name
    return None


def load_model_artifacts(
    database: Database, model_id: str, signing_key: str
) -> tuple[Any, Any, dict] | None:
    if not _MODEL_ID.fullmatch(model_id):
        return None
    record = database[REGISTRY_NAME].find_one({"_id": model_id})
    if record is None:
        return None
    _validate_manifest(record, signing_key)
    cache_key = (str(database.name), model_id, record["model_sha256"])
    global _CACHE_BYTES
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
        if cached is not None:
            _CACHE.move_to_end(cache_key)
            return cached[0], cached[1], dict(cached[2])

    bucket = GridFSBucket(database, bucket_name=BUCKET_NAME)
    model_data = _read_file(
        bucket, record["model_file_id"], record["model_sha256"],
        record["model_hmac"], signing_key, model_id, "model",
    )
    scaler_data = None
    if record.get("scaler_file_id") is not None:
        scaler_data = _read_file(
            bucket, record["scaler_file_id"], record["scaler_sha256"],
            record["scaler_hmac"], signing_key, model_id, "scaler",
        )
    try:
        # Deserialization happens only after both manifest and binary HMAC checks.
        model = joblib.load(io.BytesIO(model_data))
        scaler = joblib.load(io.BytesIO(scaler_data)) if scaler_data is not None else None
    except Exception:
        raise ArtifactError("Authenticated model artifact could not be decoded.") from None

    size = len(model_data) + (len(scaler_data) if scaler_data is not None else 0)
    if size <= MAX_CACHE_BYTES:
        with _CACHE_LOCK:
            previous = _CACHE.pop(cache_key, None)
            if previous is not None:
                _CACHE_BYTES -= previous[3]
            _CACHE[cache_key] = (model, scaler, dict(record["metadata"]), size)
            _CACHE_BYTES += size
            while len(_CACHE) > MAX_CACHE_ENTRIES or _CACHE_BYTES > MAX_CACHE_BYTES:
                _, removed = _CACHE.popitem(last=False)
                _CACHE_BYTES -= removed[3]
    return model, scaler, dict(record["metadata"])


def clear_artifact_cache() -> None:
    """Clear the bounded in-process cache; intended for tests and key rotation."""
    global _CACHE_BYTES
    with _CACHE_LOCK:
        _CACHE.clear()
        _CACHE_BYTES = 0
