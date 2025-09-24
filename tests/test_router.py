from src.retrieval.router import choose_store
def test_router_safety_override():
    d = choose_store("Exact dose for bleeding control in RB7?")
    assert d.store == "chunks"
def test_router_complication():
    d = choose_store("List major complications of valve placement")
    assert d.store == "chunks"