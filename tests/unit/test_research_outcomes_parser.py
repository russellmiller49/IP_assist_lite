from __future__ import annotations

import pytest

from medparse.extractors import research_outcomes as ro
from medparse.schema.article import ArticleDocument


def test_grouped_count_pattern_extracts_counts_and_arm() -> None:
    text = (
        "Biopsy resulted in a specific diagnosis in 94 of 119 patients (79.0%) in the navigational bronchoscopy group "
        "and in 81 of 110 patients (73.6%) in the transthoracic needle biopsy group."
    )
    matches = list(ro.GROUPED_COUNT_PATTERN.finditer(text))
    assert len(matches) == 2

    first = matches[0]
    assert first.group("num") == "94"
    assert first.group("den") == "119"
    assert first.group("pct") == "79.0"
    assert ro._normalize_arm_name(first.group("arm")) == "navigational bronchoscopy"

    second = matches[1]
    assert second.group("num") == "81"
    assert second.group("den") == "110"
    assert second.group("pct") == "73.6"
    assert ro._normalize_arm_name(second.group("arm")) == "transthoracic needle biopsy"


def test_ci_pattern_matches_range() -> None:
    text = "absolute difference, 5.4 percentage points; 95% confidence interval, -6.5 to 17.2; P=0.003 for noninferiority."
    match = ro.CI_PATTERN.search(text)
    assert match is not None
    assert match.group("lower") == "-6.5"
    assert match.group("upper") == "17.2"


def test_p_value_pattern_detects_noninferiority_value() -> None:
    text = "Absolute difference, 5.4 percentage points; 95% confidence interval, -6.5 to 17.2; P = 0.003 for noninferiority; P = 0.17 for superiority."
    matches = list(ro.P_VALUE_PATTERN.finditer(text))
    assert [m.group("pval") for m in matches] == ["0.003", "0.17"]


@pytest.mark.parametrize(
    "paragraph, expected",
    [
        ("Diagnostic accuracy was similar between groups.", True),
        ("Pneumothorax occurred in 4 of 121 patients (3.3%) in the navigational bronchoscopy group.", True),
        ("Randomized patients completed follow-up questionnaires.", False),
    ],
)
def test_paragraph_relevant_detection(paragraph: str, expected: bool) -> None:
    assert ro._paragraph_relevant(paragraph.lower()) is expected


def test_research_outcomes_follow_up_reason() -> None:
    document = ArticleDocument(doc_type="article", source_file="veritas.pdf", page_count=1)
    document.doc_subtype = "research_diagnostic"
    paragraph_store = {
        "h1": {
            "text": "Biopsy resulted in a specific diagnosis in 10 of 20 patients (50.0%) in the navigational bronchoscopy group after 12-month follow-up.",
            "order": [1],
            "page": 1,
        },
        "h2": {
            "text": "Pneumothorax occurred in 2 of 20 patients (10.0%) in the navigational bronchoscopy group with nonspecific findings.",
            "order": [2],
            "page": 1,
        },
    }

    outcomes = ro.extract_research_outcomes(
        document=document,
        paragraph_store=paragraph_store,
        evidence_bank={},
        subtype="research_diagnostic",
    )

    assert outcomes is not None
    assert outcomes.arms, "Expected arm-level outcomes"
    arm = outcomes.arms[0]
    assert arm.diagnostic_accuracy is not None
    assert "follow_up_used_in_numerator" in arm.diagnostic_accuracy.reasons

    complications = arm.complications.get("pneumothorax_any")
    assert complications is not None
    assert "nonspecific_counts_included" in complications.reasons

    assert set(outcomes.reasons) == {
        "follow_up_used_in_numerator",
        "nonspecific_counts_included",
    }
    assert outcomes.evidence_ids
