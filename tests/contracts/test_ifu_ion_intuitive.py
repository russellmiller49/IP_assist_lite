from __future__ import annotations

from pathlib import Path

import pytest

from medparse.pipeline.run_extract import run_extract

CONFIG_PATH = Path("configs/run_ifu.yaml")
ION_PDF = Path(
    "data/Input pdfs/IFUs/pdf/Ion Endoluminal System, Instruments, and Accessories User Manual(553990-11).pdf"
)


@pytest.mark.skipif(not ION_PDF.exists(), reason="Ion IFU fixture not available")
def test_ion_manual_toc_guard_and_anchor_hygiene() -> None:
    outcome = run_extract(
        pdf_path=ION_PDF,
        config_path=CONFIG_PATH,
        use_cache=False,
        force_deep=False,
        profile_override="enriched",
    )
    assert outcome.success, outcome.failure_reason or "extraction failed"

    document = outcome.document
    assert document is not None

    pipeline = document.pipeline_info
    assert pipeline.get("anchor_bleed_errors") in (None, [])
    anchors_bleed = pipeline.get("anchors_bleed") or {}
    for anchor in ("indications_for_use", "warnings", "sterilization"):
        assert anchors_bleed.get(anchor, 0) == 0

    dropped_pages = pipeline.get("toc_guard_pages_dropped") or []
    assert pipeline.get("toc_guard_applied") is True
    assert pipeline.get("toc_guard_pages_dropped_count", 0) >= 3
    expected_drop = {5, 6, 7, 8, 9}
    assert expected_drop.issubset(set(dropped_pages)), dropped_pages

    assert pipeline.get("references_anchor_backfill") is True
    references_anchor = pipeline.get("references_anchor") or {}
    assert references_anchor.get("pages")

    text_fields = [
        getattr(document, "indications_for_use", None),
        getattr(document, "warnings", None),
        getattr(document, "sterilization", None),
    ]
    for field in text_fields:
        if isinstance(field, str) and field:
            assert "Table of Contents" not in field

    indications = document.indications_for_use
    assert isinstance(indications, dict)
    assert indications.get("provenance") == "anchor_numbered"
    assert indications.get("anchors_used")
