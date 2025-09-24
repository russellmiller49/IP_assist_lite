from src.graph.nodes.verify_coverage import _facet_hit
def test_rb_boundary_match():
    assert not _facet_hit("RB7", {"text":"Findings in RB70 segment"})
    assert _facet_hit("RB7", {"text":"EBUS was performed in RB7."})