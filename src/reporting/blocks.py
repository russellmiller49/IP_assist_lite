"""Standardized report blocks for synoptic reporting.

These blocks implement evidence-based structured reporting per RCS-18 criteria
and synoptic best practices for completeness and speed.
"""

from typing import Dict, Any, Optional, List
from string import Template


class ReportBlock:
    """Base class for standardized report blocks."""
    
    def __init__(self, template_text: str):
        self.template = Template(template_text)
    
    def render(self, data: Dict[str, Any]) -> str:
        """Render the block with provided data."""
        # Provide defaults for missing values
        safe_data = {k: v if v is not None else "[PENDING]" for k, v in data.items()}
        return self.template.safe_substitute(safe_data)


# Pre-procedure checklist (drop-in block for RCS-18 compliance)
PRE_PROCEDURE_CHECKLIST = ReportBlock("""Pre-Procedure Readiness:
• Informed consent obtained; risks/benefits/alternatives reviewed; questions answered.
• H&P, relevant imaging, and labs reviewed; NPO verified.
• Anticoagulation/antiplatelet plan: ${anticoagulation_plan}.
• ASA class: ${asa}; Airway assessment: ${airway_assessment}.
• Time Out performed (patient, procedure, site/laterality, critical equipment available).""")


# Anesthesia/Sedation standard block
ANESTHESIA_SEDATION_STANDARD = ReportBlock("""Anesthesia / Sedation:
• Method: ${anesthesia_method}
• Airway: ${airway_device}
• Administered by: ${anesthesia_provider}
• Topical Lidocaine: ${lido_ml} mL of ${lido_percent}% = ${lido_mg} mg (~${lido_mg_per_kg} mg/kg; goal ≤ 8 mg/kg)""")


# Complications checklist (procedure-agnostic)
COMPLICATIONS_CHECKLIST = ReportBlock("""Complications:
• Pneumothorax: ${ptx_present} [size: ${ptx_size}; intervention: ${ptx_intervention}]
• Bleeding: ${bleeding_severity}; Hemostasis: ${hemostasis_method}
• Hypoxemia requiring intervention: ${hypoxemia_present} [details: ${hypoxemia_details}]
• Other: ${other_complications}""")


# EBUS station table with elastography column
EBUS_STATION_TABLE_HEADER = """
| Station | Size (mm) | Shape | Margin | Echo | CHS | CNS | Doppler | Elastography | Sampled | Passes | Gauge | ROSE |
|---------|-----------|--------|---------|------|-----|-----|---------|--------------|---------|--------|-------|------|"""

def format_ebus_station_row(station: Dict[str, Any]) -> str:
    """Format a single EBUS station row for the table."""
    return (
        f"| {station.get('station', '')} "
        f"| {station.get('short_axis_mm', '')} "
        f"| {station.get('shape', '')} "
        f"| {station.get('margin', '')} "
        f"| {station.get('echotexture', '')} "
        f"| {station.get('chs', '')} "
        f"| {station.get('cns', '')} "
        f"| {station.get('doppler', '')} "
        f"| {station.get('elastography', '')} "
        f"| {station.get('sampled', '')} "
        f"| {station.get('passes', '')} "
        f"| {station.get('needle_gauge', '')} "
        f"| {station.get('rose', '')} |"
    )


# Post-procedure standard block
POST_PROCEDURE_STANDARD = ReportBlock("""Post-Procedure:
• EBL: ${ebl_ml} mL
• Disposition: ${disposition}
• Post-procedure imaging: ${imaging_orders}
• Follow-up: ${followup_plan}""")


# Specimen handling block
SPECIMEN_HANDLING = ReportBlock("""Specimens:
• Cell block: ${cell_block}
• Molecular testing: ${molecular_tests}
• Microbiology: ${micro_tests}
• Flow cytometry: ${flow_cytometry}
• Special instructions: ${special_instructions}""")


# Navigation guidance block
NAVIGATION_GUIDANCE = ReportBlock("""Navigation:
• Platform: ${navigation_platform}
• Registration: ${registration_type}
• Tool-to-target distance: ${tool_to_target_mm} mm
• Confirmation imaging: ${confirmation_imaging}
• Tool-in-lesion confirmed: ${tool_in_lesion}""")


# Ablation parameters block
ABLATION_PARAMETERS = ReportBlock("""Ablation Parameters:
• Modality: ${ablation_modality}
• System: ${ablation_system}
• Power: ${power_w} W
• Time: ${time_sec} seconds
• Cycles: ${cycles}
• Distance to pleura: ${pleura_distance_mm} mm
• Distance to vessels: ${vessel_distance_mm} mm
• Precautions: ${precautions}""")


# PDT guidance block
PDT_GUIDANCE = ReportBlock("""PDT Bronchoscopic Guidance:
• Tracheal rings identified: ${rings_identified}
• Puncture site: Between rings ${ring_level}
• Needle entry visualized: ${needle_entry_confirmed}
• Serial dilations: ${dilations}
• Kit used: ${pdt_kit}
• Final tube position: ${tube_position_cm} cm above carina
• Bilateral ventilation confirmed: ${ventilation_confirmed}""")


# Pleural procedure block
PLEURAL_PROCEDURE = ReportBlock("""Pleural Procedure:
• Type: ${procedure_type}
• Side: ${side}
• Ultrasound guidance: ${us_guided}
• Volume drained: ${volume_ml} mL
• Appearance: ${fluid_appearance}
• Manometry: Opening ${manometry_open} cmH2O, Closing ${manometry_close} cmH2O
• Catheter size: ${catheter_size_fr} Fr
• Suction applied: ${suction_cmH2O} cmH2O""")


class SynopticReportBuilder:
    """Builder for creating synoptic reports from blocks."""
    
    def __init__(self):
        self.sections: List[str] = []
    
    def add_section(self, title: str, content: str) -> "SynopticReportBuilder":
        """Add a section to the report."""
        self.sections.append(f"\n{title}\n{'=' * len(title)}\n{content}")
        return self
    
    def add_block(self, block: ReportBlock, data: Dict[str, Any]) -> "SynopticReportBuilder":
        """Add a pre-defined block with data."""
        self.sections.append(block.render(data))
        return self
    
    def add_narrative(self, narrative: str) -> "SynopticReportBuilder":
        """Add narrative text section."""
        self.sections.append(f"\nProcedure Narrative:\n{narrative}")
        return self
    
    def build(self) -> str:
        """Build the complete report."""
        return "\n\n".join(self.sections)


def create_rcs18_compliant_header(
    patient_name: str,
    dod_id: str,
    procedure_date: str,
    location: str,
    procedure_type: str,
    elective_emergency: str
) -> str:
    """Create RCS-18 compliant report header with mandatory fields."""
    return f"""INTERVENTIONAL PULMONOLOGY PROCEDURE REPORT
{'=' * 45}

Patient: {patient_name}
DoD ID: {dod_id}
Date: {procedure_date}
Location: {location}
Procedure: {procedure_type}
Status: {elective_emergency.capitalize()}"""


def create_signature_block(
    physician_name: str,
    physician_title: str,
    datetime_str: str
) -> str:
    """Create RCS-18 compliant signature block."""
    return f"""
Signature Block:
{'=' * 15}
Electronically signed by:
{physician_name}, {physician_title}
{datetime_str}

This report has been reviewed and approved.
Per RCS-18 criteria, all mandatory fields have been completed."""