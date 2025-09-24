"""Tests for V3 coding module enhancements."""

import pytest
from src.coding.kb import CodingKB
from src.coding.extractors import extract_case
from src.coding.rules import code_case
from src.coding.schema import StructureType

def test_kb_fallback_loads():
    """Test that KB loads with fallback."""
    kb = CodingKB(path=None)  # should pick preferred or fallback
    assert kb.version_info()
    assert isinstance(kb.version_info(), str)

def test_bilateral_modifier():
    """Test bilateral modifier -50 is added appropriately."""
    kb = CodingKB()
    report = "Bilateral thoracentesis performed under ultrasound guidance."
    case = extract_case(report, kb)
    # Force-detect thoracentesis as a performed item
    from src.coding.schema import PerformedItem
    case.items.append(PerformedItem(proc_id="thoracentesis"))
    bundle = code_case(case, kb)
    codes = {cl.code: cl for cl in bundle.professional}
    # With ultrasound, expect 32555 and -50 when bilateral indicated
    assert "32555" in codes
    assert "-50" in codes["32555"].modifiers

def test_extractor_error_is_caught():
    """Test that extraction errors are caught and reported."""
    kb = CodingKB()
    # Create a malformed case that should trigger error handling
    try:
        case = extract_case("Test report", kb)
        bundle = code_case(case, kb)
        # Even with errors, should return a valid bundle
        assert bundle is not None
    except Exception as e:
        pytest.fail(f"Extraction should handle errors gracefully: {e}")

def test_code_descriptions_present():
    """Test that all codes have descriptions."""
    kb = CodingKB()
    case = extract_case("Moderate sedation 32 minutes", kb)
    bundle = code_case(case, kb)
    for cl in bundle.professional:
        assert cl.description is not None
        assert isinstance(cl.description, str)

def test_enum_structure_type():
    """Test that StructureType enum works correctly."""
    kb = CodingKB()
    report = "EBUS-TBNA of stations 4R, 7, 11L. TBLB of RUL."
    case = extract_case(report, kb)
    
    # Check stations have correct structure type
    stations = [t for t in case.targets if t.structure_type == StructureType.STATION]
    assert len(stations) >= 3
    
    # Check lobes have correct structure type  
    lobes = [t for t in case.targets if t.structure_type == StructureType.LOBE]
    assert len(lobes) >= 1

def test_parsing_warnings_propagate():
    """Test that parsing warnings are propagated to the bundle."""
    kb = CodingKB()
    # Create a case with warnings
    from src.coding.schema import Case
    case = Case(report_text="test", parsing_warnings=["Test warning"])
    bundle = code_case(case, kb)
    assert "Test warning" in bundle.warnings

def test_kb_version_info():
    """Test KB version info is available."""
    kb = CodingKB()
    version = kb.version_info()
    assert version
    assert isinstance(version, str)
    assert "file:" in version or "version" in version

def test_qa_context_includes_kb_version():
    """Test Q&A context includes KB version."""
    from src.coding.qa import build_context
    kb = CodingKB()
    case = extract_case("Test report", kb)
    bundle = code_case(case, kb)
    ctx = build_context(case, bundle, kb=kb)
    assert "kb_version" in ctx
    assert ctx["kb_version"]

def test_named_groups_in_station_pattern():
    """Test that station pattern uses named groups."""
    from src.coding.patterns import PATTERNS
    pattern = PATTERNS['lymph_stations']
    match = pattern.search("Station 4R sampled")
    assert match
    # Should have named group
    assert match.group('station') or match.group('station2') or match.group('station3') or match.group('station4')

def test_clear_coding_context():
    """Test clearing coding context."""
    from src.coding.chat_router import clear_coding_context
    state = {"coding_ctx": {"test": "data"}, "other": "data"}
    new_state = clear_coding_context(state)
    assert "coding_ctx" not in new_state
    assert "other" in new_state

if __name__ == "__main__":
    pytest.main([__file__, "-v"])