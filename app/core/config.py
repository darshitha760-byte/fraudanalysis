"""Core application configuration loaded from environment variables."""

from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings. MongoDB credentials are supplied only by the environment."""

    mongodb_uri: str = ""
    mongodb_database: str = "fraud_detection_db"
    model_storage_backend: str = "local"
    model_artifact_signing_key: str = ""

    fastapi_host: str = "127.0.0.1"
    fastapi_port: int = 8000
    debug: bool = True
    environment: str = "development"

    secret_key: str = "dev_secret_key_change_in_production_minimum_32_chars_required"
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    admin_email: str = "admin@fraud-detection.local"

    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:8501"]
    streamlit_server_port: int = 8501
    streamlit_server_address: str = "127.0.0.1"
    api_base_url: str = "http://127.0.0.1:8000"

    ml_model_threshold: float = 0.5
    enable_ml_detection: bool = True
    dataset_path: str = "data/raw/creditcard.csv"
    synthetic_data_size: int = 10000

    max_upload_size_mb: int = 100
    rate_limit_login_attempts: int = 5
    rate_limit_window_seconds: int = 900
    log_level: str = "INFO"
    log_file: Optional[str] = "logs/app.log"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"


@lru_cache()
def get_settings() -> Settings:
    """Return one cached settings instance per process."""
    return Settings()
