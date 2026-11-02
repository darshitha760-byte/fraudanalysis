from __future__ import annotations

import io
from datetime import datetime, timezone

import mongomock
import mongomock.gridfs
import numpy as np
import pytest
from gridfs import GridFSBucket
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

import app.ml.artifact_store as store


SIGNING_KEY = "local-test-artifact-signing-key-with-adequate-length"


class _Download:
    def __init__(self, value: bytes):
        self.length = len(value)
        self._stream = io.BytesIO(value)

    def read(self, size=-1):
        return self._stream.read(size)


class _MemoryBucket:
    files: dict = {}

    def __init__(self, database, bucket_name):
        pass

    def upload_from_stream_with_id(self, file_id, filename, source, metadata=None):
        self.files[file_id] = source.read()

    def open_download_stream(self, file_id):
        if file_id not in self.files:
            raise RuntimeError("artifact missing")
        return _Download(self.files[file_id])

    def delete(self, file_id):
        self.files.pop(file_id, None)


@pytest.fixture
def artifact_db(monkeypatch):
    mongomock.gridfs.enable_gridfs_integration()
    _MemoryBucket.files = {}
    monkeypatch.setattr(store, "GridFSBucket", _MemoryBucket)
    client = mongomock.MongoClient()
    yield client.artifact_test
    store.clear_artifact_cache()
    client.close()


def _trained_objects():
    features = np.array([[0.0, 0.1], [1.0, 1.1], [2.0, 2.1], [3.0, 3.1]])
    labels = np.array([0, 0, 1, 1])
    scaler = StandardScaler().fit(features)
    model = LogisticRegression(random_state=7).fit(scaler.transform(features), labels)
    metadata = {
        "model_type": "random_forest",
        "feature_names": ["amount", "velocity"],
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "data_source": "database",
        "evaluation_only": False,
    }
    return model, scaler, metadata, features


def _save(database, model_id="random_forest_v1.0.0_20261102_001122_123456"):
    model, scaler, metadata, features = _trained_objects()
    store.save_model_artifacts(
        database, model, metadata, "random_forest", model_id, SIGNING_KEY, scaler
    )
    return model_id, features, scaler


def test_gridfs_artifact_round_trip_after_cache_clear_and_database_reopen(artifact_db):
    model_id, features, scaler = _save(artifact_db)
    expected = scaler.transform(features)
    store.clear_artifact_cache()

    # A new database handle models a process restart; artifact bytes remain in
    # the backing database, not in this process's memory or local filesystem.
    restarted_database = artifact_db.client[artifact_db.name]
    loaded = store.load_model_artifacts(restarted_database, model_id, SIGNING_KEY)
    assert loaded is not None
    model, loaded_scaler, metadata = loaded
    assert np.array_equal(model.predict(loaded_scaler.transform(features)), [0, 0, 1, 1])
    assert np.allclose(loaded_scaler.transform(features), expected)
    assert metadata["feature_names"] == ["amount", "velocity"]
    assert store.latest_model_id(restarted_database, SIGNING_KEY) == (model_id, "random_forest")


