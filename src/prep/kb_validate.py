"""Validate generated knowledge base markdown files for simple structural checks."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Any

PMID_RE = re.compile(r"\bPMID[:\s]*([0-9]{7,8})\b", re.IGNORECASE)
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b", re.IGNORECASE)
MD_TABLE_RE = re.compile(r"^\|.+\|\s*$\n^\|(?:\s*:?-+:?\s*\|)+\s*$", re.MULTILINE)

THRESHOLD_RE = re.compile(r"(?:>=|<=|>|<|\bthreshold\b)", re.IGNORECASE)
THRESHOLD_SYMBOLS = {"\u2265", "\u2264"}


def validate_file(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    evidence_ids = set(PMID_RE.findall(text)) | set(DOI_RE.findall(text))
    lower_text = text.lower()
    return {
        "has_required_sections": all(token in lower_text for token in ["epidemiology", "diagnostic", "management", "evidence", "reference"]),
        "evidence_count": len(evidence_ids),
        "has_tables": bool(MD_TABLE_RE.search(text)),
        "has_thresholds": bool(THRESHOLD_RE.search(text) or any(symbol in text for symbol in THRESHOLD_SYMBOLS)),
        "has_algorithms": bool(re.search(r"\balgorithm|workflow|protocol\b", lower_text, re.IGNORECASE)),
        "word_count": len(text.split()),
    }


def main() -> None:
    base = Path("data/structured_knowledge/diseases")
    if not base.exists():
        print(f"no disease files found -> {base}")
        return
    for path in sorted(base.glob("*.md")):
        print(f"{path.name}: {validate_file(path)}")


if __name__ == "__main__":
    main()
