from __future__ import annotations
from graph.state import IPState
from llm.verifier import verify_answer

def sentence_guard(state: IPState) -> IPState:
    cfg  = state.get("config", {})
    minG = cfg.get("verification", {}).get("min_confidence_supported", 0.70)
    minC = cfg.get("verification", {}).get("min_confidence_critical", 0.90)

    res = verify_answer(state["answer_sentences"], state["retrieved_chunks"], minG, minC)
    state["answer_sentences"]    = res["keep"]
    state["sentence_citations"]  = res["citations"]
    state["sentence_confidences"]= res["confidences"]
    state["missing_sentences"]   = res["missing"]
    state["needs_rewrite"]       = len(res["missing"]) > 0
    return state
