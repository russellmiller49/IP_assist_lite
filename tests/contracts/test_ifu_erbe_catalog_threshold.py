from __future__ import annotations

from pathlib import Path

import pytest

from medparse.pipeline.run_extract import run_extract

CONFIG_PATH = Path("configs/run_ifu.yaml")
ERBE_PDF = Path("data/Input pdfs/IFUs/pdf/85100-172_ERBE_EN_Units_and_modules__D080643.pdf")


@pytest.fixture(scope="module")
def erbe_outcome():
    if not ERBE_PDF.exists():
        pytest.skip("ERBE catalog IFU fixture not available")
    outcome = run_extract(
        pdf_path=ERBE_PDF,
        config_path=CONFIG_PATH,
        use_cache=False,
        force_deep=False,
        profile_override="enriched",
        second_pass_mode="auto",
    )
    assert outcome.success, outcome.failure_reason or "extraction failed"
    return outcome


def test_erbe_catalog_dynamic_threshold(erbe_outcome) -> None:
    document = erbe_outcome.document
    assert document is not None
    pipeline = document.pipeline_info

    assert pipeline.get("safety_expected_min") == 15
    assert pipeline.get("safety_expected") == 15
    assert pipeline.get("safety_expectation_source", "").startswith("manufacturer")

    for issue in erbe_outcome.validator_issues:
        if "Expected ≥" in issue.message:
            assert issue.severity == "warning"

    assert not any(issue.severity == "error" for issue in erbe_outcome.validator_issues)
