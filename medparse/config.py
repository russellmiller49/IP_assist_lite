"""Application configuration utilities for Medparse."""

from __future__ import annotations

import os
from enum import Enum
from typing import Mapping, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field


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

        # In enriched mode, respect individual flags
        return cls(
            profile=profile,
            enable_umls=_parse_bool(os.getenv("MEDPARSE_ENABLE_UMLS", "1")),
            enable_relations=_parse_bool(os.getenv("MEDPARSE_ENABLE_RELATIONS", "1")),
            enable_guideline_norms=_parse_bool(os.getenv("MEDPARSE_ENABLE_GUIDELINE_NORMS", "1")),
            enable_validators=_parse_bool(os.getenv("MEDPARSE_ENABLE_VALIDATORS", "1")),
            use_cache=_parse_bool(os.getenv("MEDPARSE_USE_CACHE", "1")),
            fail_fast=_parse_bool(os.getenv("MEDPARSE_FAIL_FAST", "0")),
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
