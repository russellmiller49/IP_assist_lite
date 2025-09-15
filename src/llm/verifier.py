from __future__ import annotations
from typing import List, Dict, Any
from .llm_client import llm_call
import re

VERIFY_PROMPT = """Answer (numbered sentences):
{answer}

You are given retrieved chunks in the form [ID] text...
For EACH sentence number return:
- the single best supporting chunk ID, or MISSING
- a confidence score in [0,1]
Return JSON: {{"map": {{"1": {{"chunk_id":"C12","confidence":0.92}}}}}}
Chunks:
{chunks}
"""

CRITICAL_PATTERNS = [
    r'\b(contraindicat(?:ed|ion))\b', r'\b(fatal|death|hemorrhage|haemorrhage|perforation|tamponade|cardiac arrest)\b',
    r'\b(do not|never|must not|avoid)\b', r'\b(\d+\s*(?:mg|mcg|µg|ml|units?))\b'
]

def number_sentences(sentences: List[str]) -> str:
    return "\n".join(f"{i+1}. {s}" for i, s in enumerate(sentences))

def format_chunks(chunks: List[Dict[str,Any]]) -> str:
    return "\n".join(f"[{c['id']}] {c.get('text','')}" for c in chunks)

def is_critical(sentence: str) -> bool:
    return any(re.search(p, sentence, re.I) for p in CRITICAL_PATTERNS)

def verify_answer(sentences: List[str], chunks: List[Dict[str,Any]],
                  min_conf_general: float = 0.70, min_conf_critical: float = 0.90):
    out = llm_call(VERIFY_PROMPT.format(
        answer=number_sentences(sentences), chunks=format_chunks(chunks)
    ), response_format="json")
    raw = out.get("map", {})
    keep, cites, confidences, missing = [], [], [], []
    for i, s in enumerate(sentences, start=1):
        rec = raw.get(str(i), {"chunk_id":"MISSING","confidence":0.0})
        cid = rec.get("chunk_id","MISSING")
        conf= float(rec.get("confidence", 0.0))
        required = min_conf_critical if is_critical(s) else min_conf_general
        if cid != "MISSING" and conf >= required:
            keep.append(s); cites.append(cid); confidences.append(conf)
        else:
            missing.append({"sentence": s, "cid": cid, "confidence": conf, "required": required})
    return {"keep": keep, "citations": cites, "confidences": confidences, "missing": missing}