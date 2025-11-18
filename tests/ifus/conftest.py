from __future__ import annotations

from pathlib import Path

import pytest

from medparse.pipeline.run_extract import run_extract

CONFIG_PATH = Path("configs/run_ifu.yaml")
BW18_PDF = Path("data/Input pdfs/IFUs/pdf/BW-18V_Instruction_Manual.pdf")


@pytest.fixture(scope="session")
def bw18_outcome():
    if not BW18_PDF.exists():
        pytest.skip("BW-18V IFU fixture not available")

    outcome = run_extract(
        pdf_path=BW18_PDF,
        config_path=CONFIG_PATH,
        use_cache=False,
        profile_override="enriched",
        chunking_mode="smart",
    )
    assert outcome.success, outcome.failure_reason or "BW-18V extraction failed"
    return outcome
