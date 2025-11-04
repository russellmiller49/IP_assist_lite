"""Manufacturer detection utilities for IFU documents."""

from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import yaml

from medparse.ingest.models import PageData
from medparse.utils.log import get_logger

LOGGER = get_logger(__name__)

CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "_shared" / "ifu_manufacturers.yaml"


@dataclass(slots=True)
class ManufacturerDetection:
    """Structured manufacturer detection outcome."""

    name: Optional[str] = None
    confidence: str = "unknown"
    source: str = "unknown"

    def as_dict(self) -> Dict[str, Optional[str]]:
        return {
            "name": self.name,
            "confidence": self.confidence,
            "source": self.source,
        }


@functools.lru_cache(maxsize=1)
def _load_config() -> Dict[str, object]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.debug("Failed to load IFU manufacturer config: %s", exc)
        return {}

    entries: List[Dict[str, object]] = []
    for entry in data.get("manufacturers", []) or []:
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        aliases = [str(alias).strip().lower() for alias in entry.get("aliases", []) or [] if str(alias).strip()]
        hints = [str(hint).strip().lower() for hint in entry.get("hints", []) or [] if str(hint).strip()]
        entries.append(
            {
                "name": name,
                "aliases": aliases,
                "hints": hints,
            }
        )

    fallback_hints = {}
    for key, value in (data.get("fallback_hints") or {}).items():
        if not isinstance(value, dict):
            continue
        fallback_hints[str(key).lower()] = {
            "name": value.get("name"),
            "confidence": value.get("confidence", "low"),
        }

    return {
        "entries": entries,
        "fallback_hints": fallback_hints,
    }


def _normalize_text(value: Sequence[PageData], max_pages: int) -> str:
    buffer: List[str] = []
    for page in value[:max_pages]:
        text = (page.text or "").strip()
        if text:
            buffer.append(text.lower())
    return " ".join(buffer)


def detect_manufacturer(
    pages: Sequence[PageData],
    *,
    metadata_title: Optional[str] = None,
    pdf_path: Optional[Path] = None,
    max_pages: int = 5,
) -> Dict[str, Optional[str]]:
    """Detect manufacturer for an IFU using cover text, metadata, and filename hints."""

    config = _load_config()
    entries: Sequence[Dict[str, object]] = config.get("entries", [])  # type: ignore[assignment]
    fallback_hints: Dict[str, Dict[str, object]] = config.get("fallback_hints", {})  # type: ignore[assignment]

    cover_text = _normalize_text(pages, max_pages)
    tail_text = _normalize_text(list(reversed(pages)), min(max_pages, len(pages)))

    detection = _scan_entries(entries, cover_text)
    if detection:
        detection.source = "cover"
        return detection.as_dict()

    if tail_text:
        detection = _scan_entries(entries, tail_text)
        if detection:
            detection.source = "tail"
            return detection.as_dict()

    normalized_title = (metadata_title or "").replace("_", " ").lower()
    if normalized_title:
        detection = _scan_entries(entries, normalized_title, confidence="medium")
        if detection:
            detection.source = "metadata_title"
            return detection.as_dict()

    file_hint = (pdf_path.name if pdf_path else metadata_title or "").lower()
    for hint, payload in fallback_hints.items():
        if hint and hint in file_hint:
            name = payload.get("name")
            if name:
                return ManufacturerDetection(
                    name=str(name),
                    confidence=str(payload.get("confidence", "low")),
                    source="filename",
                ).as_dict()

    hint_detection = _scan_hint_entries(entries, cover_text or tail_text or "")
    if hint_detection:
        return hint_detection.as_dict()

    return {}


def _scan_entries(
    entries: Sequence[Dict[str, object]],
    haystack: str,
    *,
    confidence: str = "high",
) -> Optional[ManufacturerDetection]:
    if not haystack:
        return None

    for entry in entries:
        name = entry.get("name")
        if not name:
            continue
        tokens = [str(name).lower()]
        tokens.extend(entry.get("aliases", []))  # type: ignore[arg-type]
        for token in tokens:
            token = str(token).strip().lower()
            if token and token in haystack:
                return ManufacturerDetection(name=str(name), confidence=confidence, source="cover")
    return None


def _scan_hint_entries(
    entries: Sequence[Dict[str, object]],
    haystack: str,
) -> Optional[ManufacturerDetection]:
    if not haystack:
        return None

    for entry in entries:
        name = entry.get("name")
        hints = entry.get("hints", [])  # type: ignore[assignment]
        if not name or not hints:
            continue
        for hint in hints:
            hint_value = str(hint).strip().lower()
            if hint_value and hint_value in haystack:
                return ManufacturerDetection(name=str(name), confidence="medium", source="keyword")
    return None


__all__ = ["detect_manufacturer"]
