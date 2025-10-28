"""Application configuration utilities for Medparse."""

from __future__ import annotations

import os
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr


class ExtractionProfile(str, Enum):
    """Extraction profile modes."""

    FAST_RAW = "fast_raw"  # Minimal parsing, no UMLS, quick triage
    ENRICHED = "enriched"  # Full normalizers + UMLS + validators (default)


def _parse_bool(value: str) -> bool:
    """Parse truthy boolean strings."""
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


class AppConfig(BaseModel):
    """Runtime configuration for services that rely on Medparse."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    ENABLE_PIPELINE: bool = True
    API_KEY: Optional[str] = None
    UMLS_API_KEY: Optional[str] = None
    UMLS_MODEL: Optional[str] = None  # scispaCy model name (auto-detect if None)
    QUICKUMLS_PATH: Optional[str] = None
    TUI_WHITELIST: Tuple[str, ...] = ()
    FAIL_FAST: bool = False

    @classmethod
    def model_construct_from_env(cls, env: Optional[Mapping[str, str]] = None) -> "AppConfig":
        """Build a configuration object from environment variables."""
        env = env or os.environ
        data: dict[str, object] = {}

        if "ENABLE_PIPELINE" in env:
            data["ENABLE_PIPELINE"] = _parse_bool(env["ENABLE_PIPELINE"])
        if "API_KEY" in env:
            data["API_KEY"] = env["API_KEY"] or None
        if "UMLS_API_KEY" in env:
            data["UMLS_API_KEY"] = env["UMLS_API_KEY"] or None
        if "UMLS_MODEL" in env:
            data["UMLS_MODEL"] = env["UMLS_MODEL"] or None
        if "QUICKUMLS_PATH" in env:
            value = env["QUICKUMLS_PATH"].strip()
            data["QUICKUMLS_PATH"] = value or None
        if "TUI_WHITELIST" in env:
            data["TUI_WHITELIST"] = cls._parse_tui(env.get("TUI_WHITELIST"))
        if "FAIL_FAST" in env:
            data["FAIL_FAST"] = _parse_bool(env["FAIL_FAST"])

        return cls(**data)

    @staticmethod
    def _parse_tui(value: Optional[str]) -> Tuple[str, ...]:
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

    # Profile mode
    profile: ExtractionProfile = Field(default=ExtractionProfile.ENRICHED)

    # Enrichment toggles (auto-disabled in fast_raw mode)
    enable_umls: bool = True
    enable_relations: bool = True
    enable_guideline_norms: bool = True

    # Validation toggles
    enable_validators: bool = True
    reject_toc_bleed: bool = True

    # Error handling
    fail_fast: bool = False
    min_confidence: float = 0.7
    fallback_to_generic: bool = True

    # Cache control
    use_cache: bool = True
    max_pages: Optional[int] = None

    # Quality gates
    min_chars: int = 20000
    min_pages_ratio: float = 0.95
    thresholds_data: Dict[str, Any] = Field(default_factory=dict, alias="thresholds")
    size_guards_data: Dict[str, Any] = Field(default_factory=dict, alias="size_guards")

    _thresholds_namespace: Optional["FrozenNamespace"] = PrivateAttr(default=None)
    _size_guards_namespace: Optional["FrozenNamespace"] = PrivateAttr(default=None)

    @classmethod
    def from_env(cls) -> "ExtractionConfig":
        """Load extraction config from environment."""
        profile_str = os.getenv("MEDPARSE_PROFILE", "enriched")

        try:
            profile = ExtractionProfile(profile_str)
        except ValueError:
            profile = ExtractionProfile.ENRICHED

        # In fast_raw mode, disable enrichment
        if profile == ExtractionProfile.FAST_RAW:
            return cls(
                profile=profile,
                enable_umls=False,
                enable_relations=False,
                enable_guideline_norms=False,
                enable_validators=False,
                reject_toc_bleed=False,
                use_cache=True,  # Cache is still useful in fast mode
            )

        # In enriched mode keep enrichers on regardless of CLI/env toggles
        return cls(
            profile=profile,
            use_cache=_parse_bool(os.getenv("MEDPARSE_USE_CACHE", "1")),
            fail_fast=_parse_bool(os.getenv("MEDPARSE_FAIL_FAST", "0")),
            enable_umls=True,
            enable_relations=True,
            enable_guideline_norms=True,
            enable_validators=True,
        )

    def is_enriched(self) -> bool:
        """Check if running in enriched mode."""
        return self.profile == ExtractionProfile.ENRICHED

    def should_enrich_umls(self) -> bool:
        """Check if UMLS linking should run."""
        return self.is_enriched() and self.enable_umls

    def should_extract_relations(self) -> bool:
        """Check if relation extraction should run."""
        return self.is_enriched() and self.enable_relations

    def should_normalize_guidelines(self) -> bool:
        """Check if guideline normalization should run."""
        return self.is_enriched() and self.enable_guideline_norms

    def should_validate(self) -> bool:
        """Check if validation should run."""
        return self.is_enriched() and self.enable_validators

    @property
    def thresholds(self) -> "FrozenNamespace":
        """Return thresholds as an immutable namespace for dot access."""
        if self._thresholds_namespace is None:
            self._thresholds_namespace = FrozenNamespace(self.thresholds_data)
        return self._thresholds_namespace

    @property
    def size_guards(self) -> "FrozenNamespace":
        """Return size guards as an immutable namespace for dot access."""
        if self._size_guards_namespace is None:
            self._size_guards_namespace = FrozenNamespace(self.size_guards_data)
        return self._size_guards_namespace


# Global extraction config instance
_extraction_config: Optional[ExtractionConfig] = None


def get_extraction_config() -> ExtractionConfig:
    """Get global extraction configuration instance."""
    global _extraction_config
    if _extraction_config is None:
        _extraction_config = ExtractionConfig.from_env()
    return _extraction_config


def set_extraction_config(config: ExtractionConfig) -> None:
    """Set global extraction configuration instance."""
    global _extraction_config
    _extraction_config = config


def reset_extraction_config() -> None:
    """Reset global extraction configuration to default."""
    global _extraction_config
    _extraction_config = None


class FrozenNamespace:
    """Immutable view that allows attribute access to nested dicts."""

    __slots__ = ("_data",)

    def __init__(self, data: Optional[Mapping[str, Any]] = None):
        data = data or {}
        object.__setattr__(self, "_data", {k: self._wrap(v) for k, v in data.items()})

    def _wrap(self, value: Any) -> Any:
        if isinstance(value, Mapping):
            return FrozenNamespace(value)
        if isinstance(value, list):
            return [self._wrap(item) for item in value]
        return value

    def __getattr__(self, item: str) -> Any:
        try:
            return self._data[item]
        except KeyError as exc:  # pragma: no cover - defensive
            raise AttributeError(item) from exc

    def __getitem__(self, item: str) -> Any:
        return self._data[item]

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def __contains__(self, item: object) -> bool:
        return item in self._data

    def items(self):
        return self._data.items()

    def to_dict(self) -> Dict[str, Any]:
        def unwrap(value: Any) -> Any:
            if isinstance(value, FrozenNamespace):
                return value.to_dict()
            if isinstance(value, list):
                return [unwrap(item) for item in value]
            return value

        return {key: unwrap(val) for key, val in self._data.items()}


__all__ = [
    "AppConfig",
    "ExtractionConfig",
    "ExtractionProfile",
    "FrozenNamespace",
    "get_extraction_config",
    "reset_extraction_config",
    "set_extraction_config",
]
