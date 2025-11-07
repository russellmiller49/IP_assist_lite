from __future__ import annotations

from typing import List

from medparse.config import ExtractionConfig, ExtractionProfile
from medparse.schema.common import EvidenceSpan
from medparse.schema.ifu import IFUDocument, SafetyBlock
from medparse.validate.ifu_rules import validate_ifu


def _make_config() -> ExtractionConfig:
    return ExtractionConfig(
        profile=ExtractionProfile.ENRICHED,
        use_cache=False,
        thresholds={},
        metadata_sources={},
        enrichment={},
        ifu={},
    )


def _base_ifu(**overrides: object) -> IFUDocument:
    base = {
        "doc_type": "ifu",
        "source_file": "dummy.pdf",
        "page_count": 12,
        "manufacturer": "Acme Medical",
        "product_name": "Acme Device",
        "part_number": "PN-123",
        "revision": "R1",
        "publication_date": "2020-01",
        "model": "Model-X",
        "indications_for_use": "Device is indicated for airway procedures.",
        "intended_use": "Use according to instructions.",
        "intended_user": "Clinicians",
        "intended_patient_population": "Adults",
        "safety_blocks": [
            SafetyBlock(
                level="warning",
                text="WARNING: Use with caution.",
                evidence=EvidenceSpan(text="WARNING: Use with caution.", page=1),
            )
        ],
    }
    base.update(overrides)
    document = IFUDocument(**base)
    document.pipeline_info = {}
    return document


def _get_issue(issues: List[object], keyword: str):
    for issue in issues:
        if keyword in issue.message:
            return issue
    return None


def test_missing_front_matter_critical_is_error() -> None:
    config = _make_config()
    document = _base_ifu(manufacturer=None)

    issues = validate_ifu(document, config)
    issue = _get_issue(issues, "manufacturer")
    assert issue is not None
    assert issue.severity == "error"


def test_missing_front_matter_noncritical_warning() -> None:
    config = _make_config()
    document = _base_ifu(publication_date=None)

    issues = validate_ifu(document, config)
    issue = _get_issue(issues, "publication_date")
    assert issue is not None
    assert issue.severity == "warning"


def test_toc_bleed_severity_non_intuitive_warning() -> None:
    config = _make_config()
    document = _base_ifu()
    document.pipeline_info = {
        "anchor_bleed_errors": ["TOC bleed detected"],
        "anchor_bleed_fields": ["indications_for_use"],
        "anchor_spans": {"indications_for_use": {"start_page": 5, "end_page": 6}},
        "toc_guard_pages_dropped": [],
    }

    issues = validate_ifu(document, config)
    issue = _get_issue(issues, "Clinical anchor bleed")
    assert issue is not None
    assert issue.severity == "warning"


def test_toc_bleed_severity_intuitive_error() -> None:
    config = _make_config()
    document = _base_ifu(manufacturer="Intuitive Surgical, Inc.")
    document.pipeline_info = {
        "anchor_bleed_errors": ["TOC bleed detected"],
        "anchor_bleed_fields": ["indications_for_use"],
        "anchor_spans": {"indications_for_use": {"start_page": 7, "end_page": 8}},
        "toc_guard_pages_dropped": [],
    }

    issues = validate_ifu(document, config)
    issue = _get_issue(issues, "Clinical anchor bleed")
    assert issue is not None
    assert issue.severity == "error"


def test_safety_shortfall_intuitive_error() -> None:
    config = _make_config()
    document = _base_ifu(manufacturer="Intuitive Surgical, Inc.", page_count=40, safety_blocks=[])

    issues = validate_ifu(document, config)
    issue = _get_issue(issues, "Safety content below expected density")
    assert issue is not None
    assert issue.severity == "error"


def test_safety_shortfall_non_intuitive_warning() -> None:
    config = _make_config()
    document = _base_ifu(manufacturer="ERBE Elektromedizin GmbH", page_count=25, safety_blocks=[])

    issues = validate_ifu(document, config)
    issue = _get_issue(issues, "Safety content below expected density")
    assert issue is not None
    assert issue.severity == "warning"
