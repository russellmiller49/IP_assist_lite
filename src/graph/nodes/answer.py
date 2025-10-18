from __future__ import annotations
from graph.state import IPState
from llm.llm_client import llm_call

ANSWER_PROMPT = """Using ONLY the retrieved evidence, answer the question in short declarative sentences.
End each sentence with [CHUNK_ID].
Question: {q}
Evidence:
{chunks}
"""

def _pack_chunks(chunks):
    return "\n".join(f"[{c['id']}] {c['text']}" for c in chunks[:8])

def answer_node(state: IPState) -> IPState:
    txt = llm_call(ANSWER_PROMPT.format(q=state["query"], chunks=_pack_chunks(state["retrieved_chunks"])))
    state["answer_sentences"] = [s.strip() for s in txt.split("\n") if s.strip()]
    return state
