from __future__ import annotations

from pathlib import Path

import pytest

from medparse.pipeline.run_extract import run_extract

CONFIG_PATH = Path("configs/run_ifu.yaml")
ALT_PRO_PDF = Path("data/Input pdfs/IFUs/pdf/ALT-Pro_Instruction Manual.pdf")


@pytest.mark.skipif(not ALT_PRO_PDF.exists(), reason="ALT-Pro IFU fixture not available")
def test_alt_pro_front_matter_backfill() -> None:
    outcome = run_extract(
        pdf_path=ALT_PRO_PDF,
        config_path=CONFIG_PATH,
        use_cache=False,
        force_deep=False,
        profile_override="enriched",
    )
    assert outcome.success, outcome.failure_reason or "extraction failed"

    document = outcome.document
    assert document is not None

    assert document.manufacturer and "olympus" in document.manufacturer.lower()
    assert document.model == "ALT PRO"
    assert document.part_number is not None and document.part_number.strip()
    assert document.publication_date is not None and document.publication_date.startswith("20")

    second_pass_info = getattr(document, "pipeline_info", {}).get("second_pass", {})
    assert isinstance(second_pass_info, dict)
    applied = second_pass_info.get("applied") or second_pass_info.get("patches_applied") or []
    reasons = second_pass_info.get("reasons") or []
    if "ifu_frontmatter_backfill" in applied or "frontmatter_backfill" in reasons:
        modifications = second_pass_info.get("modifications", {})
        assert isinstance(modifications, dict)
        assert modifications.get("front_matter_model", 0) >= 1
        assert modifications.get("front_matter_publication_date", 0) >= 1
    else:
        assert "no_fields_detected" in reasons or "frontmatter_complete" in reasons

    errors = [issue for issue in (outcome.validator_issues or []) if issue.severity == "error"]
    assert not errors, "ALT-Pro validation should not emit hard errors"
