from __future__ import annotations

from pathlib import Path

import pytest

from medparse.pipeline.run_extract import run_extract

CONFIG_PATH = Path("configs/run_article.yaml")
ATS_PDF = Path("data/Input pdfs/articles/pdf/Guideline ATS diagnostic yield.pdf")


def test_ats_statement_has_summary_structures():
    if not ATS_PDF.exists():
        pytest.skip("ATS statement fixture not available")

    outcome = run_extract(
        pdf_path=ATS_PDF,
        config_path=CONFIG_PATH,
        use_cache=False,
        force_deep=False,
        profile_override="enriched",
    )
    assert outcome.success, outcome.failure_reason or "extraction failed"
    document = outcome.document
    assert document is not None

    assert document.doc_subtype == "statement"
    assert document.key_points and len(document.key_points) >= 15
    assert any("strict" in point.text.lower() for point in document.key_points)

    assert document.definitions
    assert "diagnostic_yield" in document.definitions
    diag_def = document.definitions["diagnostic_yield"]
    assert diag_def.text
    assert diag_def.evidence_refs, "diagnostic yield definition missing evidence refs"

    assert document.diagnostic_flow is not None
    assert document.diagnostic_flow.formula

    metrics = outcome.metrics
    ats_metrics = metrics.get("ats")
    assert ats_metrics is not None
    assert "compatible" in ats_metrics
    assert metrics.get("paragraph_dedup_applied") is not None
