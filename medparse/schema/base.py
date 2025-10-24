"""Common Pydantic configuration for Medparse models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class MedparseModel(BaseModel):
    """Base class wiring default configuration for Medparse schema objects."""

    model_config = ConfigDict(
        populate_by_name=True,
        validate_assignment=True,
        str_strip_whitespace=True,
        extra="ignore",
    )


__all__ = ["MedparseModel"]
