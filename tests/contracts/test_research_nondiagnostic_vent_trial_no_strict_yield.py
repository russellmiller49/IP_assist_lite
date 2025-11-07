from __future__ import annotations

from pathlib import Path

import pytest

from medparse.pipeline.run_extract import run_extract

CONFIG_PATH = Path("configs/run_article.yaml")
VENT_PDF = Path("data/Input pdfs/articles/pdf/VENT Trial.pdf")


@pytest.mark.skipif(not VENT_PDF.exists(), reason="VENT trial fixture not available")
def test_research_nondiagnostic_vent_trial_no_strict_yield() -> None:
    outcome = run_extract(
        pdf_path=VENT_PDF,
        config_path=CONFIG_PATH,
        use_cache=False,
        force_deep=False,
        profile_override="enriched",
    )

    assert outcome.success, outcome.failure_reason or "extraction failed"
    document = outcome.document
    assert document is not None
    assert document.doc_subtype == "research_therapeutic"

    ats_meta = getattr(document, "ats_compatibility", None)
    assert ats_meta is not None
    assert ats_meta.compatible_with_ats is False
    assert "not_diagnostic_study" in (ats_meta.exclusion_reasons or [])

    metrics = outcome.metrics
    ats_metrics = metrics.get("ats")
    assert ats_metrics is not None
    assert ats_metrics.get("compatible") is False
    assert "not_diagnostic_study" in ats_metrics.get("exclusion_reasons", [])

    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    assert pipeline_info.get("ats_yield_applicability") == "not_applicable"
    reasons = pipeline_info.get("ats_yield_reasons") or []
    assert any(reason.startswith("doc_subtype:") for reason in reasons)
    assert "not_diagnostic_study" in reasons

    errors = [issue for issue in outcome.validator_issues if issue.severity == "error"]
    assert not errors
