from __future__ import annotations

from pathlib import Path

import pytest

from medparse.pipeline.run_extract import run_extract

CONFIG_PATH = Path("configs/run_ifu.yaml")
ERBE_PDF = Path("data/Input pdfs/IFUs/pdf/30180-103_ERBE_EN_SystemCarrier_performance__D294849.pdf")


@pytest.mark.skipif(not ERBE_PDF.exists(), reason="ERBE IFU fixture not available")
def test_erbe_safety_density_uses_vendor_override() -> None:
    outcome = run_extract(
        pdf_path=ERBE_PDF,
        config_path=CONFIG_PATH,
        use_cache=False,
        force_deep=False,
        profile_override="enriched",
    )
    assert outcome.success, outcome.failure_reason or "extraction failed"

    metrics = outcome.metrics
    document = outcome.document
    assert document is not None

    expected_min = metrics.get("safety_expected_min")
    assert expected_min == 15
    assert len(document.safety_blocks or []) >= expected_min - 5

    hard_errors = [issue for issue in outcome.validator_issues if issue.severity == "error"]
    assert not any("Safety content below expected" in issue.message for issue in hard_errors)

    pipeline = document.pipeline_info
    assert pipeline.get("safety_expected_min") == 15
    assert pipeline.get("safety_expectation_source") == "density_config_override"
