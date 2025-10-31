from __future__ import annotations

from pathlib import Path

import pytest

from medparse.pipeline.run_extract import run_extract

CONFIG_PATH = Path("configs/run_article.yaml")
CRYOBIOPSY_PDF = Path("data/Input pdfs/articles/pdf/Robotic Cyrobiopsy 2022.pdf")


def _run_extract(pdf_path: Path):
    outcome = run_extract(
        pdf_path=pdf_path,
        config_path=CONFIG_PATH,
        use_cache=False,
        force_deep=False,
        profile_override="enriched",
    )
    assert outcome.success, outcome.failure_reason or "extraction failed"
    assert outcome.document is not None
    return outcome


def test_cryobiopsy_percent_yield_recovers_denominator() -> None:
    if not CRYOBIOPSY_PDF.exists():
        pytest.skip("Cryobiopsy fixture PDF not available")

    outcome = _run_extract(CRYOBIOPSY_PDF)
    document = outcome.document
    assert document is not None

    diagnostic = document.diagnostic_yield
    assert diagnostic is not None
    assert diagnostic.denominator_hint
    assert "120" in diagnostic.denominator_hint
    assert not diagnostic.strict
    assert diagnostic.denominator is not None
    assert document.n_lesions == 120
