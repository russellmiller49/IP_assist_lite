from __future__ import annotations

from pathlib import Path

import pytest

from medparse.pipeline.run_extract import run_extract

CONFIG_PATH = Path("configs/run_article.yaml")
VALUE_BASED_PDF = Path("data/Input pdfs/articles/pdf/Value-Based Proposition for a Dedicated IP suite.pdf")


@pytest.mark.skipif(not VALUE_BASED_PDF.exists(), reason="Value-Based editorial fixture not available")
def test_value_based_editorial_skips_imrad_and_yield() -> None:
    outcome = run_extract(
        pdf_path=VALUE_BASED_PDF,
        config_path=CONFIG_PATH,
        use_cache=False,
        force_deep=False,
        profile_override="enriched",
    )

    assert outcome.success, outcome.failure_reason or "extraction failed"
    document = outcome.document
    assert document is not None
    assert document.doc_subtype == "editorial_or_economics"
    assert document.research_scope == "editorial_or_economics"

    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    assert pipeline_info.get("imrad_required") is False
    assert pipeline_info.get("ats_yield_applicability") == "not_applicable"
    assert pipeline_info.get("ats_yield_reasons")

    metrics = outcome.metrics
    assert metrics.get("imrad_required") is False
    assert metrics.get("ats_yield_required") is False
    assert metrics.get("research_scope") == "editorial_or_economics"

    error_messages = [issue.message for issue in outcome.validator_issues if issue.severity == "error"]
    assert "Research article has too few sections" not in error_messages
