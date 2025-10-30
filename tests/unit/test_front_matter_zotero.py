from pathlib import Path

from medparse.normalize.zotero_map import configure_zotero_library, lookup_front_matter


def test_zotero_fm_fill() -> None:
    library_path = Path("data/zotero/my_library.json")
    if not library_path.exists():
        raise RuntimeError("Zotero library fixture missing")

    configure_zotero_library(str(library_path))
    try:
        fm = lookup_front_matter(doi="10.1378/chest.15-0022", title=None)
        assert fm is not None
        assert fm.authors
    finally:
        configure_zotero_library(None)
