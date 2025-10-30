import json
from pathlib import Path


ARTIFACT = Path("tests/data/ifu_ion-out.json")


def _load() -> dict:
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def test_meta_fields() -> None:
    data = _load()
    assert data["part_number"] == "553990-11"
    assert data["revision"] == "Rev C"
    assert data["manufacturer"] == "Intuitive Surgical, Inc."
    assert data["product_name"] == "Ion Endoluminal System"


def test_indications_and_user() -> None:
    data = _load()
    assert "ion endoluminal system" in data["indications_for_use"].lower()
    assert "rx only" in data["intended_user"].lower()
    assert not data["references"]


def test_tables_curated() -> None:
    data = _load()
    titles = [t.get("title", "").lower() for t in data["tables"]]
    assert any("table 4.2 led status" in title for title in titles)
    assert any("table 7.1 power modes" in title for title in titles)
    assert all(t.get("title") or t.get("rows") for t in data["tables"])


def test_software_versions_filtered() -> None:
    data = _load()
    assert data["software_versions"]
    assert all("ion os" in s.lower() or "planpoint" in s.lower() for s in data["software_versions"])
