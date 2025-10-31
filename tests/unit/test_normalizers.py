from medparse.normalize.references import normalize_references
from medparse.normalize.safety import detect_severity
from medparse.utils.slug import slugify


def test_ifu_references_require_anchor_and_allowlist() -> None:
    lines = [
        "1. Smith J. Clinical use.",
        "2. Doe A. Another line.",
        "3. Example." ,
    ]
    assert normalize_references(lines, mode="ifu", headings=[]) == []

    headings = ["References"]
    assert normalize_references(lines, mode="ifu", headings=headings) == []

    allowlisted = [
        "1. Smith J. Clinical use. Journal 2024; doi:10.1000/xyz",
        "2. Doe A. Another line. Chest Medicine 2023; PMID 12345",
        "3. Example Study. Lung 2022;10(1):5-10",
    ]
    refs = normalize_references(allowlisted, mode="ifu", headings=headings)
    assert len(refs) == 3
    assert all("text" in ref for ref in refs)
    assert any(ref.get("doi") for ref in refs)


def test_safety_severity_supports_symbols() -> None:
    assert detect_severity("⚠ Risk of shock") == "warning"
    assert detect_severity("CAUTION: handle with care") == "caution"
    assert detect_severity("Note: additional steps") == "note"


def test_slugifier_corrects_common_typos() -> None:
    assert slugify("Robotic Cyrobiopsy 2022") == "robotic-cryobiopsy-2022"
