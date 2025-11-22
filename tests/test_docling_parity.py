import pytest
from pathlib import Path
import json
from src.contracts.schema import ExtractionResult

GOLDEN_DIR = Path("tests/_golden/ifus_docling")

@pytest.mark.parametrize("golden_file", GOLDEN_DIR.glob("*.json"))
def test_docling_parity_ifu(golden_file):
    """
    Compares Docling extraction against basic sanity metrics (Parity Check).
    """
    with open(golden_file) as f:
        data = json.load(f)
        
    result = ExtractionResult(**data)
    
    # 1. Page Count Sanity
    # We expect page count to be reasonable (extracted from metrics)
    page_count = result.metrics.get("extraction_metrics", {}).get("page_count", 0)
    assert page_count > 0, "Page count should be positive"
    
    # 2. Chunk Counts
    # Should have chunks if page count is > 0
    assert len(result.chunks) > 0, "Should have extracted chunks"
    
    # 3. Table Counts
    # If tables exist, table_sentences should also exist
    if result.tables:
        assert len(result.table_sentences) > 0, "Tables found but no sentences generated"
        
    # 4. Safety Policy
    # Check if safety warnings exist for IFUs (heuristic)
    if result.doc_type == "ifu":
        assert len(result.safety_warnings) > 0, "IFU should have safety warnings"
        
    # 5. Schema Version
    assert result.schema_version == "2.0.0"

def test_legacy_parity_comparison():
    """
    Placeholder: logic to load a 'classic' extraction result and compare.
    """
    pass
