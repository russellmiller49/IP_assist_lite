from __future__ import annotations

from pathlib import Path

import pytest

from medparse.pipeline.run_extract import run_extract

CONFIG_PATH = Path("configs/run_ifu.yaml")
BW18V_PDF = Path("data/Input pdfs/IFUs/pdf/BW-18V_Instruction_Manual.pdf")


@pytest.fixture(scope="module")
def bw18v_outcome():
    if not BW18V_PDF.exists():
        pytest.skip("BW-18V IFU fixture not available")
    outcome = run_extract(
        pdf_path=BW18V_PDF,
        config_path=CONFIG_PATH,
        use_cache=False,
        force_deep=False,
        profile_override="enriched",
        second_pass_mode="auto",
    )
    assert outcome.success, outcome.failure_reason or "extraction failed"
    return outcome


def test_bw18v_uses_leaflet_threshold(bw18v_outcome) -> None:
    document = bw18v_outcome.document
    assert document is not None
    pipeline = document.pipeline_info

    assert pipeline.get("safety_expected_min") == 8
    assert pipeline.get("safety_expected") == 8
    assert pipeline.get("safety_threshold_rule") == "small_leaflet"
    assert pipeline.get("safety_status") == "ok"

    product_name = document.product_name or ""
    assert product_name.startswith("Olympus BW-18V Channel Cleaning Brush")

    revision = document.revision
    assert pipeline.get("front_matter_revision_sanitized") or not revision

    messages = [issue.message for issue in bw18v_outcome.validator_issues]
    assert not any(">=20" in message for message in messages)
    assert not any(issue.severity == "error" for issue in bw18v_outcome.validator_issues)
