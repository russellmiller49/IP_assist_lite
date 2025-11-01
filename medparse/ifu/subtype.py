"""Heuristics to infer IFU document subtypes."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Sequence

from medparse.ingest.models import PageData

CATALOG_TOKENS = {
    "units and modules",
    "catalog",
    "catalogue",
    "legend",
    "product overview",
}

INSTALL_TOKENS = {
    "mounting instruction",
    "installation guide",
    "installation instructions",
    "installation manual",
    "assembly instructions",
    "systemcarrier performance",
}

PART_NUMBER_PATTERN = re.compile(r"\b\d{5}-\d{3}\b")


def infer_ifu_subtype_from_text(text: str, pdf_name: str = "") -> Optional[str]:
    lowered = text.lower()
    name_lower = pdf_name.lower()

    if any(token in lowered or token in name_lower for token in INSTALL_TOKENS):
        return "installation_guide"

    catalog_hint = any(token in lowered or token in name_lower for token in CATALOG_TOKENS)
    pn_hits = len(PART_NUMBER_PATTERN.findall(lowered))
    if catalog_hint or pn_hits >= 8:
        return "catalog"

    return None


def infer_ifu_subtype_from_pages(pages: Sequence[PageData], pdf_path: Path) -> Optional[str]:
    sample_text = " ".join(page.text for page in pages[:4] if page.text)
    if not sample_text:
        sample_text = ""
    return infer_ifu_subtype_from_text(sample_text, pdf_path.name)


__all__ = [
    "infer_ifu_subtype_from_pages",
    "infer_ifu_subtype_from_text",
]

