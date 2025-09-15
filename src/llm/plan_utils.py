# -*- coding: utf-8 -*-
from __future__ import annotations
import re
from typing import Dict

RB_SEG      = r'\b(?:RB|LB)[-\s]?\d{1,2}\b'
GAUGE       = r'\b(\d{1,2})[-\s]?(?:gauge|g)\b'
MM          = r'\b(\d+(?:\.\d+)?)\s*(?:mm|millimeters?)\b'
FRENCH      = r'\b(\d+(?:\.\d+)?)\s*(?:fr|french)\b'
ENERGY_WATT = r'\b(\d+(?:\.\d+)?)\s*(?:w|watts?)\b'

def extract_entities(q: str) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for pat, tag in [(RB_SEG,'L'),(GAUGE,'D'),(MM,'M'),(FRENCH,'F'),(ENERGY_WATT,'E')]:
        for m in re.finditer(pat, q, flags=re.I):
            t = m.group(0)
            if t not in mapping:
                i = 1 + sum(1 for v in mapping.values() if v.startswith(tag))
                mapping[t] = f"{tag}{i}"
    return mapping

def anonymize(text: str, mapping: Dict[str, str]) -> str:
    for k in sorted(mapping.keys(), key=len, reverse=True):
        text = re.sub(re.escape(k), mapping[k], text)
    return text

def deanonymize(text: str, mapping: Dict[str, str]) -> str:
    inv = {v: k for k, v in mapping.items()}
    for k in sorted(inv.keys(), key=len, reverse=True):
        text = text.replace(k, inv[k])
    return text