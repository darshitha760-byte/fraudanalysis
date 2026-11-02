"""Shared Pydantic base for persisted MongoDB documents."""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel as PydanticModel, ConfigDict, Field


class BaseModel(PydanticModel):
    """Document base with explicit integer identity and UTC timestamps."""

    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: Optional[int] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
