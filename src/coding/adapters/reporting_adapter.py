"""Adapter to convert IPProcedureReport to coding Case objects."""

from typing import List, Optional, Dict
from ...reporting.schema_contract import IPProcedureReport
from ..schema import Case, PerformedItem, Sedation


def case_from_ip_report(ip: IPProcedureReport) -> Case:
    """Convert IPProcedureReport to Case for deterministic coding.
    
    Args:
        ip: Validated IPProcedureReport from structurer
        
    Returns:
        Case object ready for coding rules engine
    """
    case = Case(report_text="")  # Text not needed for structured input
    
    # Set patient age if available
    if hasattr(ip, "patient") and hasattr(ip.patient, "dob"):
        # Could calculate age from DOB if needed
        pass
    
    # Map procedures as a list of PerformedItems
    case.items = []
    
    # Map procedure family
    _map_procedures(case, ip)
    
    # Map imaging guidance
    _map_imaging(case, ip)
    
    # Map sampling
    _map_sampling(case, ip)
    
    # Map sedation/anesthesia
    _map_sedation(case, ip)
    
    return case

def _map_procedures(case: Case, ip: IPProcedureReport) -> None:
    """Map procedure types to Case."""
    proc_key = ip.procedure_key
    
    # Bronchoscopy base
    if proc_key != "pdt":  # PDT doesn't have bronch base
        case.items.append(PerformedItem(
            proc_id="flexible_bronchoscopy",
            details={}
        ))
    
    # Navigation procedures
    if "robotic" in proc_key or "enb" in proc_key:
        platform = "Ion" if "ion" in proc_key else "Monarch" if "monarch" in proc_key else "ENB"
        case.items.append(PerformedItem(
            proc_id="navigation_bronchoscopy",
            details={"platform": platform}
        ))
    
    # EBUS procedures
    if "ebus" in proc_key:
        if "staging" in proc_key:
            # Systematic staging - multiple stations
            station_count = 0
            if ip.ebus and ip.ebus.stations:
                station_count = len([s for s in ip.ebus.stations if s.sampled])
            case.items.append(PerformedItem(
                proc_id="ebus_tbna",
                details={"station_count": str(station_count), "type": "staging"}
            ))
        else:
            # Targeted EBUS
            case.items.append(PerformedItem(
                proc_id="ebus_tbna",
                details={"type": "targeted"}
            ))
    
    # PDT
    if proc_key == "pdt":
        case.items.append(PerformedItem(
            proc_id="percutaneous_tracheostomy",
            details={"bronch_guided": "true"}
        ))
    
    # Ablation procedures
    if "ablation" in proc_key or "mwa" in proc_key:
        case.items.append(PerformedItem(
            proc_id="bronchoscopic_ablation",
            details={"modality": "MWA"}
        ))
    
    # Therapeutic procedures
    if "therapeutic_cryo" in proc_key:
        case.items.append(PerformedItem(
            proc_id="therapeutic_cryotherapy",
            details={}
        ))
    
    # Foreign body
    if "foreign_body" in proc_key:
        case.items.append(PerformedItem(
            proc_id="foreign_body_removal",
            details={"rigid": "true"}
        ))
    
    # Pleural procedures
    if "pleurodesis" in proc_key:
        case.items.append(PerformedItem(
            proc_id="talc_pleurodesis",
            details={}
        ))
    elif "ipc" in proc_key:
        if "fibrinolysis" in proc_key:
            case.items.append(PerformedItem(
                proc_id="ipc_fibrinolysis",
                details={}
            ))
        else:
            case.items.append(PerformedItem(
                proc_id="ipc_placement",
                details={}
            ))

def _map_imaging(case: Case, ip: IPProcedureReport) -> None:
    """Map imaging guidance to Case."""
    if not ip.imaging_guidance:
        return
    
    # CBCT/3D spin
    if ip.imaging_guidance.cbct and ip.imaging_guidance.cbct.system:
        case.items.append(PerformedItem(
            proc_id="cbct_guidance",
            details={
                "system": ip.imaging_guidance.cbct.system,
                "spins": str(ip.imaging_guidance.cbct.spins or 0)
            }
        ))
    
    # Radial EBUS
    if ip.imaging_guidance.rebus and ip.imaging_guidance.rebus.used:
        case.items.append(PerformedItem(
            proc_id="radial_ebus",
            details={"view": ip.imaging_guidance.rebus.view or ""}
        ))
    
    # Fluoroscopy
    if ip.imaging_guidance.fluoro and ip.imaging_guidance.fluoro.used:
        case.items.append(PerformedItem(
            proc_id="fluoroscopic_guidance",
            details={"time_min": str(ip.imaging_guidance.fluoro.time_min or 0)}
        ))

