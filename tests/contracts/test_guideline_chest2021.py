from __future__ import annotations

from pathlib import Path

import pytest

from medparse.pipeline.run_extract import run_extract

CONFIG_PATH = Path("configs/run_article.yaml")
CHEST_PDF = Path("data/Input pdfs/articles/pdf/Guildeline lung cancer screening 2021.pdf")


@pytest.mark.skipif(not CHEST_PDF.exists(), reason="CHEST guideline fixture not available")
def test_chest_guideline_contract():
    outcome = run_extract(
        pdf_path=CHEST_PDF,
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
    assert len(recommendations) >= 16
    with_grade = [rec for rec in recommendations if rec.grade_normalized]
    consensus_items = [rec for rec in recommendations if getattr(rec, "ungraded", False)]
    grade_density = len(with_grade) / len(recommendations) if recommendations else 0.0
    typed_density = sum(1 for rec in recommendations if rec.grade_normalized or getattr(rec, "ungraded", False)) / len(recommendations) if recommendations else 0.0
    assert grade_density >= 0.70
    assert typed_density == pytest.approx(1.0, rel=1e-3)
    assert consensus_items, "Expected ungraded consensus entries for UCS guidance"
    scales = {rec.grade_normalized.get("scale") for rec in with_grade if rec.grade_normalized}
    assert "CHEST" in scales
    assert all(
        rec.grade_normalized.get("value")
        for rec in with_grade
        if rec.grade_normalized and not rec.grade_normalized.get("ungraded")
    )
    assert any(rec.grade_normalized.get("source") == "table" for rec in with_grade), "Expected at least one table-sourced grade"

    payload = outcome.to_payload()
    metrics = payload.get("_metrics", {})
    assert metrics.get("recommendations_count", 0) >= 16
    assert metrics.get("grade_density", 0.0) >= 0.70
    assert metrics.get("typed_density", 0.0) == pytest.approx(1.0, rel=1e-3)
    breakdown = metrics.get("grade_source_breakdown", {})
    assert breakdown.get("table", 0) > 0

    metadata = payload.get("_pipeline_metadata", {})
    if metadata.get("umls_status") == "ok":
        assert metrics.get("umls_entities", 0) > 0

    assert metadata.get("window_placeholders_removed", 0) == 0
    assert metadata.get("grade_scale_hint") == "CHEST"
