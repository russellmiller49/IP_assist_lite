from __future__ import annotations

from pathlib import Path

import pytest

from medparse.pipeline.run_extract import run_extract

CONFIG_PATH = Path("configs/run_ifu.yaml")
ION_PDF = Path("data/Input pdfs/IFUs/pdf/Ion Endoluminal System, Instruments, and Accessories User Manual(553990-11).pdf")


@pytest.fixture(scope="module")
def ion_outcome():
    if not ION_PDF.exists():
        pytest.skip("Ion IFU fixture not available")
    outcome = run_extract(
        pdf_path=ION_PDF,
        config_path=CONFIG_PATH,
        use_cache=False,
        force_deep=False,
        profile_override="enriched",
        second_pass_mode="auto",
    )
    assert outcome.success, outcome.failure_reason or "extraction failed"
    return outcome


def test_ion_indications_numbered_anchor(ion_outcome) -> None:
    document = ion_outcome.document
    assert document is not None

    indications = document.indications_for_use
    assert isinstance(indications, dict)
    assert indications.get("text")
    assert indications.get("provenance") == "second_pass:indications_numbered" or indications.get("provenance") == "second_pass:intended_to_indications"

    if isinstance(indications.get("evidence_ids"), list):
        assert indications["evidence_ids"], "Expected evidence ids for numbered heading extraction"

    pipeline_info = document.pipeline_info
    sections_map = pipeline_info.get("sections")
    assert isinstance(sections_map, dict)
    references_section = sections_map.get("references")
    assert isinstance(references_section, dict)
    assert references_section.get("page_span")
    assert references_section.get("source") == "second_pass:references_anchor_backfill"

    assert pipeline_info.get("toc_guard_severity") == "info"
    errors = [issue.message for issue in ion_outcome.validator_issues if issue.severity == "error"]
    assert not errors
