"""Synoptic report generator with RCS-18 compliance."""

from typing import Dict, List, Optional
import json
from string import Template
from .parser import parse_miniprompt, ParsedFacts
from .blocks import (
    PRE_PROCEDURE_CHECKLIST,
    ANESTHESIA_SEDATION_STANDARD,
    COMPLICATIONS_CHECKLIST,
    POST_PROCEDURE_STANDARD,
    SPECIMEN_HANDLING,
    NAVIGATION_GUIDANCE,
    ABLATION_PARAMETERS,
    PDT_GUIDANCE,
    PLEURAL_PROCEDURE,
    create_rcs18_compliant_header,
    create_signature_block,
    SynopticReportBuilder
)

# Load templates
def load_templates() -> Dict[str, str]:
    """Load procedure templates from JSON."""
    import os
    template_path = os.path.join(
        os.path.dirname(__file__), 
        '../../data/ip_templates.json'
    )
    try:
        with open(template_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

PROCEDURE_TEMPLATES = load_templates()

def render_report(miniprompt: str, patient_ctx: Optional[Dict] = None) -> Dict:
    """Generate synoptic report from mini-prompt.
    
    Args:
        miniprompt: Brief procedure description
        patient_ctx: Patient demographics and context
        
    Returns:
        Dict with text report, procedure key, and parsed facts
    """
    if patient_ctx is None:
        patient_ctx = _default_patient_context()
    
    # Parse the mini-prompt
    parsed = parse_miniprompt(miniprompt)
    
    # Build report using SynopticReportBuilder
    builder = SynopticReportBuilder()
    
    # Add RCS-18 compliant header
    header = create_rcs18_compliant_header(
        patient_name=patient_ctx.get("patient_name", "[Name]"),
        dod_id=patient_ctx.get("dod_id", "[DoD ID]"),
        procedure_date=patient_ctx.get("date", "[Date]"),
        location=patient_ctx.get("location", "[Location]"),
        procedure_type=_get_procedure_name(parsed.proc_key),
        elective_emergency=patient_ctx.get("elective_emergency", "Elective")
    )
    builder.sections.append(header)
    
    # Add pre-procedure checklist (RCS-18)
    pre_data = {
        "anticoagulation_plan": patient_ctx.get("anticoagulation_plan", "Per protocol"),
        "asa": patient_ctx.get("asa", "II"),
        "airway_assessment": patient_ctx.get("airway_assessment", "Normal")
    }
    builder.add_block(PRE_PROCEDURE_CHECKLIST, pre_data)
    
    # Add anesthesia block
    anesthesia_data = _build_anesthesia_data(parsed, patient_ctx)
    builder.add_block(ANESTHESIA_SEDATION_STANDARD, anesthesia_data)
    
    # Add procedure-specific sections
    body_sections = _build_procedure_body(parsed, miniprompt, patient_ctx)
    for section in body_sections:
        builder.sections.append(section)
    
    # Add specimen handling if applicable
    if parsed.adjuncts.get("rose") or any("biopsy" in str(t) for t in parsed.targets):
        specimen_data = _build_specimen_data(parsed, patient_ctx)
        builder.add_block(SPECIMEN_HANDLING, specimen_data)
    
    # Add complications
    comp_data = _build_complications_data(parsed, patient_ctx)
    builder.add_block(COMPLICATIONS_CHECKLIST, comp_data)
    
    # Add post-procedure
    post_data = _build_post_procedure_data(parsed, patient_ctx)
    builder.add_block(POST_PROCEDURE_STANDARD, post_data)
    
    # Add signature block
    signature = create_signature_block(
        physician_name=patient_ctx.get("physician_name", "[Physician Name]"),
        physician_title=patient_ctx.get("physician_title", "MD"),
        datetime_str=patient_ctx.get("datetime", "[DateTime]")
    )
    builder.sections.append(signature)
    
    # Add brief narrative paragraph for nuance
    narrative = _create_narrative_summary(parsed, miniprompt)
    builder.add_narrative(narrative)
    
    # Build final report
    report_text = builder.build()
    
    return {
        "text": report_text,
        "proc_key": parsed.proc_key,
        "parsed": parsed,
        "patient_ctx": patient_ctx
    }

def _build_procedure_body(parsed: ParsedFacts, miniprompt: str, ctx: Dict) -> List[str]:
    """Build procedure-specific body sections."""
    sections = []
    
    # Try to use template if available
    if parsed.proc_key in PROCEDURE_TEMPLATES:
        template_text = PROCEDURE_TEMPLATES[parsed.proc_key]
        template_data = _extract_template_data(parsed, ctx)
        filled_template = Template(template_text).safe_substitute(template_data)
        sections.append(filled_template)
    
    # Add procedure-specific blocks
    if parsed.proc_key.startswith("robotic_"):
        if parsed.adjuncts.get("cbct"):
            sections.append(_build_navigation_section(parsed, ctx))
        if "ablation" in miniprompt.lower():
            sections.append(_build_ablation_section(parsed, ctx))
    
    elif parsed.proc_key.startswith("ebus_"):
        sections.append(_build_ebus_section(parsed, ctx))
    
    elif parsed.proc_key == "pdt":
        sections.append(_build_pdt_section(parsed, ctx))
    
    elif "pleural" in parsed.proc_key or "talc" in parsed.proc_key:
        sections.append(_build_pleural_section(parsed, ctx))
    
    return sections

def _build_ebus_section(parsed: ParsedFacts, ctx: Dict) -> str:
    """Build EBUS section with elastography table."""
    table_header = """
EBUS Systematic Staging
| Station | Size (mm) | Shape | Margin | Echo | CHS | CNS | Doppler | Elastography | Sampled | Passes | Gauge | ROSE |
|---------|-----------|--------|---------|------|-----|-----|---------|--------------|---------|--------|-------|------|"""
    
    rows = []
    for target in parsed.targets:
        if target["type"] == "station":
            row = f"| {target['id']} | [size] | oval | distinct | homogeneous | present | absent | safe | heterogeneous | Yes | {parsed.tokens.get('tbna_passes', '3')} | {parsed.tokens.get('tbna_gauge', '22')}G | {parsed.tokens.get('rose', 'adequate')} |"
            rows.append(row)
    
    if not rows:
        rows.append("| 4R | 12 | oval | distinct | homogeneous | present | absent | safe | blue (stiff) | Yes | 3 | 22G | adequate |")
    
    return table_header + "\n" + "\n".join(rows)

def _build_navigation_section(parsed: ParsedFacts, ctx: Dict) -> str:
    """Build navigation guidance section."""
    data = {
        "navigation_platform": "Ion" if "ion" in parsed.proc_key else "Monarch",
        "registration_type": "Automatic",
        "tool_to_target_mm": "5",
        "confirmation_imaging": "CBCT" if parsed.adjuncts.get("cbct") else "Fluoroscopy",
        "tool_in_lesion": "Yes"
    }
    return NAVIGATION_GUIDANCE.render(data)

def _build_ablation_section(parsed: ParsedFacts, ctx: Dict) -> str:
    """Build ablation parameters section."""
    data = {
        "ablation_modality": "MWA",
        "ablation_system": "[System]",
        "power_w": "65",
        "time_sec": "180",
        "cycles": "1",
        "pleura_distance_mm": "15",
        "vessel_distance_mm": "10",
        "precautions": "Distance maintained from critical structures"
    }
    return ABLATION_PARAMETERS.render(data)

def _build_pdt_section(parsed: ParsedFacts, ctx: Dict) -> str:
    """Build PDT guidance section."""
    data = {
        "rings_identified": "Yes",
        "ring_level": "2-3",
        "needle_entry_confirmed": "Yes",
        "dilations": "Sequential 8-36Fr",
        "pdt_kit": "Ciaglia Blue Rhino",
        "tube_position_cm": "4",
        "ventilation_confirmed": "Yes"
    }
    return PDT_GUIDANCE.render(data)

def _build_pleural_section(parsed: ParsedFacts, ctx: Dict) -> str:
    """Build pleural procedure section."""
    data = {
        "procedure_type": "Talc pleurodesis" if "talc" in parsed.proc_key else "IPC placement",
        "side": "Right",
        "us_guided": "Yes",
        "volume_ml": "1000",
        "fluid_appearance": "Serosanguineous",
        "manometry_open": "-5",
        "manometry_close": "-20",
        "catheter_size_fr": "14",
        "suction_cmH2O": "-20"
    }
    return PLEURAL_PROCEDURE.render(data)

def _build_anesthesia_data(parsed: ParsedFacts, ctx: Dict) -> Dict:
    """Build anesthesia data from parsed facts."""
    return {
        "anesthesia_method": parsed.tokens.get("anesthesia", "General"),
        "airway_device": "ETT" if parsed.tokens.get("anesthesia") == "general" else "None",
        "anesthesia_provider": "Anesthesiology",
        "lido_ml": str(int(parsed.tokens.get("lido_mg", "60")) / 10),
        "lido_percent": "1",
        "lido_mg": parsed.tokens.get("lido_mg", "60"),
        "lido_mg_per_kg": str(float(parsed.tokens.get("lido_mg", "60")) / 70)[:3]
    }

def _build_specimen_data(parsed: ParsedFacts, ctx: Dict) -> Dict:
    """Build specimen handling data."""
    return {
        "cell_block": "Yes",
        "molecular_tests": "EGFR, ALK, ROS1, PD-L1",
        "micro_tests": "Bacterial, Fungal, AFB",
        "flow_cytometry": "If indicated",
        "special_instructions": "Rush processing if ROSE positive"
    }

def _build_complications_data(parsed: ParsedFacts, ctx: Dict) -> Dict:
    """Build complications data from parsed facts."""
    return {
        "ptx_present": "No" if parsed.complications.get("pneumothorax") == "none" else "No",
        "ptx_size": "N/A",
        "ptx_intervention": "None",
        "bleeding_severity": parsed.complications.get("bleeding", "None"),
        "hemostasis_method": "Suction" if parsed.complications.get("bleeding") == "minimal" else "N/A",
        "hypoxemia_present": "No",
        "hypoxemia_details": "N/A",
        "other_complications": parsed.complications.get("general", "None")
    }

def _build_post_procedure_data(parsed: ParsedFacts, ctx: Dict) -> Dict:
    """Build post-procedure data."""
    return {
        "ebl_ml": parsed.tokens.get("ebl", "Minimal"),
        "disposition": "PACU",
        "imaging_orders": "CXR in PACU",
        "followup_plan": "IP clinic in 1-2 weeks with pathology results"
    }

def _extract_template_data(parsed: ParsedFacts, ctx: Dict) -> Dict:
    """Extract all template variables from parsed facts and context."""
    data = dict(ctx)
    
    # Add parsed tokens
    data.update(parsed.tokens)
    
    # Add standard fields
    data.update({
        "patient_name": ctx.get("patient_name", "[Name]"),
        "dod_id": ctx.get("dod_id", "[DoD ID]"),
        "date": ctx.get("date", "[Date]"),
        "proceduralist": ctx.get("physician_name", "[Physician]"),
        "assistants": "[Assistant]",
        "signature": ctx.get("physician_name", "[Physician]"),
        "title": ctx.get("physician_title", "MD"),
        "date_time": ctx.get("datetime", "[DateTime]"),
        "ebl_ml": parsed.tokens.get("ebl", "Minimal"),
        "complications": parsed.complications.get("general", "None")
    })
    
    # Add procedure-specific fields based on targets
    if parsed.targets:
        lobes = [t["id"] for t in parsed.targets if t["type"] == "lobe"]
        stations = [t["id"] for t in parsed.targets if t["type"] == "station"]
        if lobes:
            data["lobe"] = lobes[0]
        if stations:
            data["station"] = stations[0]
    
    return data

def _create_narrative_summary(parsed: ParsedFacts, miniprompt: str) -> str:
    """Create brief narrative paragraph for nuanced details."""
    narrative_parts = []
    
    # Procedure type
    proc_name = _get_procedure_name(parsed.proc_key)
    narrative_parts.append(f"{proc_name} performed")
    
    # Key findings
    if parsed.adjuncts.get("rebus"):
        narrative_parts.append("with radial EBUS guidance")
    if parsed.adjuncts.get("cbct"):
        narrative_parts.append("CBCT confirmation of tool-in-lesion")
    
    # Sampling details
    if "rose" in parsed.tokens:
        narrative_parts.append(f"ROSE {parsed.tokens['rose']}")
    
    # Include original mini-prompt for context
    narrative_parts.append(f"Clinical note: {miniprompt.strip()}")
    
    return ". ".join(narrative_parts) + "."

def _get_procedure_name(proc_key: str) -> str:
    """Get human-readable procedure name from key."""
    names = {
        "robotic_ion": "Robotic Navigational Bronchoscopy (Ion)",
        "robotic_monarch": "Robotic Navigational Bronchoscopy (Monarch)",
        "enb_rebus_fluoro": "Electromagnetic Navigation Bronchoscopy",
        "ebus_systematic_staging_ett": "EBUS Systematic Staging",
        "targeted_ebus_ett": "Targeted EBUS",
        "pdt": "Percutaneous Dilatational Tracheostomy",
        "tma_mwa": "Transbronchial Microwave Ablation",
        "therapeutic_cryo_airway": "Therapeutic Cryotherapy",
        "rigid_foreign_body": "Rigid Bronchoscopy - Foreign Body Removal",
        "talc_pleurodesis": "Talc Pleurodesis",
        "ipc_fibrinolysis": "IPC Fibrinolysis",
        "bronch_nodule_ablation_generic": "Bronchoscopic Nodule Ablation",
        "standard_bronchoscopy_optional_ebus_lma": "Standard Bronchoscopy"
    }
    return names.get(proc_key, "Bronchoscopy")

def _default_patient_context() -> Dict:
    """Provide default patient context for testing."""
    return {
        "patient_name": "[Patient Name]",
        "dod_id": "[DoD ID]",
        "date": "[Date]",
        "location": "[Location]",
        "physician_name": "[Physician Name]",
        "physician_title": "MD",
        "datetime": "[DateTime]",
        "elective_emergency": "Elective",
        "anticoagulation_plan": "Per protocol",
        "asa": "II",
        "airway_assessment": "Normal"
    }