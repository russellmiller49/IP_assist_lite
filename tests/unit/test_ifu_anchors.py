from medparse.ifu.anchors import TocGuardConfig, normalize_bullets, slice_section, strip_toc
from medparse.ingest.models import PageData


def _page(number: int, lines: list[str]) -> PageData:
    return PageData(number=number, text="\n".join(lines), lines=list(lines))


def test_strip_toc_removes_dense_dotted_page():
    toc_lines = [
        "Contents",
        "1. Introduction ............ 5",
        "2. Safety Information ............ 9",
        "3. Indications ............ 12",
        "4. Technical Data ............ 18",
    ]
    content_lines = ["Indications", "This device is intended for ...", "Warnings", "Do not reuse."]

    guard = TocGuardConfig()
    filtered, dropped = strip_toc([_page(1, toc_lines), _page(2, content_lines)], guard)

    assert dropped == [1]
    assert len(filtered) == 1
    assert filtered[0].number == 2


def test_slice_section_extracts_between_anchors():
    pages = [
        _page(1, ["Indications", "This device is intended for adult patients.", "Warnings", "Single use only."])
    ]
    section = slice_section(pages, ["indications"], ["warnings"], toc_guard=False)
    assert "adult patients" in section.text.lower()


def test_normalize_bullets_formats_leading_symbols():
    text = "\n".join(["• First", "- Second", "Third"])
    result = normalize_bullets(text)
    assert result.splitlines() == ["- First", "- Second", "Third"]
