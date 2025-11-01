from __future__ import annotations

from medparse.ingest.models import Heading, PageData
from medparse.ifu.anchors import TocGuardConfig, slice_section


def _page(number: int, lines: list[str]) -> PageData:
    text = "\n".join(lines)
    headings = []
    for idx, line in enumerate(lines):
        if line.lower().startswith("1.4.1 indications for use"):
            headings.append(Heading(page=number, line_index=idx, kind="section", title="1.4.1 Indications for Use"))
        if line.lower().startswith("1.4.2 intended use"):
            headings.append(Heading(page=number, line_index=idx, kind="section", title="1.4.2 Intended Use"))
    return PageData(number=number, text=text, lines=lines, headings=headings, tables=[])


def test_slice_section_respects_stop_headings() -> None:
    pages = [
        _page(
            10,
            [
                "1.4.1 Indications for Use",
                "Use this system to access the bronchial tree.",
                "Contraindications",
                "Do not use in patients with severe hypoxia.",
            ],
        )
    ]

    section = slice_section(
        pages,
        ["indications for use"],
        ["contraindications"],
        toc_guard=False,
        guard_config=TocGuardConfig(enabled=False),
    )

    assert "Contraindications" not in section.text
    assert "Use this system" in section.text


def test_slice_section_with_min_start_page() -> None:
    early_pages = [_page(2, ["1.4.1 Indications for Use", "Placeholder text"])]
    late_pages = [_page(12, ["1.4.1 Indications for Use", "Use as directed."])]

    section = slice_section(
        early_pages + late_pages,
        ["indications for use"],
        ["contraindications"],
        toc_guard=False,
        guard_config=TocGuardConfig(enabled=False),
        min_start_page=10,
    )

    assert "Placeholder" not in section.text
    assert "Use as directed." in section.text
