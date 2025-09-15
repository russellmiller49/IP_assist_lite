from __future__ import annotations
import re
EMERGENCY_PATTERNS = [r'\b(massive\s+hemoptysis|tension\s+pneumothorax|air\s+embolism)\b',
                      r'\b(cardiac\s+arrest|respiratory\s+failure)\b',
                      r'\b(emergency|urgent|stat|immediate)\b']
def is_emergency(q: str) -> bool:
    return any(re.search(p, q, re.I) for p in EMERGENCY_PATTERNS)