def _map_sampling(case: Case, ip: IPProcedureReport) -> None:
    """Map sampling procedures to Case."""
    if not ip.sampling:
        return
    
    # TBNA
    if ip.sampling.tbna:
        lobes = set()
        total_passes = 0
        for tbna in ip.sampling.tbna:
            if tbna.site:
                # Extract lobe from site (e.g., "RUL", "4R" -> maps to a lobe)
                lobe = _site_to_lobe(tbna.site)
                if lobe:
                    lobes.add(lobe)
            total_passes += tbna.passes or 0
        
        if lobes:
            case.items.append(PerformedItem(
                proc_id="tbna",
                details={
                    "lobes": ",".join(lobes),
                    "lobe_count": str(len(lobes)),
                    "total_passes": str(total_passes)
                }
            ))
    
    # TBBX
    if ip.sampling.tbbx:
        lobes = set()
        for tbbx in ip.sampling.tbbx:
            if tbbx.lobe:
                lobes.add(tbbx.lobe)
        
        if lobes:
            case.items.append(PerformedItem(
                proc_id="transbronchial_biopsy",
                details={
                    "lobes": ",".join(lobes),
                    "lobe_count": str(len(lobes))
                }
            ))
    
    # Cryobiopsy
    if ip.sampling.cryo_biopsy:
        case.items.append(PerformedItem(
            proc_id="cryobiopsy",
            details={
                "count": str(len(ip.sampling.cryo_biopsy)),
                "probe_mm": str(ip.sampling.cryo_biopsy[0].probe_mm) if ip.sampling.cryo_biopsy else ""
            }
        ))
    
    # BAL
    if ip.sampling.bal:
        case.items.append(PerformedItem(
            proc_id="bal",
            details={
                "volume_ml": str(ip.sampling.bal.returned_ml or 0)
            }
        ))

def _map_sedation(case: Case, ip: IPProcedureReport) -> None:
    """Map sedation/anesthesia to Case."""
    if not ip.anesthesia:
        return
    
    # Only map moderate sedation (GA doesn't get separate coding)
    if ip.anesthesia.method == "Moderate":
        case.sedation = Sedation(
            type="moderate",
            provided_by_proceduralist=ip.anesthesia.provider != "Anesthesiology",
            total_minutes=30  # Default, would need to extract from report
        )

def _site_to_lobe(site: str) -> Optional[str]:
    """Map anatomical site to lobe.
    
    Args:
        site: Station or segment identifier
        
    Returns:
        Lobe abbreviation or None
    """
    # Station to lobe mapping
    station_map = {
        "2R": "RUL", "2L": "LUL",
        "4R": "RUL", "4L": "LUL", 
        "7": "bilateral",
        "10R": "RUL", "10L": "LUL",
        "11R": "RLL", "11L": "LLL",
        "12R": "RML", "12L": "LLL"
    }
    
    # Direct lobe names
    if site.upper() in ["RUL", "RML", "RLL", "LUL", "LLL", "LINGULA"]:
        return site.upper()
    
    # Check station mapping
    return station_map.get(site.upper())

def validate_case_mapping(case: Case) -> List[str]:
    """Validate the mapped Case object.
    
    Args:
        case: Mapped Case object
        
    Returns:
        List of validation issues
    """
    issues = []
    
    # Check for basic procedure
    has_base = any(item.proc_id in ["flexible_bronchoscopy", "percutaneous_tracheostomy"] 
                   for item in case.items)
    if not has_base:
        issues.append("No base procedure identified")
    
    # Check navigation consistency
    has_nav = any(item.proc_id == "navigation_bronchoscopy" for item in case.items)
    has_confirm = any(item.proc_id in ["radial_ebus", "cbct_guidance"] for item in case.items)
    if has_nav and not has_confirm:
        issues.append("Navigation without confirmation imaging")
    
    return issues