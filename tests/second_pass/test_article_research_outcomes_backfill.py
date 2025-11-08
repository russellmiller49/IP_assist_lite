from __future__ import annotations

from pathlib import Path

from medparse.pipeline.run_extract import run_extract
from medparse.second_pass.patchers.article_research_outcomes_backfill import (
    apply_article_research_outcomes_backfill,
)
from medparse.second_pass.types import SecondPassContext

CONFIG_PATH = Path("configs/run_article.yaml")
VERITAS_PDF = Path("data/Input pdfs/articles/pdf/VERITAS.pdf")


def test_article_research_outcomes_backfill() -> None:
    if not VERITAS_PDF.exists():
        raise RuntimeError("VERITAS fixture missing")

    outcome = run_extract(
        pdf_path=VERITAS_PDF,
        config_path=CONFIG_PATH,
        use_cache=False,
        force_deep=False,
        profile_override="enriched",
    )

    document = outcome.document
    assert document is not None
    document.research_outcomes = None

    ctx = SecondPassContext(
        validation_issues=list(outcome.validator_issues),
        paragraph_store=getattr(document, "paragraph_store", {}) or {},
        evidence_bank=getattr(document, "evidence_bank", {}) or {},
        profile="enriched",
        engines_tried=[outcome.engine],
        emit_policies={},
        config={},
        mode="auto",
        doc_metrics=outcome.metrics,
    )

    result = apply_article_research_outcomes_backfill(document, ctx)
    assert result.applied
    research_outcomes = document.research_outcomes
    assert research_outcomes is not None
    assert research_outcomes.diagnostic_accuracy is not None
    arms = {arm.name: arm for arm in research_outcomes.arms}
    assert "navigational bronchoscopy" in arms
    assert arms["navigational bronchoscopy"].diagnostic_accuracy is not None
    assert arms["navigational bronchoscopy"].diagnostic_accuracy.percent is not None
