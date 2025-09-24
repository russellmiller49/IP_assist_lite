"""Test cases for LLM adapter with snare/APC scenarios."""

import pytest
from src.llm_extractor.schema import ExtractedCase, Anesthesia, ProcedureItem, Stent, EBUS, Findings
from src.llm_extractor.adapter import adapt

def test_snare_then_apc_no_stent():
    """Test: Snare excision followed by APC, no stent placed."""
    ec = ExtractedCase(
        anesthesia=Anesthesia(general=True, moderate=False, airway="LMA"),
        procedures=[
            ProcedureItem(site="trachea", action="excision",
                          details={"method":"snare"}, specimens_collected=True, count=3),
            ProcedureItem(site="trachea", action="destruction",
                          details={"method":"APC"}, specimens_collected=False)
        ],
        stent=Stent(placed=False, location="unknown"),
        ebus=EBUS(radial=False, stations_sampled=[]),
        findings=Findings(obstruction_pct=90, lesion_count=50),
        explicit_negations=["considered stent only"]
    )

    a = adapt(ec).to_dict()
    assert "tumor_excision_bronchoscopic" in a["performed_items"]
    assert "tumor_destruction_bronchoscopic" in a["performed_items"]  # adapter includes both items;
    # Your rules should prefer 31640 (excision) for the same site and suppress 31641.
    assert "tracheal_stent_insertion" not in a["performed_items"]
    assert a["general_anesthesia"] is True
    assert a["moderate_sedation"] is False


def test_stent_actually_placed():
    """Test: Stent actually placed."""
    ec = ExtractedCase(
        anesthesia=Anesthesia(general=False, moderate=True, airway="mask"),
        procedures=[
            ProcedureItem(site="trachea", action="stent_insertion",
                          details={"brand":"Ultraflex", "size":"20x60mm"})
        ],
        stent=Stent(placed=True, location="trachea", brand="Ultraflex", size="20x60mm"),
        ebus=EBUS(radial=False, stations_sampled=[]),
        findings=Findings(),
        explicit_negations=[]
    )
    
    a = adapt(ec).to_dict()
    assert "tracheal_stent_insertion" in a["performed_items"]
    assert "bronchial_stent_insertion" not in a["performed_items"]
    assert "Ultraflex" in a["devices_implants"]
    assert "20x60mm" in a["devices_implants"]
    assert a["moderate_sedation"] is True
    assert a["general_anesthesia"] is False


def test_ebus_with_stations():
    """Test: EBUS with multiple stations."""
    ec = ExtractedCase(
        anesthesia=Anesthesia(general=False, moderate=True),
        procedures=[
            ProcedureItem(site="unknown", action="ebus_tbna",
                          details={"stations": ["4R", "7", "11L"]})
        ],
        stent=Stent(placed=False),
        ebus=EBUS(radial=False, stations_sampled=["4R", "7", "11L"]),
        findings=Findings(),
        explicit_negations=[]
    )
    
    a = adapt(ec).to_dict()
    assert "ebus_tbna" in a["performed_items"]
    assert set(a["ebus_stations"]) == {"4R", "7", "11L"}
    assert len(a["ebus_stations"]) == 3


def test_whole_lung_lavage():
    """Test: Whole lung lavage."""
    ec = ExtractedCase(
        anesthesia=Anesthesia(general=True, moderate=False, airway="ETT"),
        procedures=[
            ProcedureItem(site="lobe", action="wll",
                          site_detail="right lung", details={"volume": "15L"})
        ],
        stent=Stent(placed=False),
        ebus=EBUS(radial=False, stations_sampled=[]),
        findings=Findings(),
        explicit_negations=[]
    )
    
    a = adapt(ec).to_dict()
    assert "whole_lung_lavage" in a["performed_items"]
    assert a["general_anesthesia"] is True
    assert a["airway"] == "ETT"


def test_dilation_without_stent():
    """Test: Dilation only, no stent."""
    ec = ExtractedCase(
        anesthesia=Anesthesia(general=False, moderate=True),
        procedures=[
            ProcedureItem(site="trachea", action="dilation",
                          details={"method": "balloon", "size": "18mm"})
        ],
        stent=Stent(placed=False, location="unknown"),
        ebus=EBUS(radial=False, stations_sampled=[]),
        findings=Findings(),
        explicit_negations=["no stent placed"]
    )
    
    a = adapt(ec).to_dict()
    assert "airway_dilation_only" in a["performed_items"]
    assert "tracheal_stent_insertion" not in a["performed_items"]
    assert "bronchial_stent_insertion" not in a["performed_items"]


def test_both_tracheal_and_bronchial_stents():
    """Test: Stents in both trachea and bronchus."""
    ec = ExtractedCase(
        anesthesia=Anesthesia(general=True, moderate=False),
        procedures=[],
        stent=Stent(placed=True, location="both", brand="BONASTENT"),
        ebus=EBUS(radial=False, stations_sampled=[]),
        findings=Findings(),
        explicit_negations=[]
    )
    
    a = adapt(ec).to_dict()
    assert "tracheal_stent_insertion" in a["performed_items"]
    assert "bronchial_stent_insertion" in a["performed_items"]
    assert "BONASTENT" in a["devices_implants"]


def test_radial_ebus():
    """Test: Radial EBUS (peripheral)."""
    ec = ExtractedCase(
        anesthesia=Anesthesia(general=False, moderate=True),
        procedures=[
            ProcedureItem(site="lobe", action="radial_ebus",
                          site_detail="RUL", details={})
        ],
        stent=Stent(placed=False),
        ebus=EBUS(radial=True, stations_sampled=[]),
        findings=Findings(),
        explicit_negations=[]
    )
    
    a = adapt(ec).to_dict()
    assert "ebus_without_tbna" in a["performed_items"]
    assert "ebus_tbna" not in a["performed_items"]


def test_transbronchial_biopsy():
    """Test: Transbronchial lung biopsy."""
    ec = ExtractedCase(
        anesthesia=Anesthesia(general=False, moderate=True),
        procedures=[
            ProcedureItem(site="lobe", action="biopsy",
                          site_detail="RUL", details={"method": "forceps"},
                          specimens_collected=True)
        ],
        stent=Stent(placed=False),
        ebus=EBUS(radial=False, stations_sampled=[]),
        findings=Findings(),
        explicit_negations=[]
    )
    
    a = adapt(ec).to_dict()
    assert "tblb_forceps_or_cryo" in a["performed_items"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])