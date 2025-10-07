from __future__ import annotations
import re
from typing import List, Tuple, Optional

NUM_UNIT = re.compile(r'(\d+(?:\.\d+)?)\s*(mm|cm|fr|french|g|gauge|w|watts?)\b', re.I)
RANGE    = re.compile(r'(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*(mm|cm|fr|french|g|gauge|w|watts?)\b', re.I)

GAUGE_OD_MM = {14:2.108,16:1.651,17:1.473,18:1.270,19:1.067,20:0.908,21:0.819,22:0.711,23:0.635,25:0.515}
GAUGE_ID_MM = {18:0.838,19:0.686,20:0.603,21:0.514,22:0.413,23:0.337,25:0.260}

def _unit_norm(u: str) -> str: return {"watts":"w","watt":"w","gauge":"g","french":"fr"}.get(u.lower(), u.lower())

def _extract_all(s: str) -> List[Tuple[float,str]]:
    out = []
    # Extract ranges first
    for a, b, u in RANGE.findall(s):
        out.append((float(a), u))
        out.append((float(b), u))
    # Then extract single numbers
    out += [(float(n),u) for n,u in NUM_UNIT.findall(s)]
    return out

def _to_mm(value: float, unit: str, context_hint: str = "") -> Optional[float]:
    unit = _unit_norm(unit)
    if unit == "mm": return value
    if unit == "cm": return value * 10.0
    if unit == "fr": return value * 0.333
    if unit == "g":
        g = int(round(value))
        return GAUGE_ID_MM.get(g) if ("inner" in context_hint or "lumen" in context_hint) else GAUGE_OD_MM.get(g)
    return None

def _close(a: float, b: float, tol_pct: float) -> bool:
    denom = max(b, 1e-9); return abs(a - b) / denom <= tol_pct / 100.0

def numeric_ok(pred: str, gold: str, tol_pct: float=5.0, allow_gauge_off_by_one: bool=True, context_hint: str="") -> bool:
    pred_vals, gold_vals = _extract_all(pred), _extract_all(gold)
    if not gold_vals: return True
    
    # Check if gold contains ranges and pred contains single values
    gold_ranges = RANGE.findall(gold)
    pred_ranges = RANGE.findall(pred)
    
    for g_n, g_u in gold_vals:
        g_un = _unit_norm(g_u)
        
        # Check if this gold value is part of a range
        is_in_range = any(float(a) <= g_n <= float(b) and _unit_norm(u) == g_un 
                         for a, b, u in gold_ranges)
        
        if g_un == "g":
            found = any((_unit_norm(pu)=="g" and abs(round(pn)-round(g_n)) <= (1 if allow_gauge_off_by_one else 0)) for pn,pu in pred_vals)
            if not found:
                g_mm = _to_mm(g_n, "g", context_hint)
                if not (g_mm and any((pm := _to_mm(pn, pu, context_hint)) is not None and _close(pm, g_mm, tol_pct) for pn,pu in pred_vals)):
                    return False
            continue
            
        g_mm = _to_mm(g_n, g_un, context_hint)
        if g_mm is not None:
            # If gold is in a range, check if any pred value falls within the range
            if is_in_range:
                range_match = any((pm := _to_mm(pn, pu, context_hint)) is not None and 
                                 any(float(a) * (10 if _unit_norm(u) == "cm" else 1) <= pm <= float(b) * (10 if _unit_norm(u) == "cm" else 1)
                                     for a, b, u in gold_ranges if _unit_norm(u) == g_un)
                                 for pn, pu in pred_vals)
                if not range_match:
                    return False
            else:
                if not any((pm := _to_mm(pn, pu, context_hint)) is not None and _close(pm, g_mm, tol_pct) for pn,pu in pred_vals):
                    return False
        elif g_un in {"w"}:
            if not any((_unit_norm(pu)=="w" and _close(pn, g_n, tol_pct)) for pn,pu in pred_vals):
                return False
        else:
            if not any((_unit_norm(pu)==g_un and _close(pn, g_n, tol_pct)) for pn,pu in pred_vals):
                return False
    return True