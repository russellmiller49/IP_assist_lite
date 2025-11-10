from __future__ import annotations

from pathlib import Path

import pytest

from medparse.pipeline.run_extract import run_extract

IFU_CONFIG_PATH = Path("configs/run_ifu.yaml")
ALT_PRO_PDF = Path("data/Input pdfs/IFUs/pdf/ALT-Pro_Instruction Manual.pdf")


@pytest.mark.skipif(not ALT_PRO_PDF.exists(), reason="ALT-Pro IFU fixture not available")
def test_ifu_alt_pro_safety_density_threshold() -> None:
    outcome = run_extract(
        pdf_path=ALT_PRO_PDF,
        config_path=IFU_CONFIG_PATH,
        use_cache=False,
        second_pass_mode="always",
    )

    assert outcome.success, outcome.failure_reason or "extraction failed"
    document = outcome.document
    assert document is not None

    metrics = outcome.metrics
    expected_min = metrics.get("safety_expected_min")
    assert expected_min is not None
    assert len(document.safety_blocks) >= max(0, expected_min - 5)
    assert document.pipeline_info.get("safety_expected_min") == expected_min
    assert metrics.get("safety_status") == "ok"
    assert metrics.get("safety_found") == len(document.safety_blocks)
    assert document.pipeline_info.get("safety_threshold_rule") == "default"

    safety_added = document.pipeline_info.get("safety_blocks_added", 0)
    assert isinstance(safety_added, int) and safety_added >= 0

    errors = [issue.message for issue in outcome.validator_issues if issue.severity == "error"]
    assert not any("Safety content below expected density" in message for message in errors)

    second_pass_meta = document.pipeline_info.get("second_pass", {}).get("meta", {})
    assert "safety_blocks_added" in second_pass_meta
    summary = metrics.get("_metrics", {})
    assert summary.get("safety_threshold_rule") == "default"
    assert summary.get("safety_expected_min") == expected_min
    assert summary.get("safety_found") == len(document.safety_blocks)
    assert summary.get("safety_gap") == max(0, expected_min - summary.get("safety_found", 0))
