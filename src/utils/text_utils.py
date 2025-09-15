from __future__ import annotations
import re
from typing import Dict, List, Any

def extract_temporal_markers(chunks: List[Dict[str,Any]]) -> Dict[str,int]:
    years = []
    for c in chunks:
        years += [int(y) for y in re.findall(r'\b(20\d{2}|19\d{2})\b', (c.get("text") or "").lower())]
    return {"min_year": min(years) if years else None, "max_year": max(years) if years else None}

def deduplicate_chunks(chunks: List[Dict[str,Any]], min_overlap: float=0.5) -> List[Dict[str,Any]]:
    def shingles(s: str):
        s = s or ""
        if len(s) < 50: return {s}
        return { s[i:i+50] for i in range(0, max(len(s)-50,1), 10) }
    kept, seen = [], []
    for c in chunks:
        sh = shingles(c.get("text",""))
        if not any(len(sh & sh2)/max(len(sh),1) >= min_overlap for sh2 in seen):
            kept.append(c); seen.append(sh)
    return kept