"""IFU-specific validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from medparse.config import ExtractionConfig, FrozenNamespace
from medparse.schema.ifu import IFUDocument

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class Issue:
    message: str
    severity: Severity = "error"

    @classmethod
    def error(cls, message: str) -> "Issue":
        return cls(message=message, severity="error")

    @classmethod
    def warn(cls, message: str) -> "Issue":
        return cls(message=message, severity="warning")


def validate_ifu(document: IFUDocument, config: ExtractionConfig) -> list[Issue]:
    issues: list[Issue] = []

    threshold_block = _resolve_threshold_block(config, document.manufacturer)
    strict_front = bool(getattr(threshold_block, "strict_front_matter", False))
    fm_severity = Issue.error if strict_front else Issue.warn

    for field in ("part_number", "revision", "publication_date", "model"):
        value = getattr(document, field)
        if not value:
            issues.append(fm_severity(f"IFU missing front-matter field '{field}'."))

    return issues


def _resolve_threshold_block(
    config: ExtractionConfig,
    manufacturer: Optional[str],
) -> FrozenNamespace:
    thresholds = config.thresholds
    default_block = getattr(thresholds, "default", FrozenNamespace())

    if not manufacturer:
        return default_block

    manufacturer_lower = manufacturer.lower()
    for key, value in thresholds.items():
        if isinstance(value, FrozenNamespace) and key.lower() == manufacturer_lower:
            return value

    normalized = manufacturer_lower.replace(" ", "_")
    candidate = getattr(thresholds, normalized, None)
    if isinstance(candidate, FrozenNamespace):
        return candidate

    return default_block


__all__ = ["Issue", "validate_ifu"]
