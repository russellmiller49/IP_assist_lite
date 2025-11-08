from __future__ import annotations

from pathlib import Path

import pytest

from medparse.pipeline.run_extract import run_extract

CONFIG_PATH = Path("configs/run_article.yaml")
VERITAS_PDF = Path("data/Input pdfs/articles/pdf/VERITAS.pdf")
VENT_PDF = Path("data/Input pdfs/articles/pdf/VENT Trial.pdf")
JVIR_PDF = Path("data/Input pdfs/articles/pdf/Value of Antibiotic Prophylaxis for Percutaneo.pdf")
VALUE_BASED_PDF = Path("data/Input pdfs/articles/pdf/Value-Based Proposition for a Dedicated IP suite.pdf")


def _run_pdf(pdf_path: Path):
    if not pdf_path.exists():
        pytest.skip(f"Fixture missing: {pdf_path}")
    outcome = run_extract(
        pdf_path=pdf_path,
        config_path=CONFIG_PATH,
        use_cache=False,
        force_deep=False,
        profile_override="enriched",
    )
    assert outcome.success, outcome.failure_reason or "extraction failed"
    assert outcome.document is not None
    return outcome


def test_scope_editorial_economics_imrad_skip() -> None:
    outcome = _run_pdf(VALUE_BASED_PDF)
    metrics = outcome.metrics
    assert metrics.get("research_scope") == "editorial_or_economics"
    assert metrics.get("imrad_required") is False
    assert metrics.get("ats_yield_required") is False


def test_scope_vent_therapeutic_skips_yield() -> None:
    outcome = _run_pdf(VENT_PDF)
    document = outcome.document
    assert document is not None
    assert document.research_scope == "research_therapeutic"

    metrics = outcome.metrics
    assert metrics.get("ats_yield_required") is False
    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    reasons = pipeline_info.get("ats_yield_reasons") or []
    assert any("research_scope:research_therapeutic" in reason or reason == "not_diagnostic_study" for reason in reasons)


def test_scope_jvir_non_bronchoscopic() -> None:
    outcome = _run_pdf(JVIR_PDF)
    document = outcome.document
    assert document is not None
    assert document.research_scope == "non_bronchoscopic"

    metrics = outcome.metrics
    assert metrics.get("ats_yield_required") is False
    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    reasons = pipeline_info.get("ats_yield_reasons") or []
    assert any("non_bronchoscopic" in reason for reason in reasons)


def test_scope_veritas_diagnostic_flags_requirements() -> None:
    outcome = _run_pdf(VERITAS_PDF)
    document = outcome.document
    assert document is not None
    assert document.research_scope == "diagnostic_ppn_bronchoscopy"

    metrics = outcome.metrics
    assert metrics.get("imrad_required") is True
    assert metrics.get("ats_yield_required") is True

    research = getattr(document, "research_outcomes", None)
    assert research is not None
    assert getattr(research, "diagnostic_accuracy", None) is not None
