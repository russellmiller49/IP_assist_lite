from __future__ import annotations
from langgraph.graph import StateGraph, END
from .state import IPState
from .nodes.plan import plan_node
from .nodes.retrieve import retrieve_node
from .nodes.verify_coverage import verify_coverage_node
from .nodes.answer import answer_node
from .nodes.rewrite import rewrite_node
from .nodes.verify import sentence_guard

graph = StateGraph(IPState)

graph.add_node("Plan", plan_node)
graph.add_node("Retrieve", retrieve_node)
graph.add_node("VerifyCoverage", verify_coverage_node)
graph.add_node("AnswerDraft", answer_node)
graph.add_node("VerifySentences", sentence_guard)
graph.add_node("Rewrite", rewrite_node)

graph.add_edge("Plan", "Retrieve")
graph.add_edge("Retrieve", "VerifyCoverage")

def coverage_router(state: IPState):
    if "replan_count" not in state: state["replan_count"] = 0
    if "max_replans" not in state: state["max_replans"] = state.get("config",{}).get("max_replans",3)
    if state.get("missing_facets") and state["replan_count"] < state["max_replans"]:
        state["replan_count"] += 1
        return "Plan"
    return "AnswerDraft"

graph.add_conditional_edges("VerifyCoverage", coverage_router, {"Plan":"Plan","AnswerDraft":"AnswerDraft"})
graph.add_edge("AnswerDraft", "VerifySentences")

def rewrite_router(state: IPState):
    return "Rewrite" if state.get("needs_rewrite") else END

graph.add_conditional_edges("VerifySentences", rewrite_router, {"Rewrite":"Rewrite", END: END})
graph.add_edge("Rewrite", END)
graph.set_entry_point("Plan")

compiled_graph = graph.compile()