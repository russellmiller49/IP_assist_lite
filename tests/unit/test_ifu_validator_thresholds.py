from __future__ import annotations

from types import SimpleNamespace

from medparse.ifu.safety_thresholds import expected_safety_min


def _make_doc(**overrides):
    base = {
        "doc_type": "ifu",
        "source_file": "test.pdf",
        "page_count": overrides.get("page_count", 10),
        "manufacturer": overrides.get("manufacturer"),
        "product_name": overrides.get("product_name"),
        "doc_subtype": overrides.get("doc_subtype"),
    }
    return SimpleNamespace(**base)


def test_expected_min_for_short_leaflet() -> None:
    doc = _make_doc(page_count=3)
    assert expected_safety_min(doc) == 8


def test_expected_min_for_erbe_override() -> None:
    doc = _make_doc(page_count=20, manufacturer="ERBE Elektromedizin GmbH", product_name="Units and modules")
    assert expected_safety_min(doc) == 15


def test_expected_min_defaults_to_long_form() -> None:
    doc = _make_doc(page_count=120, manufacturer="Generic Vendor")
    assert expected_safety_min(doc) == 20
