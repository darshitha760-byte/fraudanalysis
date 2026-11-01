import json
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest
import pandas as pd
from fastapi import HTTPException
from fastapi import FastAPI
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from app.api import models
from app.core.security import get_current_user
from app.db.database import get_db

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard"))
from components.auth_handler import AuthHandler


@pytest.fixture
def saved_model(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "MODELS_DIR", tmp_path)
    model_id = "random_forest_v1.0.0_20261022_010000"
    (tmp_path / f"{model_id}.json").write_text(json.dumps({
        "model_type": "random_forest",
        "trained_at": "2026-10-22T01:00:00",
        "training_samples": 500,
        "validation_metrics": {"accuracy": 0.95, "f1_score": 0.8},
        "feature_importance": [0.7, 0.3],
        "feature_names": ["amount", "hour"],
    }), encoding="utf-8")
    return model_id


def test_saved_model_list_and_metrics_match_training_metadata(saved_model):
    result = models.list_models(_user=object())
    assert result["items"][0]["id"] == saved_model
    metrics = models.model_metrics(saved_model, _user=object())
    assert metrics["metrics"]["accuracy"] == 0.95
    assert metrics["dataset_size"] == 500
    assert metrics["version"] == "1.0.0"


def test_empty_registry_and_missing_model(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "MODELS_DIR", tmp_path)
    assert models.list_models(_user=object()) == {"items": []}
    with pytest.raises(HTTPException) as error:
        models.model_metrics("missing", _user=object())
    assert error.value.status_code == 404


def test_invalid_metadata_surfaces_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "MODELS_DIR", tmp_path)
    (tmp_path / "broken_v1.json").write_text("{")
    with pytest.raises(HTTPException) as error:
        models.list_models(_user=object())
    assert error.value.status_code == 500


def test_routes_require_authentication_and_return_saved_metrics(saved_model):
    app = FastAPI()
    app.include_router(models.router)
    app.dependency_overrides[get_db] = lambda: None
    client = TestClient(app)
    assert client.get("/api/models").status_code == 401
    assert client.get(f"/api/models/{saved_model}/metrics").status_code == 401
    app.dependency_overrides[get_current_user] = lambda: object()
    assert client.get("/api/models").json()["items"][0]["id"] == saved_model
    assert client.get(f"/api/models/{saved_model}/metrics").json()["metrics"]["accuracy"] == 0.95
    assert client.get("/api/models/missing/metrics").status_code == 404


def test_metrics_cannot_read_outside_models(tmp_path, monkeypatch):
    directory = tmp_path / "models"
    directory.mkdir()
    (tmp_path / "outside.json").write_text("{}")
    monkeypatch.setattr(models, "MODELS_DIR", directory)
    with pytest.raises(HTTPException) as error:
        models.model_metrics("../outside", _user=object())
    assert error.value.status_code == 404


def performance_page(monkeypatch, client):
    monkeypatch.setattr(AuthHandler, "is_authenticated", lambda: True)
    monkeypatch.setattr(AuthHandler, "has_permission", lambda permission: True)
    monkeypatch.setattr(AuthHandler, "get_api_client", lambda: client)
    return AppTest.from_file(str(
        Path(__file__).resolve().parents[1] / "dashboard" / "pages" / "06_Model_Performance.py"
    ))


def test_performance_page_handles_untrained_installation(monkeypatch):
    client = Mock()
    client.get_models.return_value = {"items": []}
    app = performance_page(monkeypatch, client).run()
    assert not app.exception
    assert "No trained models" in app.info[0].value
    client.get_model_metrics.assert_not_called()


def test_performance_page_passes_selected_model_id(monkeypatch, saved_model):
    client = Mock()
    model = models.model_metrics(saved_model, _user=object())
    client.get_models.return_value = {"items": [model]}
    client.get_model_metrics.return_value = model
    app = performance_page(monkeypatch, client).run()
    next(button for button in app.button if "Load Model Metrics" in button.label).click().run()
    assert not app.exception
    client.get_model_metrics.assert_called_once_with(saved_model)
    assert app.metric[0].value == "95.00%"


def test_legacy_metadata_does_not_invent_scores(monkeypatch, saved_model):
    client = Mock()
    model = models.model_metrics(saved_model, _user=object())
    model["metrics"] = {}
    client.get_models.return_value = {"items": [model]}
    client.get_model_metrics.return_value = model
    app = performance_page(monkeypatch, client).run()
    next(button for button in app.button if "Load Model Metrics" in button.label).click().run()
    assert not app.exception
    assert any("not recorded" in item.value for item in app.info)
    assert not app.metric


def test_history_comparison_uses_saved_scores(monkeypatch, saved_model):
    client = Mock()
    model = models.model_metrics(saved_model, _user=object())
    second = dict(model, id="logistic_regression_v1.0.0_20261022_020000")
    client.get_models.return_value = {"items": [model, second]}
    app = performance_page(monkeypatch, client).run()
    assert not app.exception
    assert len(app.dataframe) == 2
    assert app.dataframe[0].value["F1 Score"].tolist() == ["80.00%", "80.00%"]
    assert app.dataframe[1].value.loc["accuracy", model["id"]] == "95.00%"


@pytest.mark.parametrize("kind", ["logistic_regression", "random_forest", "isolation_forest"])
def test_training_saves_validation_metrics_and_feature_names(monkeypatch, kind):
    import numpy as np
    from app.services.ml_service import MLService, DataPreprocessor, ModelTrainer, ModelEvaluator

    data = pd.DataFrame({"amount": range(100)})
    x = np.zeros((10, 2))
    y = np.array([0, 1] * 5)
    names = ["amount", "hour"]
    monkeypatch.setattr(DataPreprocessor, "load_data", lambda *args, **kwargs: data)
    monkeypatch.setattr(DataPreprocessor, "engineer_features", lambda frame: frame)
    monkeypatch.setattr(
        DataPreprocessor, "preprocess_for_training",
        lambda frame: (x, x, x, y, y, y, names, None),
    )
    predictor = Mock(spec=["predict"])
    predictor.predict.return_value = y
    monkeypatch.setattr(
        ModelTrainer, f"train_{kind}",
        lambda *args, **kwargs: (predictor, {"model_type": kind}),
    )
    metrics = {"precision": 0.8, "recall": 0.75, "f1_score": 0.77}
    monkeypatch.setattr(ModelEvaluator, "evaluate", lambda *args, **kwargs: metrics)
    save = Mock(return_value="saved.joblib")
    monkeypatch.setattr(ModelTrainer, "save_model", save)
    service = MLService.__new__(MLService)
    result = service.train_models(
        None,
        train_logistic_regression=kind == "logistic_regression",
        train_random_forest=kind == "random_forest",
        train_isolation_forest=kind == "isolation_forest",
    )
    assert result["status"] == "success"
    saved_metadata = save.call_args.args[1]
    assert saved_metadata["validation_metrics"] == metrics
    assert saved_metadata["feature_names"] == names
