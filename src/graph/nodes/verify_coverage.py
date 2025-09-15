from __future__ import annotations
from ..state import IPState
import re

FACET_SYNONYMS = {"valve":["valve","endobronchial valve","ebv","zephyr","spiration"],
                  "coil":["coil","endobronchial coil","lvrc"]}

def facet_regex(facet: str) -> re.Pattern:
    f = facet.lower().replace("-", "[-\\s]?")
    return re.compile(r'\b' + re.escape(f).replace("\\[","[").replace("\\]","]") + r'\b', re.I)

def _facet_hit(facet: str, hit) -> bool:
    text = (hit.get("text") or hit.get("payload",{}).get("text","")).lower()
    if re.search(facet_regex(facet), text): return True
    for syn in FACET_SYNONYMS.get(facet.lower(), []):
        if re.search(facet_regex(syn), text): return True
    return False

def verify_coverage_node(state: IPState) -> IPState:
    needed = state.get("facets_needed", []) or state.get("plan",{}).get("facets", [])
    hits   = state.get("retrieved_chunks", [])
    covered = {f for f in needed if any(_facet_hit(f, h) for h in hits)}
    state["missing_facets"] = [f for f in needed if f not in covered]
    state["facets_covered"] = sorted(list(covered))
    return state