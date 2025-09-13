"""Mini-prompt parser for extracting procedural facts."""

from dataclasses import dataclass, field
import re
from typing import Dict, List, Optional

@dataclass
class ParsedFacts:
    """Extracted facts from mini-prompt."""
    proc_key: str
    tokens: Dict[str, str] = field(default_factory=dict)
    targets: List[Dict] = field(default_factory=list)  # lobes/stations/nodules
    adjuncts: Dict[str, bool] = field(default_factory=dict)
    complications: Dict[str, str] = field(default_factory=dict)

# Procedure detection patterns
ION_RE = re.compile(r"\bion\b", re.I)
MONARCH_RE = re.compile(r"\bmonarch\b", re.I)
ENB_RE = re.compile(r"\benb\b", re.I)
EBUS_RE = re.compile(r"\bebus\b", re.I)
PDT_RE = re.compile(r"\b(pdt|percutaneous.*dilatational.*tracheostomy)\b", re.I)
ABLATION_RE = re.compile(r"\b(microwave|mwa|rfa|cryo.*ablation|pef|ire)\b", re.I)
PLEURODESIS_RE = re.compile(r"\b(talc|pleurodesis)\b", re.I)
IPC_RE = re.compile(r"\b(ipc|pleural.*catheter)\b", re.I)
FOREIGN_BODY_RE = re.compile(r"\bforeign.*body\b", re.I)

# Imaging patterns
CBCT_RE = re.compile(r"\b(cbct|cios\s*spin|3d\s*spin)\b", re.I)
REBUS_RE = re.compile(r"\b(radial\s*ebus|r[-\s]*ebus|rebus)\b", re.I)
FLUORO_RE = re.compile(r"\bfluoro", re.I)
DTS_RE = re.compile(r"\b(digital\s*tomosynthesis|dts)\b", re.I)

# Sampling patterns
GAUGE_RE = re.compile(r"\b(19|21|22|23|25)\s*G\b", re.I)
PASSES_RE = re.compile(r"(\d+)\s*(?:needle\s*)?passes\b", re.I)
CRYO_PASSES_RE = re.compile(r"cryo(?:biopsy)?\s*[x×]\s*(\d+)", re.I)
FREEZE_RE = re.compile(r"(?:freeze|freezes?)\s*(\d+)\s*(?:s|sec)", re.I)
PROBE_SIZE_RE = re.compile(r"(\d+\.?\d*)\s*mm\s*(?:cryo)?probe", re.I)

# Anatomical patterns
STATIONS_RE = re.compile(r"\b(2[LR]|3[ap]?|4[LR]|5|6|7|8|9|10[LR]?|11[LR]?|12[LR]?|13[LR]?|14[LR]?)\b")
LOBE_RE = re.compile(r"\b(RUL|RML|RLL|LUL|Lingula|LLL)\b", re.I)
SEGMENT_RE = re.compile(r"\b(RB\d+|LB\d+|anterior|posterior|apical|basal|lateral|medial|superior)\b", re.I)

# Clinical patterns
ROSE_RE = re.compile(r"ROSE\s*[:=-]?\s*(positive|adequate|suspicious|negative|non-?diagnostic)", re.I)
BLEEDING_RE = re.compile(r"(minimal|minor|moderate|brisk|massive)\s*bleed", re.I)
PTX_RE = re.compile(r"(pneumothorax|ptx)", re.I)
EBL_RE = re.compile(r"ebl\s*[:=-]?\s*(\d+|minimal|<\s*\d+)", re.I)

# Anesthesia patterns
LIDO_RE = re.compile(r"lidocaine.*?(\d+)\s*mg", re.I)
SEDATION_RE = re.compile(r"(moderate|conscious|deep)\s*sedation", re.I)
GA_RE = re.compile(r"(general\s*anesthesia|GA|ETT|LMA)", re.I)

def parse_miniprompt(text: str) -> ParsedFacts:
    """Extract structured facts from mini-prompt text."""
    t = text.strip()
    
    # Determine procedure key
    proc_key = _detect_procedure(t)
    
    # Extract tokens
    tokens = _extract_tokens(t)
    
    # Extract targets (anatomical locations)
    targets = _extract_targets(t)
    
    # Extract adjuncts (imaging/tools)
    adjuncts = _extract_adjuncts(t)
    
    # Extract complications
    complications = _extract_complications(t)
    
    return ParsedFacts(
        proc_key=proc_key,
        tokens=tokens,
        targets=targets,
        adjuncts=adjuncts,
        complications=complications
    )

