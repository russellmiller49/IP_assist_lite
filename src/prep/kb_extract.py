"""Run structured extraction across knowledge base documents."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from src.adapters.openai_responses import Extraction, extract_structured

IN_DIR = Path("data/knowledge_base")
OUT_JSON = Path("data/structured_knowledge/extractions.json")
OUT_JSON.parent.mkdir(parents=True, exist_ok=True)


def _extract_file(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if not text.strip():
        raise ValueError("empty file")
    payload = extract_structured(text[:150_000])
    if isinstance(payload, Extraction):
        payload = payload.model_dump()
    return {"file": str(path), "extraction": payload}


def run() -> List[Dict[str, Any]]:
    if not IN_DIR.exists():
        print(f"knowledge base directory missing -> {IN_DIR}")
        return []

    rows: List[Dict[str, Any]] = []
    for path in sorted(IN_DIR.rglob("*")):
        if path.is_dir() or path.suffix.lower() not in {".md", ".txt"}:
            continue
        try:
            rows.append(_extract_file(path))
        except Exception as exc:  # keep pipeline moving but surface failure
            rows.append({"file": str(path), "error": str(exc)})
            continue

    OUT_JSON.write_text(json.dumps(rows, indent=2))
    print(f"extracted {sum(1 for row in rows if 'extraction' in row)} records -> {OUT_JSON}")
    return rows


if __name__ == "__main__":
    run()
