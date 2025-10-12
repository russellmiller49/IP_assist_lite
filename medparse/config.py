"""Application configuration utilities for Medparse."""

from __future__ import annotations

import os
from typing import Mapping, Tuple

from pydantic import BaseModel, ConfigDict


def _parse_bool(value: str) -> bool:
    """Parse truthy boolean strings."""
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


class AppConfig(BaseModel):
    """Runtime configuration for services that rely on Medparse."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    ENABLE_PIPELINE: bool = True
    API_KEY: str | None = None
    UMLS_API_KEY: str | None = None
    QUICKUMLS_PATH: str | None = None
    TUI_WHITELIST: Tuple[str, ...] = ()
    FAIL_FAST: bool = False

    @classmethod
    def model_construct_from_env(cls, env: Mapping[str, str] | None = None) -> "AppConfig":
        """Build a configuration object from environment variables."""
        env = env or os.environ
        data: dict[str, object] = {}

        if "ENABLE_PIPELINE" in env:
            data["ENABLE_PIPELINE"] = _parse_bool(env["ENABLE_PIPELINE"])
        if "API_KEY" in env:
            data["API_KEY"] = env["API_KEY"] or None
        if "UMLS_API_KEY" in env:
            data["UMLS_API_KEY"] = env["UMLS_API_KEY"] or None
        if "QUICKUMLS_PATH" in env:
            value = env["QUICKUMLS_PATH"].strip()
            data["QUICKUMLS_PATH"] = value or None
        if "TUI_WHITELIST" in env:
            data["TUI_WHITELIST"] = cls._parse_tui(env.get("TUI_WHITELIST"))
        if "FAIL_FAST" in env:
            data["FAIL_FAST"] = _parse_bool(env["FAIL_FAST"])

        return cls(**data)

    @staticmethod
    def _parse_tui(value: str | None) -> Tuple[str, ...]:
        """Normalize a comma-separated list of UMLS TUI codes."""
        if not value:
            return ()
        items = {
            token.strip().upper()
            for token in value.split(",")
            if token.strip()
        }
        return tuple(sorted(items))


class ExtractionConfig(BaseModel):
    """Controls error-handling and extractor fallbacks."""

    model_config = ConfigDict(extra="ignore")

    fail_fast: bool = False
    min_confidence: float = 0.7
    fallback_to_generic: bool = True
