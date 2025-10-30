from pathlib import Path

import pytest

from medparse.config import ExtractionConfig, reset_extraction_config, set_extraction_config
from medparse.extractors.article import extract_article
from medparse.pipeline.run_extract import PipelineConfig

ARTICLE_CONFIG_PATH = Path("configs/run_article.yaml")
FIXTURES = Path("data/Input pdfs/articles/pdf")


@pytest.fixture()
def article_config() -> ExtractionConfig:
    pipeline_config = PipelineConfig.from_path(ARTICLE_CONFIG_PATH)
    config = pipeline_config.to_extraction_config(use_cache=False)
    set_extraction_config(config)
    yield config
    reset_extraction_config()


@pytest.mark.integration
def test_ebus_guideline_has_graded_recs(article_config: ExtractionConfig) -> None:
    pdf_path = FIXTURES / "Combined EBUS  EUS for the diagnosis and staging of lung cancer ESGE, ERS, ESTS Guideline.pdf"
    if not pdf_path.exists():
        pytest.skip("EBUS/EUS guideline fixture PDF not available")

    doc = extract_article(pdf_path, config=article_config)

    graded_like = [
        rec for rec in doc.recommendations if rec.grade or rec.statement_type != "graded"
    ]
    assert len(graded_like) >= 8

