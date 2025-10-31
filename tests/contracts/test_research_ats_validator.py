from __future__ import annotations

from pathlib import Path

import pytest

from medparse.pipeline.run_extract import run_extract

CONFIG_PATH = Path("configs/run_article.yaml")
CRYOBIOPSY_PDF = Path("data/Input pdfs/articles/pdf/Robotic Cyrobiopsy 2022.pdf")


def test_research_article_flags_non_strict_yield() -> None:
    if not CRYOBIOPSY_PDF.exists():
        pytest.skip("Robotic cryobiopsy fixture not available")

    outcome = run_extract(
        pdf_path=CRYOBIOPSY_PDF,
        config_path=CONFIG_PATH,
        use_cache=False,
        force_deep=False,
        profile_override="enriched",
    )
    assert outcome.success, outcome.failure_reason or "extraction failed"

    metrics = outcome.metrics
    ats_metrics = metrics.get("ats")
    assert ats_metrics is not None
    assert ats_metrics.get("compatible") is False
    reasons = ats_metrics.get("exclusion_reasons") or []
    assert any("follow_up_used_in_numerator" in reason for reason in reasons)
