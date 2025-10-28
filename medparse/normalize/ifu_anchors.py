"""Anchor-driven extraction of IFU clinical blocks with TOC guard."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from medparse.ingest.models import PageData
from medparse.normalize.layout import is_toc_page, slice_between
from medparse.normalize.text_cleanup import clean_paragraph
from medparse.utils.log import get_logger

LOGGER = get_logger(__name__)


@dataclass
class AnchorBleedError(Exception):
    anchor: str

    def __str__(self) -> str:  # pragma: no cover - human readable
        return f"anchor '{self.anchor}' captured table-of-contents bleed"


CLINICAL_ANCHORS = {
    "indications_for_use": {
        "start": ["indications for use"],
        "stops": ["intended use", "intended user", "contraindications", "warnings"],
    },
    "intended_use": {
        "start": ["intended use"],
        "stops": ["intended user", "contraindications", "warnings", "adverse events"],
    },
    "intended_user": {
        "start": ["intended user", "user"],
        "stops": ["contraindications", "warnings", "adverse events"],
    },
    "contraindications": {
        "start": ["contraindications"],
        "stops": ["warnings", "adverse events", "precautions"],
    },
    "adverse_events": {
        "start": ["adverse events", "complications"],
        "stops": ["warnings", "precautions", "maintenance"],
    },
}


def extract_clinical_block(
    pages: Sequence[PageData],
    *,
    start: Sequence[str],
    stops: Sequence[str] | None = None,
) -> str | None:
    safe_pages = [page for page in pages if not is_toc_page(page)]
    if not safe_pages:
        return None

    span = slice_between(
        safe_pages,
        start_anchors=start,
        stop_anchors=stops or (),
        guard_fn=None,
    )
    if not span:
        return None

    if looks_like_toc(span):
        raise AnchorBleedError(start[0])

    cleaned = clean_paragraph(span)
    return normalize_bullets(cleaned)


def lift_ifu_clinical_fields(pages: Sequence[PageData], ifu_json: dict) -> None:
    for field, anchors in CLINICAL_ANCHORS.items():
        try:
            block = extract_clinical_block(
                pages,
                start=anchors["start"],
                stops=anchors.get("stops", []),
            )
        except AnchorBleedError as exc:
            LOGGER.debug("Skipping %s due to TOC bleed: %s", field, exc)
            continue
        if block:
            ifu_json[field] = block

    # Rx-only detection for intended_user
    combined_text = "\n".join(page.text for page in pages if page.text)
    if re.search(r"\bRx\s*only\b", combined_text, re.IGNORECASE):
        ifu_json.setdefault("intended_user", "Rx only")

    for key in ("contraindications", "adverse_events"):
        value = ifu_json.get(key)
        if isinstance(value, str) and value:
            ifu_json[key] = [value]
        elif not value:
            ifu_json[key] = []


def looks_like_toc(text: str) -> bool:
    lowered = text.lower()
    if "table of contents" in lowered:
        return True

    dotted_lines = sum(1 for line in text.splitlines() if re.search(r"\.{4,}", line))
    if dotted_lines >= 3:
        return True

    return False


def normalize_bullets(text: str) -> str:
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line[0] in {"•", "-", "*"}:
            token = line[1:].strip()
            lines.append(f"- {token}")
        else:
            lines.append(line)
    return "\n".join(lines)


__all__ = ["AnchorBleedError", "extract_clinical_block", "lift_ifu_clinical_fields"]
