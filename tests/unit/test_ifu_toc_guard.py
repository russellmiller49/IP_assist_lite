from __future__ import annotations

from medparse.ingest.models import PageData
from medparse.extractors.ifu import _clamp_pages
from medparse.ifu.toc_guard import TocGuardConfig, apply_toc_guard, trim_anchor_bleed
from medparse.schema.ifu import IFUDocument
from medparse.second_pass.patchers.ifu_toc_guard_refine import apply_ifu_toc_guard_refine
from medparse.second_pass.types import SecondPassContext


def _make_page(number: int, lines: list[str]) -> PageData:
    text = "\n".join(lines)
    return PageData(number=number, text=text, lines=lines, headings=[], tables=[])


def _make_second_pass_ctx() -> SecondPassContext:
    return SecondPassContext(
        validation_issues=[],
        paragraph_store={},
        evidence_bank={},
        profile="enriched",
        engines_tried=[],
        emit_policies={},
        config={},
        mode="auto",
        doc_metrics={},
    )


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


def test_clamp_pages_bounds_results_to_document_range() -> None:
    clamped = _clamp_pages([0, 1, 5, 9, "10", None], page_count=6)
    assert clamped == [1, 5, 6]


def test_toc_guard_refine_records_reasons_once() -> None:
    document = IFUDocument(
        doc_type="ifu",
        source_file="dummy.pdf",
        page_count=5,
        manufacturer="Acme",
        product_name="Test Device",
        indications_for_use={"text": "Use per instructions."},
        contraindications=[],
    )
    document.pipeline_info = {"toc_guard_pages_dropped": [1, 2, 2]}

    ctx = _make_second_pass_ctx()
    result = apply_ifu_toc_guard_refine(document, ctx)

    assert result.applied
    assert result.reasons == ["toc_guard_refine:severity=info"]
    assert result.modifications == {"toc_guard_pages_dropped": 2}
    bucket = document.pipeline_info.get("second_pass", {})
    assert bucket.get("reasons") == ["toc_guard_refine:severity=info"]
    assert document.pipeline_info.get("toc_guard_pages_dropped") == [1, 2]
    assert document.pipeline_info.get("toc_guard_pages_dropped_count") == 2
    toc_meta = document.pipeline_info.get("toc_guard", {})
    assert isinstance(toc_meta, dict)
    assert toc_meta.get("pages_dropped") == [1, 2]
