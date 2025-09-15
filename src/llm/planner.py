from __future__ import annotations
from typing import Dict, Any
from .plan_utils import extract_entities, anonymize, deanonymize
from .llm_client import llm_call  # adapt to your client

PLAN_PROMPT = """You are a clinical planner. The user query is anonymized with placeholders (L*, D*, M*, F*, E*).
Return ONLY JSON:
{{
  "steps":[
    {{"name":"retrieve","targets":["..."],"evidence":["RCTs","guidelines","device IFUs"]}},
    {{"name":"compare","criteria":["efficacy","complications","selection criteria"]}},
    {{"name":"decide","notes":["contraindications","special cases"]}}
  ],
  "facets":["..."]
}}
Query: {q}
"""

def plan(query: str) -> Dict[str, Any]:
    mapping = extract_entities(query)
    q_anon  = anonymize(query, mapping)
    out     = llm_call(PLAN_PROMPT.format(q=q_anon), response_format="json")
    def de_list(lst): return [deanonymize(x, mapping) for x in lst]
    out["facets"] = de_list(out.get("facets", []))
    for s in out.get("steps", []):
        if "targets" in s: s["targets"] = de_list(s["targets"])
    return {"plan": out, "mapping": mapping}