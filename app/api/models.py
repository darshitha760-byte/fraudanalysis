"""Read saved training metadata without loading executable model artifacts."""

import json
import logging
from pathlib import Path
from threading import Lock
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from filelock import FileLock, Timeout
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.core.config import get_settings
from app.db.database import get_database, get_db
from app.ml.preprocessing import DataPreprocessor
from app.services.ml_service import MLService


logger = logging.getLogger(__name__)
MODELS_DIR = Path(__file__).resolve().parents[2] / "models"
router = APIRouter(prefix="/api/models", tags=["models"])
training_lock = Lock()


class TrainingRequest(BaseModel):
    algorithms: list[Literal["logistic_regression", "random_forest", "isolation_forest"]] = Field(
        default_factory=lambda: ["random_forest"], min_length=1, max_length=3
    )
    source: Literal["database", "synthetic"] = "database"
    sample_limit: int = Field(1000, ge=100, le=5000)

    model_config = {"extra": "forbid"}


def require_training_user(user=Depends(get_current_user)):
    if not user.is_active or user.role not in ("admin", "analyst"):
        raise HTTPException(403, detail="Only active admins and analysts can train models")
    return user


def read_metadata(path: Path) -> dict:
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise ValueError("Model metadata must be an object")
        return {
            "id": path.stem,
            "name": metadata.get("model_type", path.stem.split("_v")[0]),
            "version": path.stem.split("_v", 1)[-1].split("_", 1)[0],
            "training_date": metadata.get("trained_at"),
            "dataset_size": metadata.get("training_samples"),
            "metrics": metadata.get("validation_metrics", {}),
            "feature_importance": metadata.get("feature_importance", []),
            "feature_names": metadata.get("feature_names", []),
            "cv_mean": metadata.get("cv_mean"),
            "data_source": metadata.get("data_source", "not_recorded"),
            "evaluation_only": metadata.get("evaluation_only", False),
            "total_samples": metadata.get("total_samples"),
        }
    except (OSError, ValueError, TypeError):
        logger.exception("Unable to read model metadata: %s", path.name)
        raise HTTPException(500, detail="Unable to read saved model metadata")


def _stored_model_response(model_id: str, metadata: dict) -> dict:
    return {
        "id": model_id,
        "name": metadata.get("model_type", model_id.split("_v")[0]),
        "version": model_id.split("_v", 1)[-1].split("_", 1)[0],
        "training_date": metadata.get("trained_at"),
        "dataset_size": metadata.get("training_samples"),
        "metrics": metadata.get("validation_metrics", {}),
        "feature_importance": metadata.get("feature_importance", []),
        "feature_names": metadata.get("feature_names", []),
        "cv_mean": metadata.get("cv_mean"),
        "data_source": metadata.get("data_source", "not_recorded"),
        "evaluation_only": metadata.get("evaluation_only", False),
        "total_samples": metadata.get("total_samples"),
    }


def _use_atlas_artifacts() -> bool:
    return get_settings().model_storage_backend.lower() == "atlas"


def get_model_database():
    """Resolve Atlas only when model metadata is configured to live there."""
    if _use_atlas_artifacts():
        yield get_database()
    else:
        yield None


@router.get("")
def list_models(_user=Depends(get_current_user), db=Depends(get_model_database)):
    if _use_atlas_artifacts():
        from app.ml.artifact_store import ArtifactError, list_model_metadata

        try:
            return {"items": [
                _stored_model_response(item["id"], item)
                for item in list_model_metadata(db, get_settings().model_artifact_signing_key)
            ]}
        except ArtifactError:
            logger.exception("Unable to validate the model artifact registry.")
            raise HTTPException(503, detail="Saved model registry is unavailable") from None
    return {
        "items": sorted(
            (read_metadata(path) for path in MODELS_DIR.glob("*_v*.json")),
            key=lambda model: (model["training_date"] or "", model["id"]),
            reverse=True,
        )
    }


