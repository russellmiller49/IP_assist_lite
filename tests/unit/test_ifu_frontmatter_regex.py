from __future__ import annotations

from medparse.ingest.models import PageData
from medparse.ifu.frontmatter import extract_front_matter


def test_front_matter_patterns_capture_identifiers() -> None:
    cover_lines = [
        "ERBE Elektromedizin GmbH",
        "SystemCarrier Performance",
        "REF D294849",
        "Rev B",
        "Published Date: 2022-04-15",
        "Model SC-200",
    ]
    pages = [PageData(number=1, text="\n".join(cover_lines), lines=cover_lines, headings=[], tables=[])]

    meta = extract_front_matter(pages)

    assert meta["manufacturer"] == "ERBE Elektromedizin GmbH"
    assert meta["part_number"] == "D294849"
    assert meta["revision"] == "B"
    assert meta["publication_date"] == "2022-04-15"
    assert meta["model"] == "SC-200"
    assert meta["product_name"] == "SystemCarrier Performance"


def test_front_matter_captures_dot_separated_date() -> None:
    cover_lines = [
        "Ion Endoluminal System",
        "PN 553990-11",
        "Rev. C",
        "Publication Date: 2024.08",
    ]
    pages = [PageData(number=1, text="\n".join(cover_lines), lines=cover_lines, headings=[], tables=[])]

    meta = extract_front_matter(pages)

    assert meta["part_number"] == "553990-11"
    assert meta["revision"] == "C"
    assert meta["publication_date"] == "2024-08"


def test_alt_pro_model_detected_without_model_prefix() -> None:
    cover_lines = [
        "Olympus Medical Systems Corp.",
        "ALT PRO Bronchoscope",
        "Order No. 123-456",
        "Rev: B",
    ]
    pages = [PageData(number=1, text="\n".join(cover_lines), lines=cover_lines, headings=[], tables=[])]

    meta = extract_front_matter(pages)

    assert meta["model"] == "ALT PRO"
    assert meta["revision"] == "B"
