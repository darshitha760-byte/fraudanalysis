import json
import random
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import joblib
import numpy as np
import pandas as pd
import pytest
from filelock import FileLock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import models
from app.core.security import get_current_user
from app.db.database import get_db
from app.ml.predict import ModelPredictor
from app.ml.preprocessing import DataPreprocessor
from app.ml.train import ModelTrainer
from tests.conftest import insert_test_document


@pytest.fixture
def training_client(tmp_path, monkeypatch):
    app = FastAPI()
    app.include_router(models.router)
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, role="analyst", is_active=True
    )
    monkeypatch.setattr(models, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(ModelTrainer, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(ModelPredictor, "MODELS_DIR", tmp_path)
    with TestClient(app) as client:
        yield client, app, tmp_path


def test_training_requires_active_privileged_user(training_client):
    client, app, _ = training_client
    app.dependency_overrides.pop(get_current_user)
    assert client.post("/api/models/train", json={}).status_code == 401
    for role, active in (("viewer", True), ("analyst", False), ("admin", False)):
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role=role, is_active=active)
        assert client.post("/api/models/train", json={}).status_code == 403


@pytest.mark.parametrize("payload", [
    {"algorithms": []}, {"algorithms": ["unknown"]},
    {"source": "uploaded-pickle"}, {"sample_limit": 99},
    {"sample_limit": 5001}, {"sample_limit": 100, "untrusted": True},
])
def test_training_rejects_invalid_configuration(training_client, payload):
    client, _, _ = training_client
    assert client.post("/api/models/train", json=payload).status_code == 422


def test_insufficient_database_data_returns_actionable_error(training_client, monkeypatch):
    client, _, _ = training_client
    monkeypatch.setattr(DataPreprocessor, "load_data", lambda *args, **kwargs: pd.DataFrame())
    response = client.post("/api/models/train", json={"source": "database"})
    assert response.status_code == 422
    assert "100 labeled transactions" in response.json()["detail"]
    assert not models.training_lock.locked()


def test_concurrent_training_is_rejected(training_client):
    client, _, _ = training_client
    with models.training_lock:
        response = client.post("/api/models/train", json={})
    assert response.status_code == 409


def test_training_lock_is_shared_between_api_workers(training_client):
    client, _, directory = training_client
    with FileLock(directory / ".training.lock"):
        response = client.post("/api/models/train", json={})
    assert response.status_code == 409
    assert not models.training_lock.locked()


def test_authenticated_requests_close_their_database_dependency(tmp_path, monkeypatch, test_session):
    from app.core.security import create_access_token
    from app.models import User

    user = User(email="session-lifecycle@example.com", full_name="Session Test",
                password_hash="unused-in-this-token-test", role="analyst", is_active=True)
    insert_test_document(test_session, user)
    token = create_access_token({"sub": str(user.id), "role": "analyst"})
    lifecycle = []
    def database_dependency():
        lifecycle.append("open")
        try:
            yield test_session
        finally:
            lifecycle.append("close")
    app = FastAPI()
    app.include_router(models.router)
    app.dependency_overrides[get_db] = database_dependency
    monkeypatch.setattr(models, "MODELS_DIR", tmp_path)
    with TestClient(app) as client:
        for _ in range(25):
            response = client.get("/api/models", headers={"Authorization": f"Bearer {token}"})
            assert response.status_code == 200
    assert lifecycle == ["open", "close"] * 25


def test_unexpected_training_failure_is_not_success(training_client, monkeypatch):
    client, _, _ = training_client
    monkeypatch.setattr(DataPreprocessor, "load_data", lambda *args, **kwargs: pd.DataFrame())
    monkeypatch.setattr(models.MLService, "train_models", lambda *args, **kwargs: {
        "status": "error", "error_type": "training_failure", "message": "private filesystem path",
    })
    response = client.post("/api/models/train", json={})
    assert response.status_code == 500
    assert "private" not in response.text
    assert not models.training_lock.locked()


def test_real_demo_training_saves_reloadable_artifacts_and_metrics(training_client, monkeypatch):
    client, app, directory = training_client
    from scripts.generate_synthetic_data import SyntheticDataGenerator

    original = SyntheticDataGenerator.generate_synthetic_transactions
    def deterministic_data(**kwargs):
        random_state, numpy_state = random.getstate(), np.random.get_state()
        try:
            random.seed(42)
            np.random.seed(42)
            return original(**kwargs)
        finally:
            random.setstate(random_state)
            np.random.set_state(numpy_state)
    monkeypatch.setattr(SyntheticDataGenerator, "generate_synthetic_transactions", deterministic_data)
    response = client.post("/api/models/train", json={
        "source": "synthetic", "sample_limit": 1000,
        "algorithms": ["logistic_regression", "random_forest", "isolation_forest"],
    })
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["total_samples"] == 1000
    assert result["data_split"] == {"train": 700, "val": 100, "test": 200}
    assert len(result["items"]) == 3
    for item in result["items"]:
        model_id = item["id"]
        metadata = json.loads((directory / f"{model_id}.json").read_text())
        estimator = joblib.load(directory / f"{model_id}.joblib")
        scaler = joblib.load(directory / metadata["scaler_artifact"])
        assert estimator.n_features_in_ == len(item["feature_names"]) == scaler.n_features_in_
        assert item["data_source"] == "synthetic"
        assert item["evaluation_only"] is True
        assert item["dataset_size"] == 700
        assert 0 <= item["metrics"]["accuracy"] <= 1
        assert sum(item["metrics"]["confusion_matrix"].values()) == 100
        assert client.get(f"/api/models/{model_id}/metrics").json() == item
    assert len(client.get("/api/models").json()["items"]) == 3
    assert ModelPredictor.get_latest_model() is None

    # A fresh API instance reads the same persisted registry.
    restarted = FastAPI()
    restarted.include_router(models.router)
    restarted.dependency_overrides[get_current_user] = app.dependency_overrides[get_current_user]
    with TestClient(restarted) as after_restart:
        assert len(after_restart.get("/api/models").json()["items"]) == 3


def test_database_training_passes_bounded_labeled_data(training_client, monkeypatch):
    client, _, directory = training_client
    data = pd.DataFrame({"amount": range(100)})
    load = Mock(return_value=data)
    monkeypatch.setattr(DataPreprocessor, "load_data", load)
    path = directory / "random_forest_v1_20260101.joblib"
    path.with_suffix(".json").write_text(json.dumps({"model_type": "random_forest", "data_source": "database"}))
    train = Mock(return_value={
        "status": "success", "models": {"random_forest": {"path": str(path)}},
        "data_split": {"train": 70, "val": 10, "test": 20}, "total_samples": 100,
    })
    monkeypatch.setattr(models.MLService, "train_models", train)
    result = client.post("/api/models/train", json={"sample_limit": 100})
    assert result.status_code == 201
    load.assert_called_once_with(None, limit=100)
    assert train.call_args.kwargs["training_data"] is data
    assert train.call_args.kwargs["evaluation_only"] is True
    assert train.call_args.kwargs["generate_plots"] is False


def test_preprocessing_rejects_single_class_chronological_split():
    data = pd.DataFrame({
        "transaction_date": pd.date_range("2026-01-01", periods=100, freq="h"),
        "amount": np.arange(100), "fraud_label": [0] * 70 + [1] * 30,
    })
    with pytest.raises(ValueError, match="chronological training split"):
        DataPreprocessor.preprocess_for_training(data)


def test_artifact_and_metadata_share_stem_and_scaler_is_not_a_model(tmp_path, monkeypatch):
    monkeypatch.setattr(ModelTrainer, "MODELS_DIR", tmp_path)
    path = Path(ModelTrainer.save_model({"classifier": "test"}, {"model_type": "test"}, "test"))
    assert path.is_file()
    assert path.with_suffix(".json").is_file()
    assert not list(tmp_path.glob("*.tmp"))
