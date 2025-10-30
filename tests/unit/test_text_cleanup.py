from medparse.normalize.text_cleanup import restore_whitespace


def test_restore_whitespace_fixes_fused_words_and_headers() -> None:
    raw = "IonSystem,Instruments,andAccessoriesUserManualTheIonEndoluminalSystemProvidesNavigation"
    cleaned = restore_whitespace(raw)
    assert "Ion Endoluminal System Provides Navigation" in cleaned
    assert "IonSystem" not in cleaned
