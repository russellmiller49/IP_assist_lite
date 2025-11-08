from __future__ import annotations

from medparse.ifu.safety_thresholds import expected_safety_min


def test_expected_min_for_short_leaflet() -> None:
    assert expected_safety_min(char_count=1500, page_count=3, manufacturer=None) == 8


def test_expected_min_for_erbe_override() -> None:
    value = expected_safety_min(char_count=40_000, page_count=20, manufacturer="ERBE Med")
    assert value == 15


def test_expected_min_caps_at_long_form() -> None:
    value = expected_safety_min(char_count=220_000, page_count=120, manufacturer="Generic Vendor")
    assert value == 20
