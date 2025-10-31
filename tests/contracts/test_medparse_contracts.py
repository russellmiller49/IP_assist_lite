from __future__ import annotations

from pathlib import Path

import pytest

from medparse.config import reset_extraction_config, set_extraction_config
from medparse.extractors.article import extract_article
from medparse.extractors.ifu import extract_ifu
from medparse.extractors.textbook import extract_textbook_chapter
from medparse.pipeline.run_extract import PipelineConfig
from medparse.validate.validators import validate_document


ARTICLE_CONFIG_PATH = Path("configs/run_article.yaml")
IFU_CONFIG_PATH = Path("configs/run_ifu.yaml")
TEXTBOOK_CONFIG_PATH = Path("configs/run_textbook.yaml")


@pytest.fixture()
def article_config():
    pipeline_config = PipelineConfig.from_path(ARTICLE_CONFIG_PATH)
    config = pipeline_config.to_extraction_config(use_cache=False)
    set_extraction_config(config)
    yield config
    reset_extraction_config()


@pytest.fixture()
def ifu_config():
    pipeline_config = PipelineConfig.from_path(IFU_CONFIG_PATH)
    config = pipeline_config.to_extraction_config(use_cache=False)
    set_extraction_config(config)
    yield config
    reset_extraction_config()


@pytest.fixture()
def textbook_config():
    pipeline_config = PipelineConfig.from_path(TEXTBOOK_CONFIG_PATH)
    config = pipeline_config.to_extraction_config(use_cache=False)
    set_extraction_config(config)
    yield config
    reset_extraction_config()


@pytest.mark.contract
def test_guideline_has_graded_recs(article_config):
    pdf_path = Path(
        "data/Input pdfs/articles/pdf/Combined EBUS  EUS for the diagnosis and staging of lung cancer ESGE, ERS, ESTS Guideline.pdf"
    )
    if not pdf_path.exists():
        pytest.skip("Guideline fixture PDF is not available.")

    document = extract_article(pdf_path, config=article_config)
    assert document.doc_subtype == "guideline"
    assert len(document.recommendations) >= 8
    graded = [
        rec
        for rec in document.recommendations
        if rec.grade or rec.statement_type != "graded"
    ]
    assert graded
    assert len(graded) / len(document.recommendations) >= 0.7
    assert document.title
    assert "combined endobronchial and esophageal" in document.title.lower()
    assert document.authors, "Expected authors parsed from front matter"
    assert document.sections, "Expected sectionized content"
    umls_status = document.pipeline_info.get("umls_status")
    if umls_status != "linked":
        pytest.skip("UMLS linker unavailable for contract test.")
    assert len(document.umls_entities) > 0, "UMLS entities should be populated for guidelines"


@pytest.mark.contract
def test_ats_diagnostic_yield_guideline_title(article_config):
    pdf_path = Path("data/Input pdfs/articles/pdf/Guideline ATS diagnostic yield.pdf")
    if not pdf_path.exists():
        pytest.skip("ATS diagnostic yield PDF is not available.")

    document = extract_article(pdf_path, config=article_config)
    assert document.title
    assert document.title.strip().lower() != "american thoracic society"
    assert document.sections, "Expected section text for ATS diagnostic yield"
    abstract_text = (document.sections.get("abstract") or "").strip()
    assert abstract_text, "Abstract section should be populated"
    table_captions = [table.caption or "" for table in document.tables or []]
    assert not any("abstract" in caption.lower() for caption in table_captions)


@pytest.mark.contract
def test_research_yield_missing_counts_warns_not_fails(article_config):
    pdf_path = Path("data/Input pdfs/articles/pdf/Robotic Cyrobiopsy 2022.pdf")
    if not pdf_path.exists():
        pytest.skip("Research article fixture PDF is not available.")

    document = extract_article(pdf_path, config=article_config)
    issues = validate_document(document)
    error_messages = [issue.message for issue in issues if issue.severity == "error"]
    warning_messages = [issue.message for issue in issues if issue.severity == "warning"]

    assert not error_messages
    assert any(
        "numerator/denominator" in message.lower()
        for message in warning_messages
    )
    assert document.diagnostic_yield is not None
    diag = document.diagnostic_yield
    assert diag.value is not None
    assert diag.numerator is None and diag.denominator is None
    assert diag.strict is False
    assert diag.compatible_with_ats is False
    assert {
        "missing_numerator_denominator",
        "non_strict_reported",
    }.issubset(set(diag.exclusion_reasons or []))


@pytest.mark.contract
def test_ion_ifu_no_toc_bleed(ifu_config):
    pdf_path = Path(
        "data/Input pdfs/IFUs/pdf/Ion Endoluminal System, Instruments, and Accessories User Manual(553990-11).pdf"
    )
    if not pdf_path.exists():
        pytest.skip("Ion IFU fixture PDF is not available.")

    document = extract_ifu(pdf_path, config=ifu_config)
    text = (document.indications_for_use or "").lower()
    assert "table of contents" not in text
    assert document.part_number
    assert document.revision
    assert document.model
    assert document.publication_date
    toc_guard = document.pipeline_info.get("toc_guard")
    assert toc_guard is not None
    assert toc_guard.get("enabled") is True
    assert toc_guard.get("pages_dropped") is not None
    issues = validate_document(document)
    bleed_errors = [
        issue.message for issue in issues if "anchor bleed" in issue.message.lower()
    ]
    assert not bleed_errors
    assert not document.pipeline_info.get("anchor_bleed_errors")


@pytest.mark.contract
def test_erbe_ifu_front_matter_and_tables(ifu_config):
    pdf_path = Path(
        "data/Input pdfs/IFUs/pdf/30180-103_ERBE_EN_SystemCarrier_performance__D294849.pdf"
    )
    if not pdf_path.exists():
        pytest.skip("ERBE SystemCarrier IFU fixture PDF is not available.")

    document = extract_ifu(pdf_path, config=ifu_config)
    assert document.manufacturer and "erbe" in document.manufacturer.lower()
    assert document.part_number
    assert document.revision
    assert document.publication_date
    assert document.model


@pytest.mark.contract
def test_textbook_coverage(textbook_config):
    pdf_path = Path(
        "data/Input pdfs/Texbooks/Principles and Practice of Interventional Pulmonology/Treatment of Airway-Esophageal Fistulas.pdf"
    )
    if not pdf_path.exists():
        pytest.skip("Textbook chapter fixture PDF is not available.")

    document = extract_textbook_chapter(pdf_path, config=textbook_config)
    assert document.coverage_ratio is not None
    assert document.coverage_ratio >= 0.8
    issues = validate_document(document)
    errors = [issue for issue in issues if issue.severity == "error"]
    assert not errors
