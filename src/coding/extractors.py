"""Hybrid extraction: regex baseline + optional LLM, with error handling."""

import re
from datetime import datetime
from typing import Dict, List, Optional, Set
from .schema import Case, Sedation, PerformedItem, SampleTarget, StructureType
from .kb import CodingKB
from .patterns import PATTERNS, LOBE_MAP, extract_stations

def _parse_hhmm(s: str) -> Optional[datetime]:
    for fmt in ("%H:%M", "%I:%M%p", "%I:%M %p"):
        try: return datetime.strptime(s.strip(), fmt)
        except Exception: pass
    return None

def _stations(text: str) -> List[str]:
    # Use the improved extract_stations function from patterns module
    return sorted(extract_stations(text))

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

        # Sedation - suppress under general anesthesia
        ga_present = bool(PATTERNS['general_anesthesia'].search(text))
        if PATTERNS['moderate_sedation'].search(text) and not ga_present:
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

        # Distinguish between linear EBUS-TBNA and radial EBUS
        # Linear EBUS is used WITH TBNA for mediastinal/hilar nodes
        # Radial EBUS is used for peripheral lesions
        if re.search(r'\bradial\s+(ultrasound|ebus|probe)\b', text, re.I):
            add("radial_ebus_peripheral")
        elif PATTERNS['ebus'].search(text) and PATTERNS['tbna'].search(text):
            # Only code as EBUS-TBNA if it's LINEAR EBUS with TBNA
            # Check for mediastinal/hilar context or explicit linear mention
            if re.search(r'\b(linear|convex|mediastinal|hilar)\b', text, re.I) or \
               re.search(r'\b(station|level)\s*\d+[RLrl]?\b', text, re.I):
                add("ebus_tbna")
            else:
                # TBNA mentioned but not with linear EBUS
                add("transbronchial_needle_aspiration")
        elif PATTERNS['ebus'].search(text):
            add("ebus_without_tbna", {"technique":"radial_or_diagnostic"})
        # Transbronchial lung biopsy (TBLB)
        if PATTERNS['tblb'].search(text) or re.search(r'transbronchial\s+biops', text, re.I):
            add("tblb_forceps_or_cryo")
        
        # Transbronchial needle aspiration (TBNA) - not EBUS-guided
        # Only add if not already added as EBUS-TBNA
        if not any(i.proc_id == "ebus_tbna" for i in case.items):
            if PATTERNS['tbna'].search(text) or re.search(r'transbronchial\s+needle\s+aspiration', text, re.I):
                add("transbronchial_needle_aspiration")
        
        # Bronchial alveolar lavage (BAL)
        if re.search(r'\b(bronchial\s+alveolar\s+lavage|bal\b|broncho.?alveolar)', text, re.I):
            add("bronchial_alveolar_lavage")
        if PATTERNS['navigation'].search(text) or re.search(r'\b(ion\s+(platform|robotic)|robotic\s+navigation)\b', text, re.I):
            add("nav_bronchoscopy")
        if PATTERNS['thoracentesis'].search(text): add("thoracentesis")
        if PATTERNS['chest_tube'].search(text): add("pleural_drainage_catheter_non_tunneled")
        if PATTERNS['pleurx'].search(text): add("ipc_tunneled_pleural_catheter")
        if PATTERNS['chartis'].search(text): add("chartis_assessment")
        if PATTERNS['valves'].search(text): add("endobronchial_valves")
        if PATTERNS['fiducial'].search(text): add("fiducial_markers")
        if PATTERNS['ablation'].search(text):
            if re.search(r'\b(microwave|mwa)\b', text, re.I): add("microwave_ablation_bronchoscopic")
            elif re.search(r'pulsed.?electric', text, re.I): add("transbronchial_ablation_pulsed_electric_field")
        
        # Whole lung lavage detection
        if PATTERNS['whole_lung_lavage'].search(text):
            add("whole_lung_lavage")
        
        # Stent procedures - placement, removal, exchange
        stent_placed = re.search(r'\b(?:stent\s+(?:was\s+)?(?:inserted|deployed|placed|positioned|in\s+\w+)|(?:inserted|deployed|placed|positioned)\s+[\w\s]*?stent)\b', text, re.I)
        stent_removed = re.search(r'\b(?:stent\s+(?:was\s+)?removed?|removal\s+of\s+(?:the\s+)?stent|extract\w*\s+stent)\b', text, re.I)
        stent_exchanged = re.search(r'\b(?:stent\s+(?:was\s+)?(?:exchanged|replaced)|replace\w*\s+stent|stent\s+exchange)\b', text, re.I)
        
        if stent_exchanged:
            add("stent_removal_and_replacement")
        elif stent_removed and not stent_placed:
            add("stent_removal")
        elif stent_placed:
            # Check for negative mentions and contemplation only
            no_stent = re.search(r'\b(no\s+stent|stent\s+not\s+placed|without\s+stent|deferred?\s+stent|considered\s+stent|reluctant\s+to\s+place\s+stent|did\s+not\s+place\s+stent)\b', text, re.I)
            if not no_stent:
                # Determine if tracheal or bronchial
                if PATTERNS['y_stent'].search(text) or (PATTERNS['tracheal_terms'].search(text) and not PATTERNS['bronchial_terms'].search(text)):
                    add("tracheal_stent_insertion")
                else:
                    add("bronchial_stent_insertion")
        
        # Excision vs destruction detection - excision takes precedence
        snare_match = PATTERNS['snare_excision'].search(text) if 'snare_excision' in PATTERNS else None
        ablation_match = PATTERNS['ablation'].search(text) if 'ablation' in PATTERNS else None
        
        # If both snare and specimen mentioned, it's excision
        if snare_match and re.search(r'\b(specimen|pathology|histology)\b', text, re.I):
            add("tumor_excision_bronchoscopic")
        # If just snare mentioned (even with ablation), prefer excision
        elif snare_match:
            add("tumor_excision_bronchoscopic")
        # Only destruction if no excision methods but ablation present
        elif ablation_match and not re.search(r'\b(microwave|mwa|pulsed.?electric)\b', text, re.I):
            add("tumor_destruction_bronchoscopic")
        
        # Dilation detection (only add if no stent procedure already added)
        if PATTERNS['dilation'].search(text):
            stent_procs = ["tracheal_stent_insertion", "bronchial_stent_insertion"]
            if not any(item.proc_id in stent_procs for item in case.items):
                add("airway_dilation_only")

        # Optional: enrich with LLM later
        return case
    except Exception as e:
        # Enhanced error handling: return a minimally useful Case with a visible warning
        return Case(report_text=report_text, parsing_warnings=[f"Extraction error: {type(e).__name__}: {e}"])