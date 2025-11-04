from __future__ import annotations

import pytest

from medparse.ingest.models import PageData
from medparse.normalize.article_frontmatter import link_authors_to_affiliations
from medparse.normalize.article_frontmatter import extract_superscript_affiliations
from medparse.pipeline.run_extract import _document_metrics
from medparse.schema.article import Affiliation, ArticleDocument, Author


def test_link_authors_to_affiliations_returns_unresolved() -> None:
    authors = [
        Author(given="Jane", family="Doe"),
        Author(given="John", family="Smith"),
    ]
    affiliations = [
        Affiliation(id="1", text="Department A"),
        Affiliation(id="2", text="Department B"),
    ]
    pages = [
        PageData(
            number=1,
            text="Jane Doe et al."
            "\n"
            "Smith et al.",
            lines=["Jane Doe et al.", "John Smith et al."],
            headings=[],
            tables=[],
        )
    ]

    unresolved = link_authors_to_affiliations(authors, affiliations, pages)

    assert sorted(unresolved) == ["Doe", "Smith"]
    assert authors[0].affiliation_ids == []
    assert authors[1].affiliation_ids == []


def test_document_metrics_include_affiliation_counter() -> None:
    document = ArticleDocument(doc_type="article", source_file="stub.pdf", page_count=1)
    document.pipeline_info["frontmatter_affiliations_unresolved"] = 3
    metrics = _document_metrics(document)
    assert metrics["frontmatter_affiliations_unresolved"] == 3


def test_extract_superscript_affiliations_letter_markers() -> None:
    text = "\n".join(
        [
            "Affiliations",
            "a Department of Pulmonology, University A",
            "b Division of Thoracic Surgery, Hospital B",
        ]
    )
    mapping = extract_superscript_affiliations(text)
    assert mapping["a"].startswith("Department of Pulmonology")
    assert mapping["b"].startswith("Division of Thoracic Surgery")


def test_link_authors_to_affiliations_majority_mapped(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("WARNING")
    authors = [
        Author(given="Alice", family="Brown"),
        Author(given="Brian", family="Clark"),
        Author(given="Cara", family="Davis"),
    ]
    affiliations = [
        Affiliation(id="1", text="Department of Pulmonology, University A"),
        Affiliation(id="2", text="Division of Thoracic Surgery, Hospital B"),
    ]
    lines = [
        "Alice Brown 1, Brian Clark 2, Cara Davis",
        "Affiliations",
        "1 Department of Pulmonology, University A",
        "2 Division of Thoracic Surgery, Hospital B",
    ]
    pages = [PageData(number=1, text="\n".join(lines), lines=lines, headings=[], tables=[])]

    unresolved = link_authors_to_affiliations(authors, affiliations, pages)

    assert len(unresolved) == 1
    assert authors[0].affiliation_ids == ["1"]
    assert authors[1].affiliation_ids == ["2"]
    assert authors[2].affiliation_ids == []
    assert "Unable to resolve" not in caplog.text
