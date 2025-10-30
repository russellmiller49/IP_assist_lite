from pathlib import Path

from medparse.extract.articles import extract_article


def test_article_extraction_captures_metadata_and_yield() -> None:
    pdf_path = Path("tests/data/articles/Robotic_Cryobiopsy_2022.pdf")
    document = extract_article(pdf_path)

    assert document.doc_type == "article"
    assert document.title == "Robotic Cryobiopsy 2022"
    assert document.abstract and "peripheral lung lesions" in document.abstract.lower()
    assert document.n_patients == 112
    assert document.n_lesions == 120
    assert document.yield_summary and document.yield_summary.strict_yield == 101 / 112

    complications = {outcome.name for outcome in document.outcomes}
    assert "pneumothorax" in complications

    assert document.tables, "expected diagnostic tables to be captured"
    assert document.references and len(document.references) >= 2
