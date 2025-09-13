"""Tests for mini-prompt parser."""

import pytest
from src.reporting.parser import parse_miniprompt, ParsedFacts


class TestParser:
    """Test mini-prompt parsing functionality."""
    
    def test_ion_detection(self):
        """Test Ion robotic bronchoscopy detection."""
        text = "Ion robotic bronchoscopy with navigation to RUL"
        result = parse_miniprompt(text)
        assert result.proc_key == "robotic_ion"
    
    def test_monarch_detection(self):
        """Test Monarch robotic bronchoscopy detection."""
        text = "Monarch platform navigation to peripheral nodule"
        result = parse_miniprompt(text)
        assert result.proc_key == "robotic_monarch"
    
    def test_ebus_staging_detection(self):
        """Test EBUS staging detection."""
        text = "EBUS systematic staging with sampling of stations 4R, 7, 11L"
        result = parse_miniprompt(text)
        assert result.proc_key == "ebus_systematic_staging_ett"
    
    def test_pdt_detection(self):
        """Test PDT detection."""
        text = "Percutaneous dilatational tracheostomy with bronchoscopic guidance"
        result = parse_miniprompt(text)
        assert result.proc_key == "pdt"
    
    def test_gauge_extraction(self):
        """Test needle gauge extraction."""
        text = "TBNA performed with 23G needle"
        result = parse_miniprompt(text)
        assert result.tokens.get("tbna_gauge") == "23"
    
    def test_passes_extraction(self):
        """Test needle passes extraction."""
        text = "Performed 5 needle passes at each station"
        result = parse_miniprompt(text)
        assert result.tokens.get("tbna_passes") == "5"
    
    def test_cryo_extraction(self):
        """Test cryobiopsy details extraction."""
        text = "Cryobiopsy x3 with 1.1mm probe, 6 second freeze"
        result = parse_miniprompt(text)
        assert result.tokens.get("cryo_passes") == "3"
        assert result.tokens.get("cryo_probe_mm") == "1.1"
        assert result.tokens.get("cryo_freeze_s") == "6"
    
    def test_rose_extraction(self):
        """Test ROSE result extraction."""
        text = "ROSE positive for malignant cells"
        result = parse_miniprompt(text)
        assert result.tokens.get("rose") == "positive"
        
        text2 = "ROSE: adequate lymphoid tissue"
        result2 = parse_miniprompt(text2)
        assert result2.tokens.get("rose") == "adequate"
    
    def test_station_extraction(self):
        """Test lymph node station extraction."""
        text = "Sampled stations 2R, 4R, 7, 10L, 11R"
        result = parse_miniprompt(text)
        stations = [t["id"] for t in result.targets if t["type"] == "station"]
        assert "2R" in stations
        assert "4R" in stations
        assert "7" in stations
        assert "10L" in stations
        assert "11R" in stations
    
    def test_lobe_extraction(self):
        """Test lobe extraction."""
        text = "Navigation to RUL anterior segment, also sampled RML and RLL"
        result = parse_miniprompt(text)
        lobes = [t["id"] for t in result.targets if t["type"] == "lobe"]
        assert "RUL" in lobes
        assert "RML" in lobes
        assert "RLL" in lobes
    
    def test_imaging_adjuncts(self):
        """Test imaging modality detection."""
        text = "Used CBCT (Cios spin) and radial EBUS for confirmation"
        result = parse_miniprompt(text)
        assert result.adjuncts["cbct"] is True
        assert result.adjuncts["rebus"] is True
        
        text2 = "Fluoroscopy and digital tomosynthesis guidance"
        result2 = parse_miniprompt(text2)
        assert result2.adjuncts["fluoro"] is True
        assert result2.adjuncts["dts"] is True
    
    def test_complications_extraction(self):
        """Test complications extraction."""
        text = "No pneumothorax, minimal bleeding"
        result = parse_miniprompt(text)
        assert result.complications.get("pneumothorax") == "none"
        assert result.complications.get("bleeding") == "minimal"
        
        text2 = "Moderate bleeding controlled with APC"
        result2 = parse_miniprompt(text2)
        assert result2.complications.get("bleeding") == "moderate"
    
    def test_complex_miniprompt(self):
        """Test parsing of complex real-world mini-prompt."""
        with open("data/fixtures/robotic_ion_case_01.txt", "r") as f:
            text = f.read()
        
        result = parse_miniprompt(text)
        assert result.proc_key == "robotic_ion"
        assert result.tokens.get("tbna_gauge") == "23"
        assert result.tokens.get("tbna_passes") == "5"
        assert result.tokens.get("rose") == "positive"
        assert result.adjuncts["cbct"] is True
        assert result.adjuncts["rebus"] is True
        assert result.complications.get("bleeding") == "minimal"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])