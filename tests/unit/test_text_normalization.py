from medparse.ingest.cleaning import normalize_text_artifacts


def test_normalize_text_artifacts_replaces_ligatures() -> None:
    raw = "classi/uniFB01 ed re/uniFB02 ow \ufb01 \ufb02"
    normalised = normalize_text_artifacts(raw)
    assert "classified" in normalised
    assert "reflow" in normalised
    assert "/uniFB01" not in normalised
    assert "\ufb01" not in normalised


def test_normalize_text_artifacts_tidy_whitespace() -> None:
    raw = "fi stula  example \n next line"
    normalised = normalize_text_artifacts(raw)
    assert "fistula example" in normalised
    assert " \n" not in normalised
