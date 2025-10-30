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
def test_ats_yield_statement_is_statement_and_passes(article_config: ExtractionConfig) -> None:
    pdf_path = FIXTURES / "Guideline ATS diagnostic yield.pdf"
    if not pdf_path.exists():
        pytest.skip("ATS diagnostic yield fixture PDF not available")

    doc = extract_article(pdf_path, config=article_config)

    assert doc.doc_subtype == "statement"
    assert bool(doc.yield_definitions_present)
