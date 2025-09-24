from src.reporter import parse_prompt

PROMPT = ("Ion robotic bronchoscopy via ETT, RLL anterior segment, CBCT confirmation, "
          "23G TBNA x5 ROSE positive, 1.1mm cryo x3, minimal bleeding followed by EBUS staging "
          "stations 4R (12mm), 7 (8mm), 11R (15mm), all with 22G x3 passes, ROSE adequate")

def test_core_extraction():
    r = parse_prompt(PROMPT)
    assert r.rb.platform == "Ion"
    assert r.rb.airway == "ETT"
    assert r.rb.anesthesia == "general"
    assert r.rb.target_location.lower().startswith("rll")
    assert r.rb.cbct_tool_in_lesion is True

    tbna = next(x for x in r.rb.lesion_samples if x.modality == "TBNA")
    assert tbna.gauge_or_size == "23G"
    assert tbna.passes == 5
    assert tbna.rose == "positive"

    cryo = next(x for x in r.rb.lesion_samples if x.modality == "Cryobiopsy")
    assert cryo.gauge_or_size == "1.1 mm"
    assert cryo.passes == 3

    assert r.complications.bleeding == "minimal"

    assert r.ebus.performed is True
    assert len(r.ebus.samples) == 3
    stations = {s.station: s for s in r.ebus.samples}
    assert stations["4R"].short_axis_mm == 12
    assert stations["7"].short_axis_mm == 8
    assert stations["11R"].short_axis_mm == 15
    for s in stations.values():
        assert s.needle_gauge == "22G"
        assert s.passes == 3
        assert s.rose == "adequate"