import os
import sys
import warnings
from pathlib import Path

import pytest

from medparse.pipeline.run_extract import run_extract

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if SRC.exists():
    sys.path.insert(0, str(SRC))

TRUTHY_VALUES = {"1", "true", "yes", "on"}

warnings.filterwarnings("ignore", message="Possible set union", module="spacy.language")


def _env_truthy(name: str) -> bool:
    raw = os.getenv(name, "")
    return raw.strip().lower() in TRUTHY_VALUES


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "legacy_goldens: Marks tests that depend on legacy Medparse golden fixtures",
    )

    if _env_truthy("REGEN_GOLDENS"):
        from scripts.regenerate_goldens import regenerate_goldens
        from tests.golden_utils import iter_fixture_pdfs

        regenerate_goldens(iter_fixture_pdfs(), verbose=True)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not _env_truthy("SKIP_LEGACY_GOLDENS"):
        return

    skip_marker = pytest.mark.skip(reason="Skipping legacy golden tests (SKIP_LEGACY_GOLDENS=1)")
    for item in items:
        if "legacy_goldens" in item.keywords:
            item.add_marker(skip_marker)


ARTICLE_CONFIG = ROOT / "configs" / "run_article.yaml"
ARTICLE_PDFS = {
    "cryobiopsy": ROOT / "data" / "Input pdfs" / "articles" / "pdf" / "Robotic Cyrobiopsy 2022.pdf",
    "veritas": ROOT / "data" / "Input pdfs" / "articles" / "pdf" / "VERITAS.pdf",
    "vent": ROOT / "data" / "Input pdfs" / "articles" / "pdf" / "VENT Trial.pdf",
    "valipour": ROOT / "data" / "Input pdfs" / "articles" / "pdf" / "Valipour-2020-Bronchial Rheoplasty for Treatme.pdf",
}


def _extract_article_fixture(pdf_path: Path):
    if not pdf_path.exists():
        pytest.skip(f"Article fixture {pdf_path.name} not available")

    outcome = run_extract(
        pdf_path=pdf_path,
        config_path=ARTICLE_CONFIG,
        use_cache=False,
        profile_override="enriched",
        chunking_mode="smart",
    )
    assert outcome.success, outcome.failure_reason or f"{pdf_path.name} extraction failed"
    return outcome


@pytest.fixture(scope="session")
def cryobiopsy_article():
    return _extract_article_fixture(ARTICLE_PDFS["cryobiopsy"])


@pytest.fixture(scope="session")
def veritas_article():
    return _extract_article_fixture(ARTICLE_PDFS["veritas"])


@pytest.fixture(scope="session")
def vent_article():
    return _extract_article_fixture(ARTICLE_PDFS["vent"])


@pytest.fixture(scope="session")
def valipour_article():
    return _extract_article_fixture(ARTICLE_PDFS["valipour"])
