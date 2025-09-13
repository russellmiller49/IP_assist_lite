"""Adapter to convert IPProcedureReport to coding Case objects."""

from typing import List, Optional
from ...reporting.schema_contract import IPProcedureReport
from ..schema import Case, PerformedProcedure, Sedation


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
    
    # Map procedure family
    _map_procedures(case, ip)
    
    # Map imaging guidance
    _map_imaging(case, ip)
    
    # Map sampling
    _map_sampling(case, ip)
    
    # Map sedation/anesthesia
    _map_sedation(case, ip)
    
    # Map complications
    _map_complications(case, ip)
    
    return case

def _map_procedures(case: Case, ip: IPProcedureReport) -> None:
    """Map procedure types to Case."""
    proc_key = ip.procedure_key
    
    # Bronchoscopy base
    if proc_key != "pdt":  # PDT doesn't have bronch base
        case.bronchoscopy = PerformedProcedure(
            name="Flexible bronchoscopy",
            performed=True
        )
    
    # Navigation procedures
    if "robotic" in proc_key or "enb" in proc_key:
        case.navigation = PerformedProcedure(
            name="Computer-assisted navigation",
            performed=True,
            details={"platform": "Ion" if "ion" in proc_key else "Monarch" if "monarch" in proc_key else "ENB"}
        )
    
    # EBUS procedures
    if "ebus" in proc_key:
        if "staging" in proc_key:
            # Systematic staging - multiple stations
            if ip.ebus and ip.ebus.stations:
                station_count = len([s for s in ip.ebus.stations if s.sampled])
                case.ebus_tbna = PerformedProcedure(
                    name="EBUS-TBNA",
                    performed=True,
                    details={"station_count": station_count}
                )
        else:
            # Targeted EBUS
            case.ebus_tbna = PerformedProcedure(
                name="EBUS-TBNA targeted",
                performed=True
            )
    
    # PDT
    if proc_key == "pdt":
        case.tracheostomy = PerformedProcedure(
            name="Percutaneous dilatational tracheostomy",
            performed=True,
            details={"bronch_guided": True}
        )
    
    # Ablation procedures
    if "ablation" in proc_key or "mwa" in proc_key:
        case.ablation = PerformedProcedure(
            name="Bronchoscopic ablation",
            performed=True,
            details={"modality": "MWA"}
        )
    
    # Therapeutic procedures
    if "therapeutic_cryo" in proc_key:
        case.therapeutic = PerformedProcedure(
            name="Therapeutic cryotherapy",
            performed=True
        )
    
    # Foreign body
    if "foreign_body" in proc_key:
        case.foreign_body = PerformedProcedure(
            name="Foreign body removal",
            performed=True,
            details={"rigid": True}
        )
    
    # Pleural procedures
    if "pleurodesis" in proc_key:
        case.pleurodesis = PerformedProcedure(
            name="Talc pleurodesis",
            performed=True
        )
    elif "ipc" in proc_key:
        if "fibrinolysis" in proc_key:
            case.ipc_fibrinolysis = PerformedProcedure(
                name="IPC fibrinolysis",
                performed=True
            )
        else:
            case.ipc = PerformedProcedure(
                name="IPC placement",
                performed=True
            )

def _map_imaging(case: Case, ip: IPProcedureReport) -> None:
    """Map imaging guidance to Case."""
    if not ip.imaging_guidance:
        return
    
    # CBCT/3D spin
    if ip.imaging_guidance.cbct and ip.imaging_guidance.cbct.system:
        case.cbct = PerformedProcedure(
            name="CBCT guidance",
            performed=True,
            details={
                "system": ip.imaging_guidance.cbct.system,
                "spins": ip.imaging_guidance.cbct.spins
            }
        )
    
    # Radial EBUS
    if ip.imaging_guidance.rebus and ip.imaging_guidance.rebus.used:
        case.radial_ebus = PerformedProcedure(
            name="Radial EBUS",
            performed=True,
            details={"view": ip.imaging_guidance.rebus.view}
        )
    
    # Fluoroscopy
    if ip.imaging_guidance.fluoro and ip.imaging_guidance.fluoro.used:
        case.fluoroscopy = PerformedProcedure(
            name="Fluoroscopic guidance",
            performed=True,
            details={"time_min": ip.imaging_guidance.fluoro.time_min}
        )

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
            case.tbna = PerformedProcedure(
                name="Transbronchial needle aspiration",
                performed=True,
                details={
                    "lobes": list(lobes),
                    "lobe_count": len(lobes),
                    "total_passes": total_passes
                }
            )
    
    # TBBX
    if ip.sampling.tbbx:
        lobes = set()
        for tbbx in ip.sampling.tbbx:
            if tbbx.lobe:
                lobes.add(tbbx.lobe)
        
        if lobes:
            case.tbbx = PerformedProcedure(
                name="Transbronchial biopsy",
                performed=True,
                details={
                    "lobes": list(lobes),
                    "lobe_count": len(lobes)
                }
            )
    
    # Cryobiopsy
    if ip.sampling.cryo_biopsy:
        case.cryobiopsy = PerformedProcedure(
            name="Cryobiopsy",
            performed=True,
            details={
                "count": len(ip.sampling.cryo_biopsy),
                "probe_mm": ip.sampling.cryo_biopsy[0].probe_mm if ip.sampling.cryo_biopsy else None
            }
        )
    
    # BAL
    if ip.sampling.bal:
        case.bal = PerformedProcedure(
            name="Bronchoalveolar lavage",
            performed=True,
            details={
                "volume_ml": ip.sampling.bal.returned_ml
            }
        )

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

def _map_complications(case: Case, ip: IPProcedureReport) -> None:
    """Map complications for reference."""
    if not ip.complications:
        return
    
    # Store as details for reference (doesn't affect CPT coding directly)
    complications = []
    
    if ip.complications.pneumothorax and ip.complications.pneumothorax.present:
        complications.append("pneumothorax")
    
    if ip.complications.bleeding and ip.complications.bleeding.severity not in ["none", "minimal"]:
        complications.append(f"bleeding_{ip.complications.bleeding.severity}")
    
    if complications:
        case.complications = complications

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
    if not case.bronchoscopy and not case.tracheostomy:
        issues.append("No base procedure identified")
    
    # Check navigation consistency
    if case.navigation and not case.radial_ebus and not case.cbct:
        issues.append("Navigation without confirmation imaging")
    
    return issues