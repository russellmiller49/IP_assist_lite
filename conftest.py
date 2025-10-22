import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if SRC.exists():
    sys.path.insert(0, str(SRC))

TRUTHY_VALUES = {"1", "true", "yes", "on"}


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