def _detect_procedure(text: str) -> str:
    """Detect primary procedure from text."""
    if PDT_RE.search(text):
        return "pdt"
    elif PLEURODESIS_RE.search(text):
        return "talc_pleurodesis"
    elif IPC_RE.search(text) and "fibrinolysis" in text.lower():
        return "ipc_fibrinolysis"
    elif FOREIGN_BODY_RE.search(text):
        return "rigid_foreign_body"
    elif ABLATION_RE.search(text):
        if "microwave" in text.lower() or "mwa" in text.lower():
            return "tma_mwa"
        elif "cryo" in text.lower() and "therapy" in text.lower():
            return "therapeutic_cryo_airway"
        else:
            return "bronch_nodule_ablation_generic"
    elif ION_RE.search(text):
        return "robotic_ion"
    elif MONARCH_RE.search(text):
        return "robotic_monarch"
    elif ENB_RE.search(text):
        return "enb_rebus_fluoro"
    elif "staging" in text.lower() and (EBUS_RE.search(text) or STATIONS_RE.search(text)):
        return "ebus_systematic_staging_ett"
    elif EBUS_RE.search(text):
        return "targeted_ebus_ett"
    else:
        return "standard_bronchoscopy_optional_ebus_lma"

def _extract_tokens(text: str) -> Dict[str, str]:
    """Extract procedural tokens from text."""
    tokens = {}
    
    # Gauge
    if m := GAUGE_RE.search(text):
        tokens["tbna_gauge"] = m.group(1)
    
    # Passes
    if m := PASSES_RE.search(text):
        tokens["tbna_passes"] = m.group(1)
    
    # Cryobiopsy
    if m := CRYO_PASSES_RE.search(text):
        tokens["cryo_passes"] = m.group(1)
    if m := FREEZE_RE.search(text):
        tokens["cryo_freeze_s"] = m.group(1)
    if m := PROBE_SIZE_RE.search(text):
        tokens["cryo_probe_mm"] = m.group(1)
    
    # ROSE
    if m := ROSE_RE.search(text):
        tokens["rose"] = m.group(1).lower()
    
    # Anesthesia
    if m := LIDO_RE.search(text):
        tokens["lido_mg"] = m.group(1)
    if GA_RE.search(text):
        tokens["anesthesia"] = "general"
    elif SEDATION_RE.search(text):
        tokens["anesthesia"] = "moderate"
    
    # EBL
    if m := EBL_RE.search(text):
        tokens["ebl"] = m.group(1)
    
    return tokens

def _extract_targets(text: str) -> List[Dict]:
    """Extract anatomical targets from text."""
    targets = []
    
    # Stations
    for station in STATIONS_RE.findall(text):
        targets.append({"type": "station", "id": station})
    
    # Lobes
    for lobe in LOBE_RE.findall(text):
        targets.append({"type": "lobe", "id": lobe.upper()})
    
    # Segments
    for segment in SEGMENT_RE.findall(text):
        targets.append({"type": "segment", "id": segment})
    
    return targets

def _extract_adjuncts(text: str) -> Dict[str, bool]:
    """Extract imaging and tool adjuncts."""
    return {
        "cbct": bool(CBCT_RE.search(text)),
        "rebus": bool(REBUS_RE.search(text)),
        "fluoro": bool(FLUORO_RE.search(text)),
        "dts": bool(DTS_RE.search(text)),
        "rose": bool(ROSE_RE.search(text))
    }

def _extract_complications(text: str) -> Dict[str, str]:
    """Extract complications from text."""
    complications = {}
    
    # Bleeding
    if m := BLEEDING_RE.search(text):
        complications["bleeding"] = m.group(1)
    elif "no bleeding" in text.lower() or "minimal bleeding" in text.lower():
        complications["bleeding"] = "minimal"
    
    # Pneumothorax
    if PTX_RE.search(text):
        if "no ptx" in text.lower() or "no pneumothorax" in text.lower():
            complications["pneumothorax"] = "none"
        else:
            complications["pneumothorax"] = "present"
    
    # General complications
    if "no complications" in text.lower():
        complications["general"] = "none"
    
    return complications