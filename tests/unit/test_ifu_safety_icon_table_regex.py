from medparse.ifu.safety_blocks import _detect_header


def test_detect_header_with_icon_prefix() -> None:
    lines = ["⚠ WARNING", "Do not reuse"]
    header = _detect_header(lines, 0, set())
    assert header is not None
    assert header.level == "warning"
    assert header.source == "icon"
    assert header.lines_consumed == 2


def test_detect_header_with_table_colon() -> None:
    lines = ["WARNING: Do not bend catheter"]
    header = _detect_header(lines, 0, set())
    assert header is not None
    assert header.level == "warning"
    assert header.source == "table"
    assert header.inline_text.lower().startswith("do not bend")
