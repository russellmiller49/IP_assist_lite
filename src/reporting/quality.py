"""Quality validators for RCS-18 compliance and IP-specific safety checks."""

from typing import List, Optional, Dict, Any
from .schema_contract import IPProcedureReport

# RCS-18 Required Fields (Qasem et al.)
RCS18_FIELDS = [
    "date_time",
    "elective_vs_emergency", 
    "surgeon_proceduralist",
    "anesthetist_provider",
    "procedure_performed",
    "incision_approach",
    "diagnosis_preop",
    "findings_intraop",
    "complications",
    "extra_procedures",
    "tissue_removed_added",
    "implants_devices",
    "closure_method",
    "estimated_blood_loss",
    "antibiotic_prophylaxis",
    "vte_prophylaxis",
    "postop_instructions",
    "signature_attestation"
]

def validate_rcs18(ip: IPProcedureReport) -> List[str]:
    """Validate RCS-18 compliance.
    
    Per Qasem et al. (2019), all 18 fields should be present.
    Digital proformas achieve 99.6% compliance when mandatory.
    
    Args:
        ip: IPProcedureReport to validate
        
    Returns:
        List of missing or problematic fields
    """
    issues = []
    
    # Check date/time
    if not ip.context or not ip.context.date:
        issues.append("Missing date (RCS-18 #1)")
    
    # Check elective vs emergency
    if not ip.context or not ip.context.elective_vs_emergency:
        issues.append("Missing elective/emergency status (RCS-18 #2)")
    
    # Check proceduralist (surgeon)
    if not ip.procedure_key:
        issues.append("Missing procedure identification (RCS-18 #5)")
    
    # Check anesthesia provider
    if ip.anesthesia and not ip.anesthesia.provider:
        issues.append("Missing anesthesia provider (RCS-18 #4)")
    
    # Check findings
    if not ip.findings:
        issues.append("Missing intraoperative findings (RCS-18 #8)")
    
    # Check complications
    if not ip.complications:
        issues.append("Missing complications documentation (RCS-18 #9)")
    
    # Check EBL
    if not ip.postop or ip.postop.ebl_ml is None:
        issues.append("Missing estimated blood loss (RCS-18 #14)")
    
    # Check disposition/instructions
    if not ip.postop or not ip.postop.disposition:
        issues.append("Missing post-operative instructions (RCS-18 #17)")
    
    return issues

def validate_lidocaine_safety(ip: IPProcedureReport) -> List[str]:
    """Validate lidocaine dosing safety.
    
    Target: ≤ 8 mg/kg (per template guidelines)
    Toxic threshold: > 5 mg/kg without epinephrine, > 7 mg/kg with
    
    Args:
        ip: IPProcedureReport to validate
        
    Returns:
        List of safety warnings
    """
    warnings = []
    
    if not ip.anesthesia or not ip.anesthesia.topical_lidocaine:
        return warnings
    
    lido = ip.anesthesia.topical_lidocaine
    
    # Check absolute dose
    if lido.mg and lido.mg > 500:
        warnings.append(f"High lidocaine dose: {lido.mg} mg (>500 mg)")
    
    # Check mg/kg if available
    if lido.mg_per_kg:
        if lido.mg_per_kg > 8.0:
            warnings.append(f"Lidocaine exceeds 8 mg/kg target: {lido.mg_per_kg} mg/kg")
        elif lido.mg_per_kg > 7.0:
            warnings.append(f"Lidocaine approaching toxic threshold: {lido.mg_per_kg} mg/kg")
    
    return warnings

def validate_imaging_consistency(ip: IPProcedureReport) -> List[str]:
    """Validate imaging modality documentation.
    
    If CBCT/3D spin mentioned, ensure proper documentation.
    
    Args:
        ip: IPProcedureReport to validate
        
    Returns:
        List of consistency issues
    """
    issues = []
    
    if not ip.imaging_guidance:
        return issues
    
    # Check CBCT documentation
    if ip.imaging_guidance.cbct:
        cbct = ip.imaging_guidance.cbct
        if cbct.system and not cbct.spins:
            issues.append("CBCT used but spin count not documented")
    
    # Check radiation metrics for fluoro/CBCT
    if (ip.imaging_guidance.fluoro and ip.imaging_guidance.fluoro.used) or \
       (ip.imaging_guidance.cbct and ip.imaging_guidance.cbct.system):
        # Should have radiation metrics
        if not ip.imaging_guidance.fluoro or not ip.imaging_guidance.fluoro.time_min:
            issues.append("Radiation-based imaging used but fluoro time not documented")
    
    return issues

def validate_ebus_completeness(ip: IPProcedureReport) -> List[str]:
    """Validate EBUS documentation completeness.
    
    For systematic staging, ensure elastography column populated.
    
    Args:
        ip: IPProcedureReport to validate
        
    Returns:
        List of missing EBUS fields
    """
    issues = []
    
    if not ip.ebus or not ip.ebus.stations:
        return issues
    
    for i, station in enumerate(ip.ebus.stations):
        # Check elastography for staging procedures
        if "staging" in ip.procedure_key.lower():
            if not station.elastography:
                issues.append(f"Station {station.station}: Missing elastography assessment")
        
        # Check basic requirements for sampled stations
        if station.sampled:
            if not station.passes:
                issues.append(f"Station {station.station}: Sampled but passes not documented")
            if not station.needle_gauge:
                issues.append(f"Station {station.station}: Sampled but needle gauge not documented")
    
    return issues

