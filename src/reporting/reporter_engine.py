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
    
    # Add "Procedure Performed" section
    procedure_performed = _create_procedure_performed_section(parsed, miniprompt)
    builder.sections.append(f"\nProcedure Performed:\n{procedure_performed}")
    
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
    
    # Add impression/summary section
    impression = _create_impression_summary(parsed, miniprompt, patient_ctx)
    builder.sections.append(f"\nImpression / Summary:\n{impression}")
    
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
        "micro_tests": "Bacterial, fungal, AFB cultures",
        "flow_cytometry": "If indicated",
        "special_instructions": "Rush processing if ROSE positive"
    }

def _build_complications_data(parsed: ParsedFacts, ctx: Dict) -> Dict:
    """Build complications data from parsed facts."""
    bleeding = parsed.complications.get("bleeding", "none")
    if bleeding == "minimal":
        bleeding_text = "None"
        hemostasis = "not required"
    elif bleeding == "none":
        bleeding_text = "None"
        hemostasis = "not required"
    else:
        bleeding_text = bleeding.capitalize()
        hemostasis = "required"
    
    return {
        "ptx_present": "No",
        "ptx_size": "N/A",
        "ptx_intervention": "None",
        "bleeding_severity": bleeding_text,
        "hemostasis_method": hemostasis,
        "hypoxemia_present": "No",
        "hypoxemia_details": "N/A",
        "other_complications": "None"
    }

