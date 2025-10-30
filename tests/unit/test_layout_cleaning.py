from medparse.ingest.cleaning import sanitize_sections


def test_sanitize_sections_drops_headers_and_normalises_spacing() -> None:
    lines = [
        "HEADER TITLE",
        " Section 1  Text ",
        "",
        "\tSecond line   continues",
        "HEADER TITLE",
        "Third    line",
    ]
    assert sanitize_sections(lines) == ["Section 1 Text", "", "Second line continues", "Third line"]


def test_sanitize_sections_collapses_duplicate_blank_lines() -> None:
    lines = ["First", "", "", "Second", "", ""]
    assert sanitize_sections(lines) == ["First", "", "Second"]