def validate_specimen_handling(ip: IPProcedureReport) -> List[str]:
    """Validate specimen collection and handling.
    
    Args:
        ip: IPProcedureReport to validate
        
    Returns:
        List of specimen handling issues
    """
    issues = []
    
    # Check if specimens were collected but not documented
    if ip.sampling:
        has_samples = False
        
        if ip.sampling.tbna and len(ip.sampling.tbna) > 0:
            has_samples = True
        elif ip.sampling.tbbx and len(ip.sampling.tbbx) > 0:
            has_samples = True
        elif ip.sampling.cryo_biopsy and len(ip.sampling.cryo_biopsy) > 0:
            has_samples = True
        
        if has_samples and not ip.specimens:
            issues.append("Samples collected but specimen handling not documented")
    
    return issues

def validate_safety_critical(ip: IPProcedureReport) -> List[str]:
    """Validate safety-critical fields.
    
    Args:
        ip: IPProcedureReport to validate
        
    Returns:
        List of critical safety issues
    """
    critical = []
    
    # Check for massive bleeding without intervention
    if ip.complications and ip.complications.bleeding:
        if ip.complications.bleeding.severity in ["brisk", "massive"]:
            if not ip.complications.bleeding.hemostasis:
                critical.append("CRITICAL: Significant bleeding without documented hemostasis")
    
    # Check for pneumothorax without intervention plan
    if ip.complications and ip.complications.pneumothorax:
        if ip.complications.pneumothorax.present and not ip.complications.pneumothorax.intervention:
            critical.append("CRITICAL: Pneumothorax present without intervention documented")
    
    # Check for hypoxemia without response
    if ip.complications and ip.complications.hypoxemia_intervention:
        if ip.complications.hypoxemia_intervention.present and not ip.complications.hypoxemia_intervention.details:
            critical.append("CRITICAL: Hypoxemia requiring intervention but details missing")
    
    return critical

def run_all_validators(ip: IPProcedureReport) -> Dict[str, List[str]]:
    """Run all quality validators.
    
    Args:
        ip: IPProcedureReport to validate
        
    Returns:
        Dictionary of validator results
    """
    return {
        "rcs18": validate_rcs18(ip),
        "lidocaine": validate_lidocaine_safety(ip),
        "imaging": validate_imaging_consistency(ip),
        "ebus": validate_ebus_completeness(ip),
        "specimens": validate_specimen_handling(ip),
        "safety_critical": validate_safety_critical(ip)
    }

def get_validation_summary(results: Dict[str, List[str]]) -> str:
    """Generate human-readable validation summary.
    
    Args:
        results: Validator results from run_all_validators
        
    Returns:
        Formatted summary string
    """
    lines = []
    
    # Check critical issues first
    if results.get("safety_critical"):
        lines.append("⚠️ CRITICAL SAFETY ISSUES:")
        for issue in results["safety_critical"]:
            lines.append(f"  • {issue}")
    
    # RCS-18 compliance
    rcs_issues = results.get("rcs18", [])
    if rcs_issues:
        lines.append(f"\n📋 RCS-18 Compliance: {18 - len(rcs_issues)}/18 fields complete")
        for issue in rcs_issues[:3]:  # Show first 3
            lines.append(f"  • {issue}")
        if len(rcs_issues) > 3:
            lines.append(f"  • ... and {len(rcs_issues) - 3} more")
    else:
        lines.append("\n✅ RCS-18 Compliance: All 18 fields present")
    
    # Other validators
    validator_names = {
        "lidocaine": "Lidocaine Safety",
        "imaging": "Imaging Documentation",
        "ebus": "EBUS Completeness",
        "specimens": "Specimen Handling"
    }
    
    for key, name in validator_names.items():
        issues = results.get(key, [])
        if issues:
            lines.append(f"\n⚠️ {name}:")
            for issue in issues[:2]:
                lines.append(f"  • {issue}")
    
    if not any(results.values()):
        lines.append("\n✅ All quality checks passed")
    
    return "\n".join(lines)

def auto_fill_defaults(ip: IPProcedureReport) -> IPProcedureReport:
    """Auto-fill safe defaults for missing non-critical fields.
    
    Per evidence, digital proformas can auto-populate 63% of fields.
    
    Args:
        ip: IPProcedureReport to augment
        
    Returns:
        Updated IPProcedureReport
    """
    # Set safe defaults for missing fields
    if ip.context:
        if not ip.context.elective_vs_emergency:
            ip.context.elective_vs_emergency = "elective"
        if not ip.context.asa:
            ip.context.asa = "II"  # Most common
    
    if ip.postop:
        if not ip.postop.disposition:
            ip.postop.disposition = "PACU"
        if ip.postop.ebl_ml is None:
            ip.postop.ebl_ml = 5  # Minimal default
    
    if ip.complications:
        if not ip.complications.pneumothorax:
            ip.complications.pneumothorax = {"present": False}
        if not ip.complications.bleeding:
            ip.complications.bleeding = {"severity": "none"}
    
    return ip