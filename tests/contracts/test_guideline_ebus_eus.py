from __future__ import annotations

from pathlib import Path

import pytest

from medparse.pipeline.run_extract import run_extract

CONFIG_PATH = Path("configs/run_article.yaml")
EBUS_PDF = Path("data/Input pdfs/articles/pdf/Combined EBUS  EUS for the diagnosis and staging of lung cancer ESGE, ERS, ESTS Guideline.pdf")


@pytest.mark.skipif(not EBUS_PDF.exists(), reason="EBUS/EUS guideline fixture not available")
def test_ebus_guideline_contract():
    outcome = run_extract(
        pdf_path=EBUS_PDF,
        config_path=CONFIG_PATH,
        use_cache=False,
        force_deep=False,
        profile_override="enriched",
    )
    assert outcome.success, outcome.failure_reason or "extraction failed"

    document = outcome.document
    assert document is not None
    assert document.doc_subtype == "guideline"

    recommendations = document.recommendations or []
    assert len(recommendations) >= 8
    with_grade = [rec for rec in recommendations if rec.grade_normalized]
    sign_inline = [
        rec
        for rec in recommendations
        if rec.grade_normalized
        and rec.grade_normalized.get("scale") == "SIGN"
        and rec.grade_normalized.get("source") == "inline"
        and rec.grade_normalized.get("letter")
    ]
    grade_density = len(with_grade) / len(recommendations) if recommendations else 0.0
    typed_density = sum(1 for rec in recommendations if rec.grade_normalized or getattr(rec, "ungraded", False)) / len(recommendations) if recommendations else 0.0
    assert grade_density >= 0.70
    assert typed_density >= 0.95
    assert sign_inline, "Expected SIGN inline detections"

    payload = outcome.to_payload()
    metrics = payload.get("_metrics", {})
    assert metrics.get("recommendations_count", 0) >= 8
    assert metrics.get("grade_density", 0.0) >= 0.70
    assert metrics.get("typed_density", 0.0) >= 0.95
    breakdown = metrics.get("grade_source_breakdown", {})
    assert breakdown.get("inline", 0) > 0

    metadata = payload.get("_pipeline_metadata", {})
    if metadata.get("umls_status") == "ok":
        assert metrics.get("umls_entities", 0) > 0

    assert metadata.get("window_placeholders_removed", 0) == 0
