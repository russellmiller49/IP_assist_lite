import pytest
from pathlib import Path

from medparse.config import (
    ExtractionConfig,
    ExtractionProfile,
    reset_extraction_config,
    set_extraction_config,
)
from medparse.extractors.article import extract_article
from medparse.pipeline.run_extract import PipelineConfig
from medparse.schema.article import ArticleDocument, Author, GuidelineRecommendation
from medparse.schema.common import EvidenceSpan
from medparse.validate.article_rules import validate_article

ARTICLE_CONFIG_PATH = Path("configs/run_article.yaml")
ARTICLES_DIR = Path("data/Input pdfs/articles/pdf")


@pytest.fixture()
def article_config():
    pipeline_config = PipelineConfig.from_path(ARTICLE_CONFIG_PATH)
    config = pipeline_config.to_extraction_config(use_cache=False)
    set_extraction_config(config)
    yield config
    reset_extraction_config()


@pytest.mark.integration
def test_guideline_title_and_recommendations(article_config):
    pdf_path = ARTICLES_DIR / "Combined EBUS  EUS for the diagnosis and staging of lung cancer ESGE, ERS, ESTS Guideline.pdf"
    if not pdf_path.exists():
        pytest.skip("Guideline fixture PDF not available")

    document = extract_article(pdf_path, config=article_config)

    assert document.doc_subtype == "guideline"
    assert document.title
    assert document.title_confidence >= 0.8
    assert "Guideline 545" not in document.title

    assert len(document.recommendations) >= 8
    with_grade = [rec for rec in document.recommendations if rec.grade_normalized]
    assert len(with_grade) / len(document.recommendations) >= 0.7

    max_cell = 0
    for table in document.tables:
        for row in table.rows:
            for cell in row:
                if isinstance(cell, str):
                    max_cell = max(max_cell, len(cell))
    assert max_cell <= 600


@pytest.mark.integration
def test_guideline_umls_status_recorded(article_config):
    pdf_path = ARTICLES_DIR / "Combined EBUS  EUS for the diagnosis and staging of lung cancer ESGE, ERS, ESTS Guideline.pdf"
    if not pdf_path.exists():
        pytest.skip("Guideline fixture PDF not available")

    document = extract_article(pdf_path, config=article_config)
    assert "umls_status" in document.pipeline_info


@pytest.mark.integration
def test_ebus_guideline_title_authors(article_config):
    pdf_path = ARTICLES_DIR / "Combined EBUS  EUS for the diagnosis and staging of lung cancer ESGE, ERS, ESTS Guideline.pdf"
    if not pdf_path.exists():
        pytest.skip("EBUS/EUS guideline fixture PDF not available")

    document = extract_article(pdf_path, config=article_config)

    expected_title = (
        "Combined endobronchial and esophageal endosonography for the diagnosis and staging of lung cancer: "
        "European Society of Gastrointestinal Endoscopy"
    )
    assert document.title.startswith(expected_title)
    assert document.authors, "expected authors to be extracted"
    first_author = document.authors[0]
    assert (first_author.given, first_author.family) == ("Peter", "Vilmann")
    assert len(document.authors) >= 10


@pytest.mark.integration
def test_ats_iip_title_authors(article_config):
    pdf_path = ARTICLES_DIR / "Guideline ATS Classification of Interstital Pneumonia.pdf"
    if not pdf_path.exists():
        pytest.skip("ATS IIP guideline fixture PDF not available")

    document = extract_article(pdf_path, config=article_config)

    expected_title = (
        "An Official American Thoracic Society/European Respiratory Society Statement: Update of the "
        "International Multidisciplinary Classification of the Idiopathic Interstitial Pneumonias"
    )
    assert document.title == expected_title
    assert document.authors, "expected authors to be extracted"
    first_author = document.authors[0]
    assert (first_author.given.rstrip('.'), first_author.family) == ("William D", "Travis")
    assert any(author.family == "Costabel" for author in document.authors)


def _make_recommendation(label: str, *, graded: bool) -> GuidelineRecommendation:
    if graded:
        return GuidelineRecommendation(
            label=label,
            text=f"Recommendation {label}",
            grade="A",
            evidence_level="high",
            evidence=EvidenceSpan(text="Sample evidence", page=1),
            grade_normalized={
                "scale": "GRADE",
                "strength": "strong",
                "certainty": "high",
                "source": "inline",
                "confidence": 0.9,
                "ungraded": False,
            },
        )
    return GuidelineRecommendation(
        label=label,
        text=f"Recommendation {label}",
        recommendation_type="consensus_statement",
        evidence=EvidenceSpan(text="Sample evidence", page=1),
    )


def test_grade_density_gate_triggers_warning():
    recommendations = [
        _make_recommendation(str(idx), graded=idx % 3 == 0)
        for idx in range(1, 11)
    ]
    document = ArticleDocument(
        doc_type="article",
        source_file="dummy.pdf",
        page_count=10,
        title="Test Guideline",
        doc_subtype="guideline",
        sections={"introduction": "Intro text"},
        recommendations=recommendations,
    )
    config = ExtractionConfig(
        profile=ExtractionProfile.ENRICHED,
        thresholds={
            "guideline": {
                "min_recommendations": 8,
                "min_grade_density": 0.7,
                "min_sections": 1,
            }
        },
    )

    issues = validate_article(document, config)

    assert issues, "expected validation issues for low typed density"
    assert any(
        issue.severity == "error" and "graded/typed coverage" in issue.message
        for issue in issues
    )


def test_guideline_warns_on_sparse_authors():
    recommendations = [_make_recommendation(str(idx), graded=True) for idx in range(8)]
    document = ArticleDocument(
        doc_type="article",
        source_file="dummy.pdf",
        page_count=8,
        title="Sparse Author Guideline",
        title_confidence=0.85,
        doc_subtype="guideline",
        sections={"introduction": "Intro text"},
        recommendations=recommendations,
        authors=[
            Author(given="Alice", family="Smith"),
            Author(given="Bob", family="Jones"),
        ],
    )
    config = ExtractionConfig(
        profile=ExtractionProfile.ENRICHED,
        thresholds={
            "guideline": {
                "min_recommendations": 8,
                "min_grade_density": 0.7,
                "min_sections": 1,
            }
        },
    )

    issues = validate_article(document, config)
    warnings = [issue for issue in issues if issue.severity == "warning"]
    assert any("few authors" in issue.message for issue in warnings)


def test_guideline_warns_on_low_title_confidence():
    recommendations = [_make_recommendation(str(idx), graded=True) for idx in range(8)]
    document = ArticleDocument(
        doc_type="article",
        source_file="dummy.pdf",
        page_count=8,
        title="Low Confidence Guideline",
        title_confidence=0.4,
        doc_subtype="guideline",
        sections={"introduction": "Intro text"},
        recommendations=recommendations,
        authors=[
            Author(given="Alice", family="Smith"),
            Author(given="Bob", family="Jones"),
            Author(given="Carol", family="Lee"),
        ],
    )
    config = ExtractionConfig(
        profile=ExtractionProfile.ENRICHED,
        thresholds={
            "guideline": {
                "min_recommendations": 8,
                "min_grade_density": 0.7,
                "min_sections": 1,
            }
        },
    )

    issues = validate_article(document, config)
    warnings = [issue for issue in issues if issue.severity == "warning"]
    assert any("title confidence" in issue.message for issue in warnings)
