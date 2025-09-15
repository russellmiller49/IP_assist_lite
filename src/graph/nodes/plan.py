from __future__ import annotations
from ..state import IPState
from ...llm.planner import plan as plan_llm

def plan_node(state: IPState) -> IPState:
    res = plan_llm(state["query"])
    state["plan"] = res["plan"]
    state["facets_needed"] = res["plan"].get("facets", [])
    return state