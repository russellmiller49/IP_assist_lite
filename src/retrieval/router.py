from __future__ import annotations
import re
from dataclasses import dataclass

@dataclass
class RouterDecision: store: str; confidence: float

SAFETY_TERMS = r'\b(bleeding|hemorrhage|haemorrhage|massive hemoptysis|death|fatal|emergency|urgent|contraindication|contraindicated|pneumothorax|perforation|air embolism)\b'
SPEC_TERMS   = r'\b(dose|dosage|protocol|technique|energy|w(?:att)?s?|mm|gauge|fr|french)\b'
OVERVIEW     = r'\b(overview|summary|recap|compare|versus|vs)\b'

def choose_store(q: str) -> RouterDecision:
    qn = q.strip().lower()
    if re.search(SAFETY_TERMS, qn, re.I): return RouterDecision("chunks", 0.95)
    if re.search(SPEC_TERMS, qn, re.I):
        if re.search(r'\b(use|administer|apply|perform|select|choose)\b', qn):
            return RouterDecision("chunks", 0.85)
        return RouterDecision("quotes", 0.80)
    if re.search(OVERVIEW, qn, re.I): return RouterDecision("summaries", 0.70)
    if len(q.split()) <= 8 or '"' in q or "exact" in qn or re.search(r'\bwhat did .* say\b', qn):
        return RouterDecision("quotes", 0.70)
    return RouterDecision("chunks", 0.60)