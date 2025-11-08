from __future__ import annotations

from pathlib import Path

import pytest

from medparse.pipeline.run_extract import run_extract

CONFIG_PATH = Path("configs/run_article.yaml")
VERITAS_PDF = Path("data/Input pdfs/articles/pdf/VERITAS.pdf")


@pytest.mark.skipif(not VERITAS_PDF.exists(), reason="VERITAS fixture not available")
def test_research_veritas_outcomes() -> None:
    outcome = run_extract(
        pdf_path=VERITAS_PDF,
        config_path=CONFIG_PATH,
        use_cache=False,
        force_deep=False,
        profile_override="enriched",
    )

    assert outcome.success, outcome.failure_reason or "extraction failed"
    document = outcome.document
    assert document is not None
    assert document.doc_subtype == "research_diagnostic"
    assert document.research_scope == "diagnostic_ppn_bronchoscopy"

    research = getattr(document, "research_outcomes", None)
    assert research is not None, "Research outcomes missing for VERITAS trial"
    assert research.primary_outcome == "diagnostic_accuracy"
    assert research.design == "randomized_noninferiority"

    arms = {arm.name: arm for arm in research.arms}
    assert "navigational bronchoscopy" in arms
    assert "transthoracic needle biopsy" in arms

    nav = arms["navigational bronchoscopy"]
    tt_nb = arms["transthoracic needle biopsy"]

    assert nav.diagnostic_accuracy is not None
    assert nav.diagnostic_accuracy.percent == pytest.approx(79.0, rel=1e-3)
    assert nav.diagnostic_accuracy.n_over_N is not None
    assert nav.diagnostic_accuracy.n_over_N.numerator == 94
    assert nav.diagnostic_accuracy.n_over_N.denominator == 119
    assert nav.diagnostic_accuracy.ci_95 == pytest.approx((-6.5, 17.2))
    assert nav.diagnostic_accuracy.p_value == pytest.approx(0.003, rel=1e-3)

    assert tt_nb.diagnostic_accuracy is not None
    assert tt_nb.diagnostic_accuracy.percent == pytest.approx(73.6, rel=1e-3)
    assert tt_nb.diagnostic_accuracy.n_over_N is not None
    assert tt_nb.diagnostic_accuracy.n_over_N.numerator == 81
    assert tt_nb.diagnostic_accuracy.n_over_N.denominator == 110

    nav_any = nav.complications.get("pneumothorax_any")
    tt_nb_any = tt_nb.complications.get("pneumothorax_any")
    assert nav_any is not None and nav_any.percent == pytest.approx(3.3, rel=1e-3)
    assert tt_nb_any is not None and tt_nb_any.percent == pytest.approx(28.3, rel=1e-3)

    nav_severe = nav.complications.get("pneumothorax_severe")
    tt_nb_severe = tt_nb.complications.get("pneumothorax_severe")
    assert nav_severe is not None and nav_severe.percent == pytest.approx(0.8, rel=1e-3)
    assert tt_nb_severe is not None and tt_nb_severe.percent == pytest.approx(11.5, rel=1e-3)

    paragraph_store = getattr(document, "paragraph_store", {}) or {}
    assert paragraph_store, "Paragraph store should be populated"

    def _assert_evidence(metric) -> None:
        evidence_ids = getattr(metric, "evidence_ids", []) or []
        assert evidence_ids, f"No evidence ids recorded for {metric}"
        for evidence_id in evidence_ids:
            assert evidence_id in paragraph_store, f"Missing paragraph hash {evidence_id}"

    _assert_evidence(nav.diagnostic_accuracy)
    _assert_evidence(tt_nb.diagnostic_accuracy)
    _assert_evidence(nav_any)
    _assert_evidence(tt_nb_any)
    _assert_evidence(nav_severe)
    _assert_evidence(tt_nb_severe)
