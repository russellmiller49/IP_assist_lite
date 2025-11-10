from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from medparse.config import get_extraction_config
from medparse.pipeline.run_extract import run_extract
from medparse.validate.ifu_rules import validate_ifu

CONFIG_PATH = Path("configs/run_ifu.yaml")
BW18V_PDF = Path("data/Input pdfs/IFUs/pdf/BW-18V_Instruction_Manual.pdf")


@pytest.mark.skipif(not BW18V_PDF.exists(), reason="BW-18V IFU fixture not available")
def test_small_leaflet_indications_fallback() -> None:
    outcome = run_extract(
        pdf_path=BW18V_PDF,
        config_path=CONFIG_PATH,
        use_cache=False,
        force_deep=False,
        profile_override="enriched",
    )
    assert outcome.success, outcome.failure_reason or "extraction failed"

    document = outcome.document
    assert document is not None

    indications = document.indications_for_use
    assert isinstance(indications, dict)
    assert indications.get("derived_from") == "intended_use"
    assert indications.get("text")
    localized = document.pipeline_info.get("localized", {})
    if isinstance(localized, dict) and localized.get("indications"):
        assert localized.get("indications", {}).get("ja")

    pipeline = document.pipeline_info
    assert pipeline.get("indications_fallback_provenance") == "second_pass_small_leaflet"
    assert pipeline.get("safety_expected_min") == 8
    assert pipeline.get("safety_threshold_rule") == "small_leaflet"
    assert pipeline.get("revision_status") == "sanitized_unusable"
    front_meta = pipeline.get("front_matter_meta", {})
    assert isinstance(front_meta, dict)
    assert front_meta.get("revision_provenance") == "sanitized"
    assert len(document.safety_blocks or []) >= pipeline.get("safety_expected_min")
    assert pipeline.get("safety_blocks_added", 0) >= 0
    assert document.model == "Channel Cleaning Brush"
    assert document.product_name.startswith("Olympus")
    if document.revision:
        assert "ACUUM" not in document.revision

    # Safety density should not raise hard errors for small leaflets
    extraction_config = get_extraction_config()
    config_payload = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    extraction_config.ifu = config_payload.get("ifu", {}) or {}
    issues = validate_ifu(document, extraction_config)
    assert not any(issue.severity == "error" for issue in issues)
    safety_warnings = [issue.message for issue in issues if "Expected ≥" in issue.message]
    assert len(safety_warnings) <= 1
    if safety_warnings:
        assert "≥8" in safety_warnings[0]
    assert not any("≥20" in issue.message for issue in issues)
    info_messages = [issue.message for issue in issues if issue.severity == "info"]
    assert any("Revision sanitized" in message for message in info_messages)