@router.post("/train", status_code=201)
def train_models(
    request: TrainingRequest,
    _user=Depends(require_training_user),
    db=Depends(get_db),
):
    """Run bounded evaluation training; persist artifacts, but do not deploy them."""
    if not training_lock.acquire(blocking=False):
        raise HTTPException(409, detail="Training is already running. Please wait before starting another run.")
    process_lock = None
    try:
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        process_lock = FileLock(MODELS_DIR / ".training.lock")
        try:
            process_lock.acquire(timeout=0)
        except Timeout:
            raise HTTPException(409, detail="Training is already running. Please wait before starting another run.")
        if request.source == "synthetic":
            from scripts.generate_synthetic_data import SyntheticDataGenerator
            data = SyntheticDataGenerator.generate_synthetic_transactions(
                n_transactions=request.sample_limit,
                n_customers=max(10, request.sample_limit // 20),
                fraud_rate=0.15,
            )
            # Generator annotations are not predictive inputs.
            data = data.drop(columns=["merchant_name", "merchant_id", "is_synthetic"], errors="ignore")
        else:
            data = DataPreprocessor.load_data(db, limit=request.sample_limit)
        settings = get_settings()
        if settings.model_storage_backend.lower() == "atlas":
            artifact_database = db
            artifact_signing_key = settings.model_artifact_signing_key
        else:
            artifact_database = None
            artifact_signing_key = ""
        result = MLService().train_models(
            db,
            train_logistic_regression="logistic_regression" in request.algorithms,
            train_random_forest="random_forest" in request.algorithms,
            train_isolation_forest="isolation_forest" in request.algorithms,
            training_data=data,
            data_source=request.source,
            evaluation_only=True,
            generate_plots=False,
            artifact_database=artifact_database,
            artifact_signing_key=artifact_signing_key,
        )
        if result["status"] != "success":
            if result.get("error_type") == "invalid_data":
                raise HTTPException(422, detail=result["message"])
            raise HTTPException(500, detail="Training failed. Check the API logs for details.")
        if settings.model_storage_backend.lower() == "atlas":
            from app.ml.artifact_store import ArtifactError, get_model_metadata

            items = []
            for model in result["models"].values():
                model_id = model["path"]
                try:
                    metadata = get_model_metadata(db, model_id, artifact_signing_key)
                except ArtifactError:
                    logger.exception("Unable to validate a newly published model artifact.")
                    raise HTTPException(503, detail="Saved model could not be verified") from None
                if metadata is None:
                    raise HTTPException(503, detail="Saved model could not be verified")
                items.append(_stored_model_response(model_id, metadata))
        else:
            items = [
                read_metadata(Path(model["path"]).with_suffix(".json"))
                for model in result["models"].values()
            ]
        logger.info("Training completed by user %s: %s", _user.id, [item["id"] for item in items])
        return {"items": items, "data_split": result["data_split"], "total_samples": result["total_samples"]}
    finally:
        if process_lock is not None:
            process_lock.release()
        training_lock.release()


@router.get("/{model_id}/metrics")
def model_metrics(
    model_id: str,
    _user=Depends(get_current_user),
    db=Depends(get_model_database),
):
    if _use_atlas_artifacts():
        from app.ml.artifact_store import ArtifactError, get_model_metadata

        try:
            metadata = get_model_metadata(db, model_id, get_settings().model_artifact_signing_key)
        except ArtifactError:
            logger.exception("Unable to validate the requested model artifact.")
            raise HTTPException(503, detail="Saved model registry is unavailable") from None
        if metadata is None:
            raise HTTPException(404, detail="Saved model not found")
        return _stored_model_response(model_id, metadata)
    path = (MODELS_DIR / f"{model_id}.json").resolve()
    if path.parent != MODELS_DIR.resolve() or not path.is_file():
        raise HTTPException(404, detail="Saved model not found")
    return read_metadata(path)
