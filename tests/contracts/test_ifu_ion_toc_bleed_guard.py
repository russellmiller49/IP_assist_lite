from __future__ import annotations

from pathlib import Path

import pytest

from medparse.pipeline.run_extract import run_extract

CONFIG_PATH = Path("configs/run_ifu.yaml")
ION_PDF = Path(
    "data/Input pdfs/IFUs/pdf/Ion Endoluminal System, Instruments, and Accessories User Manual(553990-11).pdf"
)


@pytest.mark.skipif(not ION_PDF.exists(), reason="Ion IFU fixture not available")
def test_ion_manual_toc_anchors_clean() -> None:
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
    anchors_bleed = pipeline.get("anchors_bleed") or {}
    fields = (
        "indications_for_use",
        "warnings",
        "sterilization",
        "clinical_risks_and_benefits",
    )

    for field in fields:
        assert anchors_bleed.get(field, 0) == 0, f"Unexpected bleed recorded for {field}"
        value = getattr(document, field, "")
        if isinstance(value, dict):
            field_text = value.get("text", "") or ""
        else:
            field_text = value or ""
        assert "Table of Contents" not in field_text
        assert not field_text.strip().lower().startswith("table of contents")
