"""Hybrid extraction: regex baseline + optional LLM, with error handling."""

import re
from datetime import datetime
from typing import Dict, List, Optional, Set
from .schema import Case, Sedation, PerformedItem, SampleTarget, StructureType
from .kb import CodingKB
from .patterns import PATTERNS, LOBE_MAP

def _parse_hhmm(s: str) -> Optional[datetime]:
    for fmt in ("%H:%M", "%I:%M%p", "%I:%M %p"):
        try: return datetime.strptime(s.strip(), fmt)
        except Exception: pass
    return None

def _stations(text: str) -> List[str]:
    out = set()
    for m in PATTERNS['lymph_stations'].finditer(text):
        val = m.group('station') or m.group('station2') or m.group('station3') or m.group('station4')
        if val:
            cleaned = re.sub(r'[^0-9RLrl]', '', val).upper()
            if cleaned:
                out.add(cleaned)
    return sorted(out)

def _lobes(text: str) -> List[str]:
    out = set()
    for m in PATTERNS['lobes'].findall(text):
        key = m.lower().strip()
        if key in LOBE_MAP: out.add(LOBE_MAP[key])
    return sorted(out)

def extract_case(report_text: str, kb: CodingKB, llm=None) -> Case:
    """Extract with error handling and optional LLM enrichment."""
    try:
        text = report_text.strip()
        case = Case(report_text=text)

        # Sedation
        if PATTERNS['moderate_sedation'].search(text):
            minutes = None
            mm = PATTERNS['sedation_minutes'].search(text)
            if mm:
                for g in mm.groups():
                    if g and g.isdigit():
                        minutes = int(g); break
            start = end = None
            tt = PATTERNS['hhmm_times'].search(text)
            if tt:
                start, end = _parse_hhmm(tt.group(1)), _parse_hhmm(tt.group(2))
                if start and end and minutes is None:
                    minutes = max(0, int((end - start).total_seconds() // 60))
            observer = bool(re.search(r'\b(independent|trained).{0,10}observer|\bRN\b|\bnurse\b', text, re.I))
            diff_provider = bool(re.search(r'\b(anesthesi|crna)\w*\b', text, re.I))
            case.sedation = Sedation(
                provided_by_proceduralist=not diff_provider,
                start_time=start, end_time=end, total_minutes=minutes,
                independent_observer_documented=observer
            )

        # Targets with StructureType enum
        for st in _stations(text):
            case.targets.append(SampleTarget(site=st, structure_type=StructureType.STATION))
        for lb in _lobes(text):
            case.targets.append(SampleTarget(
                site=lb,
                structure_type=StructureType.LOBE,
                laterality=("right" if lb.startswith("R") else ("left" if lb.startswith("L") else None))
            ))

        # Procedures via patterns & KB synonyms
        lower = text.lower()
        def add(proc_id: str, details: Dict[str,str] = {}):
            if not any(i.proc_id == proc_id for i in case.items):
                case.items.append(PerformedItem(proc_id=proc_id, details=details))

        for p in kb.iter_procs():
            for syn in p.get("synonyms", []):
                if syn.lower() in lower: add(p["id"])

        if PATTERNS['ebus'].search(text) and PATTERNS['tbna'].search(text): add("ebus_tbna")
        elif PATTERNS['ebus'].search(text): add("ebus_without_tbna", {"technique":"radial_or_diagnostic"})
        if PATTERNS['tblb'].search(text): add("tblb_forceps_or_cryo")
        if PATTERNS['navigation'].search(text): add("nav_bronchoscopy")
        if PATTERNS['thoracentesis'].search(text): add("thoracentesis")
        if PATTERNS['chest_tube'].search(text): add("pleural_drainage_catheter_non_tunneled")
        if PATTERNS['pleurx'].search(text): add("ipc_tunneled_pleural_catheter")
        if PATTERNS['chartis'].search(text): add("chartis_assessment")
        if PATTERNS['valves'].search(text): add("endobronchial_valves")
        if PATTERNS['fiducial'].search(text): add("fiducial_markers")
        if PATTERNS['ablation'].search(text):
            if re.search(r'\b(microwave|mwa)\b', text, re.I): add("microwave_ablation_bronchoscopic")
            elif re.search(r'pulsed.?electric', text, re.I): add("transbronchial_ablation_pulsed_electric_field")

        # Optional: enrich with LLM later
        return case
    except Exception as e:
        # Enhanced error handling: return a minimally useful Case with a visible warning
        return Case(report_text=report_text, parsing_warnings=[f"Extraction error: {type(e).__name__}: {e}"])