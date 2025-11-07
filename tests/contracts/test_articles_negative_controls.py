from __future__ import annotations

from pathlib import Path

import pytest

from medparse.pipeline.run_extract import run_extract

CONFIG_PATH = Path("configs/run_article.yaml")
NEGATIVE_CASES = [
    (
        Path("data/Input pdfs/articles/pdf/VENT Trial.pdf"),
        {
            "expect_doc_subtype": "research_therapeutic",
            "expect_applicability": "not_applicable",
        },
    ),
    (
        Path("data/Input pdfs/articles/pdf/Valipour-2020-Bronchial Rheoplasty for Treatme.pdf"),
        {
            "expect_doc_subtype": "research_therapeutic",
            "expect_applicability": "not_applicable",
        },
    ),
    (
        Path("data/Input pdfs/articles/pdf/Value of Antibiotic Prophylaxis for Percutaneo.pdf"),
        {
            "expect_doc_subtype": None,
            "expect_applicability": "not_applicable",
        },
    ),
    (
        Path("data/Input pdfs/articles/pdf/Value-Based Proposition for a Dedicated IP suite.pdf"),
        {
            "expect_doc_subtype": "editorial_or_economics",
            "expect_applicability": "not_applicable",
        },
    ),
]


@pytest.mark.parametrize("pdf_path, expectations", NEGATIVE_CASES)
def test_negative_control_articles(pdf_path: Path, expectations: dict) -> None:
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

    document = outcome.document
    assert document is not None

    expected_subtype = expectations.get("expect_doc_subtype")
    if expected_subtype:
        assert document.doc_subtype == expected_subtype

    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    applicability = pipeline_info.get("ats_yield_applicability")
    reasons = pipeline_info.get("ats_yield_reasons", [])
    if expectations.get("expect_applicability"):
        assert applicability == expectations["expect_applicability"]
        assert reasons, "Applicability reasons should be recorded"

    metrics = outcome.metrics
    if expectations.get("expect_applicability"):
        assert metrics.get("ats_yield_applicability") == expectations["expect_applicability"]
