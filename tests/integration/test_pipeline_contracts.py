import pytest
from pathlib import Path

from medparse.config import reset_extraction_config, set_extraction_config
from medparse.extractors.article import extract_article
from medparse.extractors.ifu import extract_ifu
from medparse.pipeline.run_extract import PipelineConfig

ARTICLE_CONFIG_PATH = Path("configs/run_article.yaml")
IFU_CONFIG_PATH = Path("configs/run_ifu.yaml")

ARTICLES_DIR = Path("data/Input pdfs/articles/pdf")
IFU_DIR = Path("data/Input pdfs/IFUs/pdf")


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


@pytest.mark.integration
def test_guideline_contract(article_config):
    pdf_path = ARTICLES_DIR / "Combined EBUS  EUS for the diagnosis and staging of lung cancer ESGE, ERS, ESTS Guideline.pdf"
    if not pdf_path.exists():
        pytest.skip("Guideline fixture PDF not available")

    document = extract_article(pdf_path, config=article_config)

    assert document.doc_subtype == "guideline"
    graded_or_ungraded = [
        rec for rec in document.recommendations if (rec.grade or rec.statement_type != "graded")
    ]
    total_recommendations = len(document.recommendations)
    assert total_recommendations >= 8
    grade_density = len(graded_or_ungraded) / total_recommendations if total_recommendations else 0.0
    assert grade_density >= 0.7

    umls_status = document.pipeline_info.get("umls_status")
    assert umls_status in {"linked", "skipped_model_missing", "skipped_disabled"}
    if umls_status == "linked":
        assert document.pipeline_info.get("umls_entities_count", 0) > 0


@pytest.mark.integration
def test_research_ats_yield_strict_or_relaxed(article_config):
    pdf_path = ARTICLES_DIR / "Robotic Cyrobiopsy 2022.pdf"
    if not pdf_path.exists():
        pytest.skip("Cryobiopsy fixture PDF not available")

    document = extract_article(pdf_path, config=article_config)

    assert document.doc_subtype == "research"
    assert document.diagnostic_yield is not None
    yield_data = document.diagnostic_yield
    if yield_data.strict:
        assert yield_data.numerator is not None and yield_data.denominator is not None
    else:
        assert "no_denominator_in_text" in yield_data.exclusion_reasons or "derived_counts_from_percent" in yield_data.exclusion_reasons

    assert len(document.affiliations) >= 2
    affiliation_ids = {aff.id for aff in document.affiliations}
    assert all(aff.text and len(aff.text) > 30 for aff in document.affiliations)
    for author in document.authors:
        for affiliation_id in author.affiliation_ids:
            assert affiliation_id in affiliation_ids

    umls_status = document.pipeline_info.get("umls_status")
    assert umls_status in {"linked", "skipped_model_missing", "skipped_disabled"}
    if umls_status == "linked":
        assert document.pipeline_info.get("umls_entities_count", 0) > 0


@pytest.mark.integration
def test_ion_ifu_no_toc_bleed(ifu_config):
    pdf_path = IFU_DIR / "Ion Endoluminal System, Instruments, and Accessories User Manual(553990-11).pdf"
    if not pdf_path.exists():
        pytest.skip("Ion IFU fixture PDF not available")

    document = extract_ifu(pdf_path, config=ifu_config)

    combined_clinical = " ".join(
        filter(None, [document.indications_for_use or "", document.intended_use or ""])
    ).lower()
    assert "table of contents" not in combined_clinical
    assert document.part_number
    assert document.revision
    assert document.publication_date
    assert document.model