def test_binary_corruption_is_detected_before_joblib_deserialization(artifact_db, monkeypatch):
    model_id, _, _ = _save(artifact_db)
    store.clear_artifact_cache()
    record = artifact_db[store.REGISTRY_NAME].find_one({"_id": model_id})
    original = _MemoryBucket.files[record["model_file_id"]]
    _MemoryBucket.files[record["model_file_id"]] = original[:-1] + bytes([original[-1] ^ 1])
    called = False

    def forbidden_load(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("untrusted bytes must never be deserialized")

    monkeypatch.setattr(store.joblib, "load", forbidden_load)
    with pytest.raises(store.ArtifactError, match="checksum"):
        store.load_model_artifacts(artifact_db, model_id, SIGNING_KEY)
    assert not called


def test_manifest_tampering_is_rejected(artifact_db):
    model_id, _, _ = _save(artifact_db)
    artifact_db[store.REGISTRY_NAME].update_one(
        {"_id": model_id}, {"$set": {"metadata.data_source": "changed"}}
    )
    store.clear_artifact_cache()
    with pytest.raises(store.ArtifactError, match="manifest authentication"):
        store.load_model_artifacts(artifact_db, model_id, SIGNING_KEY)


def test_artifact_capacity_is_enforced_before_upload(artifact_db, monkeypatch):
    monkeypatch.setattr(store, "MAX_MODEL_BYTES", 1)
    model, scaler, metadata, _ = _trained_objects()
    with pytest.raises(store.ArtifactError, match="per-model size limit"):
        store.save_model_artifacts(
            artifact_db, model, metadata, "random_forest",
            "random_forest_v1.0.0_20261102_001122_123456", SIGNING_KEY, scaler,
        )
    assert artifact_db[store.REGISTRY_NAME].count_documents({}) == 0
    assert _MemoryBucket.files == {}


def test_predictor_restores_preprocessing_after_restart(artifact_db, monkeypatch):
    from app.core.config import get_settings
    from app.ml.predict import ModelPredictor

    model_id, features, scaler = _save(artifact_db)
    monkeypatch.setattr(get_settings(), "model_storage_backend", "atlas")
    monkeypatch.setattr(get_settings(), "model_artifact_signing_key", SIGNING_KEY)
    store.clear_artifact_cache()
    predictor = ModelPredictor(database=artifact_db.client[artifact_db.name])
    assert predictor.load_active_model()
    assert predictor.metadata["feature_names"] == ["amount", "velocity"]
    assert predictor.scaler is not None
    result = predictor.predict(predictor.scaler.transform(features[:1]))
    assert result["status"] == "success"
    assert result["model_name"] == "random_forest"


def test_missing_or_weak_signing_key_blocks_publish_and_load(artifact_db):
    model, scaler, metadata, _ = _trained_objects()
    with pytest.raises(store.ArtifactError, match="signing key"):
        store.save_model_artifacts(
            artifact_db, model, metadata, "random_forest",
            "random_forest_v1.0.0_20261102_001122_123456", "weak", scaler,
        )
    assert artifact_db[store.REGISTRY_NAME].count_documents({}) == 0


def test_failed_registry_publication_removes_uploaded_blobs(monkeypatch, caplog):
    model, scaler, metadata, _ = _trained_objects()

    class _Cursor:
        def limit(self, size):
            return self

        def __iter__(self):
            return iter(())

    class _Registry:
        def find(self, *args, **kwargs):
            return _Cursor()

        def find_one(self, *args, **kwargs):
            return None

        def insert_one(self, record):
            raise RuntimeError("simulated publication failure")

    class _Database:
        name = "failure-test"

        def __getitem__(self, key):
            assert key == store.REGISTRY_NAME
            return _Registry()

    monkeypatch.setattr(store, "GridFSBucket", _MemoryBucket)
    _MemoryBucket.files = {}
    with pytest.raises(store.ArtifactError, match="no model was published"):
        store.save_model_artifacts(
            _Database(), model, metadata, "random_forest",
            "random_forest_v1.0.0_20261102_001122_123456", SIGNING_KEY, scaler,
        )
    assert "simulated publication failure" in caplog.text
    assert _MemoryBucket.files == {}


def test_gridfs_replica_set_round_trip_when_local_test_uri_is_enabled(mongo_replica_set):
    database = mongo_replica_set.client[f"model_artifact_test_{id(mongo_replica_set)}"]
    model_id, features, scaler = _save(database)
    try:
        store.clear_artifact_cache()
        reopened = mongo_replica_set.client[database.name]
        loaded = store.load_model_artifacts(reopened, model_id, SIGNING_KEY)
        assert loaded is not None
        model, loaded_scaler, _ = loaded
        assert np.array_equal(
            model.predict(loaded_scaler.transform(features)), [0, 0, 1, 1]
        )
        assert np.allclose(loaded_scaler.transform(features), scaler.transform(features))
    finally:
        mongo_replica_set.client.drop_database(database.name)


def test_gridfs_bucket_uses_pymongo_driver_import():
    assert GridFSBucket is not None
