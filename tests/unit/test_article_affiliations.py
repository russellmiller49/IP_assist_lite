from __future__ import annotations

import pytest

from medparse.ingest.models import PageData
from medparse.normalize.article_frontmatter import extract_superscript_affiliations
from medparse.normalize.article_frontmatter import link_authors_to_affiliations
from medparse.pipeline.run_extract import _document_metrics
from medparse.schema.article import Affiliation, ArticleDocument, Author
from medparse.second_pass.patchers.article_affiliations import apply_article_affiliations
from medparse.second_pass.types import SecondPassContext


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


def test_article_affiliations_nearest_mapping_second_pass() -> None:
    authors = [
        Author(given="Alice", family="Johnson"),
        Author(given="Brian", family="Lee"),
    ]
    affiliations = [
        Affiliation(
            id="1",
            text="Massachusetts General Hospital, Boston, Massachusetts; Brigham and Women's Hospital, Boston, Massachusetts; for the Lung Screening Research Group",
        )
    ]
    document = ArticleDocument(
        doc_type="article",
        source_file="nejm.pdf",
        page_count=1,
        authors=authors,
        affiliations=affiliations,
    )
    document.pipeline_info = {}

    paragraph_store = {
        "p1": {"text": "Original Article", "order": [1], "page": 1},
        "p2": {
            "text": "Alice Johnson, M.D., Massachusetts General Hospital, Boston, Massachusetts",
            "order": [2],
            "page": 1,
        },
        "p3": {
            "text": "Brian Lee, M.D., Brigham and Women's Hospital, Boston, Massachusetts",
            "order": [3],
            "page": 1,
        },
        "p4": {
            "text": "for the Lung Screening Research Group",
            "order": [4],
            "page": 1,
        },
    }

    ctx = SecondPassContext(
        validation_issues=[],
        paragraph_store=paragraph_store,
        evidence_bank={},
        profile=None,
        engines_tried=[],
        emit_policies={},
        config={},
        mode="always",
        doc_metrics={},
        max_runtime_ms=2500,
    )

    result = apply_article_affiliations(document, ctx)
    assert result.applied is True
    assert "affiliations_split" in result.modifications
    assert result.modifications["affiliations_split"] >= 1
    assert document.pipeline_info.get("frontmatter_affiliations_unresolved") == 0
    consortia = document.pipeline_info.get("affiliation_consortia", [])
    assert consortia and "Lung Screening Research Group" in consortia[0]

    assert document.authors[0].affiliation_ids == ["1"]
    assert document.authors[1].affiliation_ids
    assert document.authors[1].affiliation_ids != ["1"]


def test_article_affiliations_zotero_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    authors = [
        Author(given="Alice", family="Baker"),
        Author(given="Brian", family="Clark"),
    ]
    affiliations = [
        Affiliation(id="1", text="Existing Department"),
    ]
    document = ArticleDocument(
        doc_type="article",
        source_file="nejm.pdf",
        page_count=1,
        authors=authors,
        affiliations=affiliations,
    )
    document.pipeline_info = {"metadata_sources": {"zotero_json": "/tmp/zotero.json"}}

    class StubAuthor:
        def __init__(self, given: str, family: str, affiliation: str):
            self.given = given
            self.family = family
            self.affiliation = affiliation

    class StubFrontMatter:
        def __init__(self) -> None:
            self.authors = [StubAuthor("Alice", "Baker", "Zotero Department")]

    monkeypatch.setattr(
        "medparse.second_pass.patchers.article_affiliations.configure_zotero_library",
        lambda path: None,
    )
    monkeypatch.setattr(
        "medparse.second_pass.patchers.article_affiliations.lookup_front_matter",
        lambda doi, title: StubFrontMatter(),
    )

    ctx = SecondPassContext(
        validation_issues=[],
        paragraph_store={},
        evidence_bank={},
        profile=None,
        engines_tried=[],
        emit_policies={},
        config={},
        mode="always",
        doc_metrics={},
        max_runtime_ms=2500,
    )

    result = apply_article_affiliations(document, ctx)
    assert result.applied is True
    assert document.authors[0].affiliation_ids
    assert document.authors[0].affiliation_ids[0] != "1"
    assert document.pipeline_info["metadata_sources"]["zotero_json"] == "/tmp/zotero.json"
    assert document.pipeline_info.get("affiliation_zotero_mapped") == 1
    assert document.pipeline_info.get("affiliation_zotero_added") == 1
    assert any(aff.text == "Zotero Department" for aff in document.affiliations)
    assert result.modifications.get("affiliations_zotero_mapped") == 1
