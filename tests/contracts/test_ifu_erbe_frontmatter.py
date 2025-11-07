from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from medparse.pipeline.run_extract import run_extract

CONFIG_PATH = Path("configs/run_ifu.yaml")
ERBE_PDF = Path("data/Input pdfs/IFUs/pdf/30180-103_ERBE_EN_SystemCarrier_performance__D294849.pdf")
SECOND_PASS_PATH = Path("configs/_shared/second_pass.yaml")


@pytest.mark.skipif(not ERBE_PDF.exists(), reason="ERBE IFU fixture not available")
def test_erbe_front_matter_and_safety_blocks() -> None:
    outcome = run_extract(
        pdf_path=ERBE_PDF,
        config_path=CONFIG_PATH,
        use_cache=False,
        force_deep=False,
        profile_override="enriched",
    )
    assert outcome.success, outcome.failure_reason or "extraction failed"

    document = outcome.document
    assert document is not None

    assert document.manufacturer == "ERBE Elektromedizin GmbH"
    assert document.product_name is not None and document.product_name.strip()
    normalized_name = document.product_name.replace(" ", "").replace("-", "").lower()
    assert "systemcarrier" in normalized_name
    assert document.part_number is not None

    safety_blocks = document.safety_blocks or []
    assert safety_blocks, "Expected safety blocks to be captured"
    for block in safety_blocks:
        assert block.level in {"danger", "warning", "caution", "notice", "note", "attention"}
        assert block.hash and len(block.hash) >= 6

    metrics = outcome.metrics
    safety_config = yaml.safe_load(SECOND_PASS_PATH.read_text(encoding="utf-8")) or {}
    shared_block = safety_config.get("second_pass", safety_config)
    safety_min_cfg = (shared_block.get("ifu", {}).get("safety_density_min", {}) if isinstance(shared_block, dict) else {})
    erbe_expected = safety_min_cfg.get("by_manufacturer", {}).get("ERBE", 15)
    assert metrics.get("safety_expected_min") == erbe_expected
    pipeline = document.pipeline_info
    assert pipeline.get("safety_expected_min") == erbe_expected
    assert pipeline.get("safety_expectation_source") in {"vendor_override", "density_config_override"}
