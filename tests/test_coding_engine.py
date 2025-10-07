"""Test suite for V3 coding engine."""

import json
from src.coding.compat_v2 import ProcedureCodingEngine, format_coding_results

def test_smoke_examples():
    engine = ProcedureCodingEngine()
    # A concise sanity test (the full suite remains in test_coding_module.py if you keep it)
    report = """
        PROCEDURE: Bronchoscopy with linear EBUS-TBNA
        INDICATION: mediastinal adenopathy
        SEDATION: Moderate sedation, 45 minutes
        DETAILS: Stations 4R, 7, 11R sampled.
    """
    analysis = engine.analyze_procedure_report(report)
    codes = [c.code for c in (analysis.primary_codes + analysis.addon_codes + analysis.sedation_codes)]
    assert "31653" in codes and "99152" in codes
    
def test_ebus_station_logic():
    """Test EBUS station counting: 1-2 stations → 31652; ≥3 → 31653"""
    engine = ProcedureCodingEngine()
    
    # Test with 1-2 stations
    report_2_stations = """
        PROCEDURE: EBUS-TBNA
        Stations sampled: 4R, 7
    """
    analysis = engine.analyze_procedure_report(report_2_stations)
    codes = [c.code for c in analysis.primary_codes]
    assert "31652" in codes
    assert "31653" not in codes
    
    # Test with ≥3 stations
    report_3_stations = """
        PROCEDURE: EBUS-TBNA
        Stations sampled: 4R, 7, 11L
    """
    analysis = engine.analyze_procedure_report(report_3_stations)
    codes = [c.code for c in analysis.primary_codes]
    assert "31653" in codes
    assert "31652" not in codes

def test_tblb_lobes():
    """Test TBLB: 31628 + +31632 for additional lobes"""
    engine = ProcedureCodingEngine()
    
    report = """
        PROCEDURE: Bronchoscopy with transbronchial lung biopsy
        LOBES: RUL, RML, RLL biopsied
    """
    analysis = engine.analyze_procedure_report(report)
    codes = [c.code for c in (analysis.primary_codes + analysis.addon_codes)]
    assert "31628" in codes  # First lobe
    assert "+31632" in codes  # Additional lobes

def test_navigation():
    """Test navigation: always adds +31627 with OPPS note"""
    engine = ProcedureCodingEngine()
    
    report = """
        PROCEDURE: Navigation bronchoscopy with biopsy
        Used ION robotic system for navigation
    """
    analysis = engine.analyze_procedure_report(report)
    codes = [c.code for c in analysis.addon_codes]
    assert "+31627" in codes
    assert any("packaged" in note.lower() for note in analysis.facility_notes)

def test_sedation_family():
    """Test sedation: correct family chosen based on provider"""
    engine = ProcedureCodingEngine()
    
    # Proceduralist provides sedation
    report_proc = """
        PROCEDURE: Bronchoscopy
        SEDATION: Moderate sedation 45 minutes, administered by proceduralist
    """
    analysis = engine.analyze_procedure_report(report_proc)
    codes = [c.code for c in analysis.sedation_codes]
    assert "99152" in codes  # Initial by proceduralist
    
    # Different provider (anesthesia) - test with age < 5 to get 99155
    report_anes = """
        PROCEDURE: Bronchoscopy
        SEDATION: Moderate sedation 45 minutes, administered by anesthesiologist
        PATIENT: 3 year old child
    """
    analysis = engine.analyze_procedure_report(report_anes)
    codes = [c.code for c in analysis.sedation_codes]
    assert "99155" in codes  # Initial by different provider (age < 5)

def test_pleural_procedures():
    """Test pleural procedures with imaging guidance detection"""
    engine = ProcedureCodingEngine()
    
    # Thoracentesis with ultrasound
    report_us = """
        PROCEDURE: Thoracentesis
        TECHNIQUE: Ultrasound guided needle aspiration of left pleural effusion
    """
    analysis = engine.analyze_procedure_report(report_us)
    codes = [c.code for c in analysis.primary_codes]
    assert "32555" in codes  # With imaging
    
    # Thoracentesis without imaging
    report_no_img = """
        PROCEDURE: Thoracentesis
        TECHNIQUE: Needle aspiration of pleural fluid
    """
    analysis = engine.analyze_procedure_report(report_no_img)
    codes = [c.code for c in analysis.primary_codes]
    assert "32554" in codes  # Without imaging

def test_ncci_warnings():
    """Test NCCI edit warnings"""
    engine = ProcedureCodingEngine()
    
    report = """
        PROCEDURE: Diagnostic bronchoscopy with EBUS-TBNA
        Performed diagnostic bronchoscopy (31622) followed by EBUS sampling
        Stations: 4R, 7, 11L
    """
    analysis = engine.analyze_procedure_report(report)
    assert any("31622" in warning for warning in analysis.warnings)

def test_documentation_gaps():
    """Test documentation gap detection"""
    engine = ProcedureCodingEngine()
    
    report = """
        PROCEDURE: EBUS-TBNA with moderate sedation
        Sampled mediastinal nodes
        Sedation provided
    """
    analysis = engine.analyze_procedure_report(report)
    # Should flag missing station details
    assert any("station" in gap.lower() for gap in analysis.missing_documentation)
    # Should flag missing sedation times
    assert any("sedation" in gap.lower() and "time" in gap.lower() 
              for gap in analysis.missing_documentation)