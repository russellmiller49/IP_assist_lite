from __future__ import annotations
from ..state import IPState
from ...llm.llm_client import llm_call

REWRITE_PROMPT = """Some sentences lacked support:
{missing}
Rewrite ONLY those using the evidence, or drop if unsupported. Return numbered short sentences.
Evidence:
{chunks}
"""

def rewrite_node(state: IPState) -> IPState:
    missing_list = [m["sentence"] for m in state.get("missing_sentences",[])]
    if not missing_list: return state
    evidence = "\n".join(f"[{c['id']}] {c['text']}" for c in state["retrieved_chunks"][:8])
    out = llm_call(REWRITE_PROMPT.format(missing="\n".join(missing_list), chunks=evidence))
    state["answer_sentences"] = [s.strip() for s in out.split("\n") if s.strip()]
    state["needs_rewrite"] = False
    return state