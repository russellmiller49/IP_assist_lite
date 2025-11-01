import pytest
from pathlib import Path

from medparse.config import reset_extraction_config, set_extraction_config
from medparse.extractors.article import extract_article
from medparse.pipeline.run_extract import PipelineConfig

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
def test_research_diagnostic_yield_relaxed(article_config):
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
        assert yield_data.reported_value is not None
        assert yield_data.reported_value == pytest.approx(0.90, rel=0.05)
        assert "no_n_over_N" in (yield_data.exclusion_reasons or [])
