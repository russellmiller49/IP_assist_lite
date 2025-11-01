from __future__ import annotations

from medparse.ingest.models import PageData
from medparse.ifu.toc_guard import TocGuardConfig, apply_toc_guard, trim_anchor_bleed


def _make_page(number: int, lines: list[str]) -> PageData:
    text = "\n".join(lines)
    return PageData(number=number, text=text, lines=lines, headings=[], tables=[])


def test_apply_toc_guard_drops_leading_toc_pages() -> None:
    pages = [
        _make_page(1, ["Table of Contents", "1. Introduction .... 3", "2. Setup .... 5"]),
        _make_page(2, ["Index", "A. Appendix ... 10", "B. References ... 12"]),
        _make_page(3, ["1 Introduction", "Real content starts here"]),
    ]
    config = TocGuardConfig(enabled=True)

    filtered, report = apply_toc_guard(pages, config)

    assert [page.number for page in filtered] == [3]
    assert report.pages_dropped == [1, 2]
    assert len(report.pages_dropped) == 2


def test_trim_anchor_bleed_removes_toc_lines() -> None:
    text = "Indications .......... 10\nWarnings ............ 12\n\nActual prose begins here."
    trimmed, removed = trim_anchor_bleed(text, max_blocks=2, ratio_threshold=0.7)

    assert "Actual prose" in trimmed
    assert "Warnings" not in trimmed
    assert removed > 0