def _build_post_procedure_data(parsed: ParsedFacts, ctx: Dict) -> Dict:
    """Build post-procedure data."""
    return {
        "ebl_ml": "Minimal",
        "disposition": "PACU, stable",
        "imaging_orders": "Chest X-ray in PACU",
        "followup_plan": "Interventional Pulmonology clinic in 1-2 weeks with pathology results"
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
    """Create detailed narrative paragraph with procedure description."""
    narrative_parts = []
    
    # Determine procedure details from parsed facts
    proc_name = _get_procedure_name(parsed.proc_key)
    
    # Build comprehensive narrative based on procedure type
    if "robotic" in parsed.proc_key:
        # Robotic navigation narrative
        if parsed.targets:
            target = parsed.targets[0]
            location = target.get('id', 'target lesion')
            size = target.get('size', '')
            if size:
                narrative_parts.append(f"Robotic navigational bronchoscopy was performed for evaluation of a {size} cm lesion in the {location}")
            else:
                narrative_parts.append(f"Robotic navigational bronchoscopy was performed for evaluation of a lesion in the {location}")
        else:
            narrative_parts.append(f"Robotic navigational bronchoscopy was performed")
        
        # Navigation details
        if "ion" in parsed.proc_key.lower():
            narrative_parts.append("Navigation was achieved using the Ion robotic system")
        elif "monarch" in parsed.proc_key.lower():
            narrative_parts.append("Navigation was achieved using the Monarch robotic system")
        
        # Tool-in-lesion confirmation
        if parsed.adjuncts.get("cbct"):
            if "no radial" in miniprompt.lower() or "no signal" in miniprompt.lower():
                narrative_parts.append("Initially, no radial signal was detected; Cios Spin cone-beam CT was obtained, showing need for readjustment. Following adjustment, tool-in-lesion was confirmed by spin imaging")
            else:
                narrative_parts.append("Tool-in-lesion was confirmed by cone-beam CT (CBCT) imaging")
        elif parsed.adjuncts.get("rebus"):
            narrative_parts.append("Radial EBUS confirmed appropriate positioning")
        
        # Sampling details
        sampling_details = _extract_sampling_details(parsed, miniprompt)
        if sampling_details:
            narrative_parts.append(f"\nSampling included {sampling_details}")
        
        # ROSE status
        if parsed.adjuncts.get("rose"):
            rose_status = parsed.tokens.get('rose', 'adequate')
            narrative_parts.append(f"ROSE was {rose_status}")
    
    # EBUS narrative
    if "ebus" in parsed.proc_key.lower() or any(t['type'] == 'station' for t in parsed.targets):
        ebus_stations = [t for t in parsed.targets if t['type'] == 'station']
        if ebus_stations:
            if narrative_parts:  # If there's already content (combined procedure)
                narrative_parts.append("\nSubsequently, linear EBUS staging was performed via the ETT")
            else:
                narrative_parts.append("Linear EBUS staging was performed")
            
            narrative_parts.append("The following stations were sampled with 22G needle (5 passes each):")
            for station in ebus_stations:
                size = station.get('size', '')
                station_id = station['id']
                if size:
                    narrative_parts.append(f"\n    • Station {station_id} ({size} mm)")
                else:
                    narrative_parts.append(f"\n    • Station {station_id}")
            
            if parsed.adjuncts.get("rose"):
                rose_status = parsed.tokens.get('rose', 'adequate')
                narrative_parts.append(f"\nROSE was {rose_status} at all stations")
    
    # Complications statement
    if parsed.complications.get('general', 'none').lower() == 'none':
        narrative_parts.append("\nThe patient tolerated the procedure without complication")
    elif parsed.complications.get('bleeding') == 'minimal':
        narrative_parts.append("\nMinimal bleeding was encountered and controlled with suction. No other complications occurred")
    
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

def _create_procedure_performed_section(parsed: ParsedFacts, miniprompt: str) -> str:
    """Create the Procedure Performed section with bullet points."""
    performed = []
    
    # Main procedure
    proc_name = _get_procedure_name(parsed.proc_key)
    performed.append(f"    • {proc_name}")
    
    # Key confirmations
    if parsed.adjuncts.get("cbct"):
        performed.append("    • Cone-beam CT (CBCT) confirmation of tool-in-lesion")
    elif parsed.adjuncts.get("rebus"):
        performed.append("    • Radial EBUS guidance")
    
    # ROSE
    if parsed.adjuncts.get("rose"):
        rose_status = parsed.tokens.get('rose', 'Adequate')
        performed.append(f"    • Rapid On-Site Evaluation (ROSE): {rose_status.capitalize()}")
    
    # EBUS staging
    ebus_stations = [t for t in parsed.targets if t['type'] == 'station']
    if ebus_stations:
        performed.append("    • Endobronchial Ultrasound (EBUS) staging")
    
    return "\n".join(performed)

def _extract_sampling_details(parsed: ParsedFacts, miniprompt: str) -> str:
    """Extract detailed sampling information from miniprompt."""
    details = []
    
    # Look for needle passes
    import re
    needle_pattern = r'(\d+)\s*(?:needle\s*)?passes?\s*(?:with\s*)?(\d+G)'
    needle_matches = re.findall(needle_pattern, miniprompt, re.IGNORECASE)
    for passes, gauge in needle_matches:
        details.append(f"{passes} {gauge} needle passes")
    
    # Alternative pattern
    alt_pattern = r'(\d+G)\s*(?:needle\s*)?(?:x|×)(\d+)'
    alt_matches = re.findall(alt_pattern, miniprompt, re.IGNORECASE)
    for gauge, passes in alt_matches:
        details.append(f"{passes} passes with {gauge} needle")
    
    # Look for cytobiopsy/cryobiopsy
    cryo_pattern = r'(?:cyto|cryo)biopsy\s*(?:x|×)?(\d+)\s*(?:with\s*)?(\d+\.\d+mm)?'
    cryo_matches = re.findall(cryo_pattern, miniprompt, re.IGNORECASE)
    for count, size in cryo_matches:
        if size:
            details.append(f"{count} cytobiopsy passes with {size} probe")
        else:
            details.append(f"{count} cytobiopsy passes")
    
    # Look for forceps
    if 'forceps' in miniprompt.lower():
        forceps_pattern = r'forceps\s*(?:biopsy\s*)?(?:x|×)?(\d+)'
        forceps_match = re.search(forceps_pattern, miniprompt, re.IGNORECASE)
        if forceps_match:
            details.append(f"{forceps_match.group(1)} forceps biopsies")
        else:
            details.append("forceps biopsy")
    
    if details:
        # Format as a readable list
        if len(details) == 1:
            return details[0]
        elif len(details) == 2:
            return f"{details[0]} and {details[1]}"
        else:
            return ", ".join(details[:-1]) + f", and {details[-1]}"
    
    return ""

def _create_impression_summary(parsed: ParsedFacts, miniprompt: str, ctx: Dict) -> str:
    """Create impression/summary section."""
    summary_parts = []
    
    # Determine success/completion status
    summary_parts.append("Successful")
    
    # Procedure type
    proc_name = _get_procedure_name(parsed.proc_key)
    if "robotic" in parsed.proc_key:
        if parsed.targets:
            target = parsed.targets[0]
            location = target.get('id', 'target')
            size = target.get('size', '')
            if size:
                summary_parts.append(f"{proc_name} of {location} {size} cm lesion")
            else:
                summary_parts.append(f"{proc_name} of {location} lesion")
        else:
            summary_parts.append(proc_name)
    else:
        summary_parts.append(proc_name)
    
    # Key confirmations
    if parsed.adjuncts.get("cbct"):
        summary_parts.append("with CBCT confirmation of tool-in-lesion")
    
    # Sampling summary
    sampling_details = _extract_sampling_details(parsed, miniprompt)
    if sampling_details:
        summary_parts.append(f"Adequate sampling obtained via {sampling_details}")
    
    # EBUS staging if performed
    ebus_stations = [t for t in parsed.targets if t['type'] == 'station']
    if ebus_stations:
        station_list = ", ".join([t['id'] for t in ebus_stations])
        summary_parts.append(f"Linear EBUS staging performed at stations {station_list} with adequate ROSE")
    
    # Complications
    if parsed.complications.get('general', 'none').lower() == 'none':
        summary_parts.append("No procedural complications")
    
    # Specimen disposition
    if parsed.adjuncts.get("rose") or any("biopsy" in str(t) for t in parsed.targets):
        summary_parts.append("Specimens sent for cytology, molecular studies, microbiology, and flow cytometry as indicated")
    
    return ". ".join(summary_parts) + "."

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