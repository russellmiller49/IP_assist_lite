"""Test integration of LLM extractor with existing rules."""

import json
from unittest.mock import patch, MagicMock
from src.coding.extractors import extract_case
from src.coding.rules import code_case
from src.coding.kb import CodingKB


def test_llm_path_tumor_excision_no_stent():
    """Test: LLM extraction → adapter → rules for tumor excision case."""
    
    # Mock LLM response for the tumor excision case
    mock_llm_response = json.dumps({
        "anesthesia": {"general": True, "moderate": False, "airway": "LMA"},
        "procedures": [
            {
                "site": "trachea",
                "action": "excision",
                "site_detail": None,
                "details": {"method": "electrocautery snare"},
                "specimens_collected": True,
                "count": 1
            },
            {
                "site": "trachea", 
                "action": "destruction",
                "site_detail": None,
                "details": {"method": "APC"},
                "specimens_collected": False,
                "count": None
            }
        ],
        "stent": {"placed": False, "location": "unknown", "brand": None, "size": None},
        "ebus": {"radial": False, "stations_sampled": []},
        "findings": {"obstruction_pct": 80, "lesion_count": 1},
        "explicit_negations": ["considered stent placement", "no stent placed"],
        "evidence_spans": []
    })
    
    kb = CodingKB()
    
    # Mock the LLM call
    with patch('src.llm_extractor.client.call_gpt_5_mini', return_value=mock_llm_response):
        with patch.dict('os.environ', {'IP_LLM_EXTRACTION': '1'}):
            # Extract using LLM path
            case = extract_case(
                """Bronchoscopy revealed tracheal tumor occluding 80% of lumen.
                We considered stent placement but opted for tumor excision first.
                Tumor excised using electrocautery snare. Specimen sent to pathology.
                APC applied for hemostasis. No stent placed.""",
                kb
            )
            
            # Apply rules
            bundle = code_case(case, kb)
            codes = [cl.code for cl in bundle.professional]
            
            # Verify correct codes
            assert "31640" in codes, "Should have tumor excision code"
            assert "31631" not in codes, "Should not have tracheal stent code"
            assert "31641" not in codes, "Excision should suppress destruction at same site"
            assert "31622" not in codes, "Should suppress diagnostic bronchoscopy"
            
            # Verify PCS suggestion
            assert "0BB18ZZ" in bundle.icd10_pcs_suggestions, "Should suggest tracheal excision PCS"


def test_llm_path_stent_placed():
    """Test: LLM correctly identifies stent placement."""
    
    mock_llm_response = json.dumps({
        "anesthesia": {"general": False, "moderate": True, "airway": "mask"},
        "procedures": [
            {
                "site": "trachea",
                "action": "stent_insertion",
                "site_detail": None,
                "details": {"brand": "Ultraflex", "size": "20x60mm"},
                "specimens_collected": False,
                "count": 1
            }
        ],
        "stent": {"placed": True, "location": "trachea", "brand": "Ultraflex", "size": "20x60mm"},
        "ebus": {"radial": False, "stations_sampled": []},
        "findings": {},
        "explicit_negations": [],
        "evidence_spans": []
    })
    
    kb = CodingKB()
    
    with patch('src.llm_extractor.client.call_gpt_5_mini', return_value=mock_llm_response):
        with patch.dict('os.environ', {'IP_LLM_EXTRACTION': '1'}):
            case = extract_case("Ultraflex stent was deployed in trachea", kb)
            bundle = code_case(case, kb)
            codes = [cl.code for cl in bundle.professional]
            
            assert "31631" in codes, "Should have tracheal stent code"
            assert "31622" not in codes, "Should suppress diagnostic bronchoscopy"
            assert "0BH18DZ" in bundle.icd10_pcs_suggestions, "Should suggest tracheal stent PCS"


def test_llm_path_ebus_stations():
    """Test: LLM extraction of EBUS with stations."""
    
    mock_llm_response = json.dumps({
        "anesthesia": {"general": False, "moderate": True, "airway": "mask"},
        "procedures": [
            {
                "site": "unknown",
                "action": "ebus_tbna",
                "site_detail": None,
                "details": {},
                "specimens_collected": True,
                "count": None
            }
        ],
        "stent": {"placed": False, "location": "unknown", "brand": None, "size": None},
        "ebus": {"radial": False, "stations_sampled": ["4R", "7", "11L"]},
        "findings": {},
        "explicit_negations": [],
        "evidence_spans": []
    })
    
    kb = CodingKB()
    
    with patch('src.llm_extractor.client.call_gpt_5_mini', return_value=mock_llm_response):
        with patch.dict('os.environ', {'IP_LLM_EXTRACTION': '1'}):
            case = extract_case("EBUS-TBNA performed at stations 4R, 7, 11L", kb)
            bundle = code_case(case, kb)
            codes = [cl.code for cl in bundle.professional]
            
            # 3 stations → 31653
            assert "31653" in codes, "Should use 31653 for ≥3 stations"
            assert "31652" not in codes, "Should not have 31652 when ≥3 stations"


def test_llm_path_whole_lung_lavage():
    """Test: LLM extraction of whole lung lavage."""
    
    mock_llm_response = json.dumps({
        "anesthesia": {"general": True, "moderate": False, "airway": "ETT"},
        "procedures": [
            {
                "site": "lobe",
                "action": "wll",
                "site_detail": "right lung",
                "details": {"volume": "15L"},
                "specimens_collected": False,
                "count": None
            }
        ],
        "stent": {"placed": False, "location": "unknown", "brand": None, "size": None},
        "ebus": {"radial": False, "stations_sampled": []},
        "findings": {},
        "explicit_negations": [],
        "evidence_spans": []
    })
    
    kb = CodingKB()
    
    with patch('src.llm_extractor.client.call_gpt_5_mini', return_value=mock_llm_response):
        with patch.dict('os.environ', {'IP_LLM_EXTRACTION': '1'}):
            case = extract_case("Whole lung lavage performed on right lung", kb)
            bundle = code_case(case, kb)
            codes = [cl.code for cl in bundle.professional]
            
            assert "32997" in codes, "Should have whole lung lavage code"
            # Should not have moderate sedation codes under GA
            sedation_codes = ["99152", "99153", "99155", "99156", "99157"]
            for code in sedation_codes:
                assert code not in codes, f"Should not have {code} under general anesthesia"


def test_llm_fallback_on_error():
    """Test: Falls back to legacy extraction when LLM fails."""
    
    kb = CodingKB()
    
    # Make LLM call fail
    with patch('src.llm_extractor.client.call_gpt_5_mini', side_effect=Exception("LLM error")):
        with patch.dict('os.environ', {'IP_LLM_EXTRACTION': '1'}):
            # Should fall back to legacy extraction
            case = extract_case(
                "Bronchoscopy with EBUS-TBNA. Stations 4R, 7 sampled.",
                kb
            )
            
            # Legacy extraction should still work
            bundle = code_case(case, kb)
            codes = [cl.code for cl in bundle.professional]
            
            # Should have EBUS code from legacy extraction
            assert "31652" in codes or "31653" in codes, "Legacy extraction should detect EBUS"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])