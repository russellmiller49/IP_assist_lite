from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from medparse.pipeline.run_extract import run_extract

CONFIG_PATH = Path("configs/run_article.yaml")
GUIDELINE_PDF = Path(
    "data/Input pdfs/articles/pdf/Combined EBUS  EUS for the diagnosis and staging of lung cancer ESGE, ERS, ESTS Guideline.pdf"
)
DROP_DEBUG = re.compile(r"^page\s+\d+\s+window<=\d+\s+tokens$", re.IGNORECASE)


def _run_extract(pdf_path: Path, emit_policy: str | None = None):
    emit_overrides = {"evidence_policy": emit_policy} if emit_policy else None
    outcome = run_extract(
        pdf_path=pdf_path,
        config_path=CONFIG_PATH,
        use_cache=False,
        force_deep=False,
        profile_override="enriched",
        emit_overrides=emit_overrides,
    )
    assert outcome.success, outcome.failure_reason or "extraction failed"
    assert outcome.document is not None
    return outcome


def _payload_size(outcome) -> int:
    payload = outcome.to_payload()
    return len(json.dumps(payload, ensure_ascii=False))


def test_emit_compact_cleans_debug_evidence_and_reduces_size() -> None:
    if not GUIDELINE_PDF.exists():
        pytest.skip("Guideline fixture PDF not available")

    compact_outcome = _run_extract(GUIDELINE_PDF, emit_policy="compact")
    verbatim_outcome = _run_extract(GUIDELINE_PDF, emit_policy="verbatim")

    assert _payload_size(compact_outcome) < _payload_size(verbatim_outcome)

    document = compact_outcome.document
    assert document is not None
    bank = getattr(document, "evidence_bank", {}) or {}
    paragraph_store = getattr(document, "paragraph_store", {}) or {}
    for payload in bank.values():
        if not isinstance(payload, dict):
            continue
        snippet = str(payload.get("text") or "").strip()
        if not snippet:
            paragraph_hash = payload.get("paragraph_hash") or payload.get("hash")
            if paragraph_hash is not None and isinstance(paragraph_store, dict):
                entry = paragraph_store.get(paragraph_hash)
                if isinstance(entry, dict):
                    snippet = str(entry.get("text") or "").strip()
        assert not snippet or not DROP_DEBUG.match(snippet)
