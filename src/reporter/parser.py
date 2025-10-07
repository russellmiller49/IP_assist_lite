import re
from typing import List
from .schema import (
    ReporterParseResult, RoboticBronchoscopy, EBUSStaging, Complications,
    LesionSampling, EBUSStationSample
)

# Precompiled patterns for speed/reliability
RE_AIRWAY = re.compile(r"\bvia\s+(ETT|LMA|Laryngeal mask|Mask|Nasal\s+cannula)\b", re.I)
RE_RLL_SEGMENT = re.compile(r"\b(RLL|RUL|RML|LLL|LUL)\s+([a-z\- ]*segment)\b", re.I)
RE_CBCT = re.compile(r"\bCBCT\b|\bcone[-\s]?beam\b", re.I)
RE_TBNA = re.compile(r"\b(\d{2}G)\s*TBNA\s*x\s*(\d+)\b", re.I)
RE_CRYO = re.compile(r"\b([\d.]+)\s*mm\s*cryo\s*x\s*(\d+)\b", re.I)
RE_ROSE_POS = re.compile(r"\bROSE\s+(positive|adequate|negative|atypical)\b", re.I)

# EBUS block: stations like "4R (12mm), 7 (8mm), 11R (15mm)" and common suffix "all with 22G x3 passes"
RE_EBUS_LIST = re.compile(r"stations?\s+([0-9R L,()]+mm[^,]*(?:,\s*[0-9R L,()]+mm[^,]*)*)", re.I)
RE_STATION = re.compile(r"(\d{1,2}[RL]?)(?:\s*\((\d+)\s*mm\))?", re.I)
RE_EBUS_NEEDLE_PASSES = re.compile(r"\b(all\s+with\s+)?(\d{2}G)\s*x\s*(\d+)\s*passes?\b", re.I)

RE_MINIMAL_BLEED = re.compile(r"\bminimal\s+bleeding\b", re.I)

def _safe_lower(s: str) -> str:
    return s.lower()

def parse_prompt(prompt: str) -> ReporterParseResult:
    text = " ".join(prompt.split())
    lower = _safe_lower(text)

    # Robotic bronchoscopy core
    rb = RoboticBronchoscopy()
    rb.platform = "Ion" if "ion" in lower else rb.platform

    # Airway & anesthesia inference
    airway_m = RE_AIRWAY.search(text)
    if airway_m:
        airway_raw = airway_m.group(1).upper().replace(" LARYNGEAL MASK", "LMA")
        rb.airway = "ETT" if "ETT" in airway_raw else ("LMA" if "LMA" in airway_raw else "Mask")
        if rb.airway == "ETT":
            rb.anesthesia = "general"

    # Target location (keep it free text for reliability)
    seg = RE_RLL_SEGMENT.search(text)
    if seg:
        rb.target_location = f"{seg.group(1).upper()} {seg.group(2).lower()}"

    # CBCT confirmation
    if RE_CBCT.search(text):
        rb.cbct_tool_in_lesion = True

    # Lesion sampling modalities
    # TBNA
    tbna = RE_TBNA.search(text)
    if tbna:
        rb.lesion_samples.append(
            LesionSampling(modality="TBNA", gauge_or_size=tbna.group(1).upper(), passes=int(tbna.group(2)), rose="not documented")
        )
    # Cryo
    cryo = RE_CRYO.search(text)
    if cryo:
        rb.lesion_samples.append(
            LesionSampling(modality="Cryobiopsy", gauge_or_size=f"{cryo.group(1)} mm", passes=int(cryo.group(2)), rose="not documented")
        )

    # ROSE near the lesion sampling part
    rose_all = list(RE_ROSE_POS.finditer(text))
    # Heuristic: the first ROSE mention applies to lesion; the last one after EBUS likely applies to EBUS
    rose_lesion = rose_all[0].group(1).lower() if rose_all else "not documented"
    rose_ebus = rose_all[-1].group(1).lower() if len(rose_all) > 1 else rose_lesion
    # Attach lesion ROSE to all lesion modalities if not already set
    for s in rb.lesion_samples:
        if s.rose == "not documented":
            s.rose = rose_lesion

    # EBUS staging
    ebus = EBUSStaging(performed=("ebus" in lower))
    # Pull station list with sizes
    stn_block = RE_EBUS_LIST.search(text)
    stations: List[EBUSStationSample] = []
    if stn_block:
        for stn, size in RE_STATION.findall(stn_block.group(1)):
            size_mm = int(size) if size else None
            stations.append(EBUSStationSample(station=stn.upper(), short_axis_mm=size_mm))
    # Common needle/passes descriptor
    np_m = RE_EBUS_NEEDLE_PASSES.search(text)
    common_gauge, common_passes = None, None
    if np_m:
        common_gauge = np_m.group(2).upper()
        common_passes = int(np_m.group(3))
    for s in stations:
        s.needle_gauge = common_gauge
        s.passes = common_passes
        s.rose = rose_ebus if rose_ebus else "not documented"
    if stations:
        ebus.samples = stations

    # Complications
    comp = Complications()
    if RE_MINIMAL_BLEED.search(text):
        comp.bleeding = "minimal"

    # Data quality checks
    warnings = []
    if not rb.target_location:
        warnings.append("Target location not documented.")
    if not rb.lesion_samples:
        warnings.append("Lesion sampling details not documented.")
    if ebus.performed and not ebus.samples:
        warnings.append("EBUS mentioned but no stations parsed.")
    if rb.cbct_tool_in_lesion is False and "cbct" in lower:
        # Should be true if CBCT is present; handled already above
        pass

    return ReporterParseResult(
        rb=rb,
        ebus=ebus,
        complications=comp,
        rose_summary_lesion=rose_lesion,
        rose_summary_ebus=rose_ebus,
        data_warnings=warnings
    )