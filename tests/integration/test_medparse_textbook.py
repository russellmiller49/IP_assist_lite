from pathlib import Path

from medparse.extract.textbook import extract_textbook_chapter


def test_textbook_chapter_extraction_merges_book_meta() -> None:
    pdf_path = Path(
        "tests/data/textbooks/airway_fistulas/02_Treatment_of_Airway-Esophageal_Fistulas.pdf"
    )
    document = extract_textbook_chapter(pdf_path)

    assert document.doc_type == "textbook_chapter"
    assert document.chapter_title.startswith("Treatment of Airway-Esophageal Fistulas")
    assert document.chapter_number == "02"
    assert document.authors
    assert document.book_meta and document.book_meta.book_title
    assert len(document.sections) >= 3
