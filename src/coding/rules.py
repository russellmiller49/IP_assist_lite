"""Deterministic mapping to codes + OPPS/NCCI/doc checks, with bilateral support."""

from math import ceil
from typing import List, Set
from .schema import Case, CodeLine, CodeBundle, StructureType
from .kb import CodingKB
from .patterns import PATTERNS

def _stations_from(case: Case) -> Set[str]:
    return {t.site for t in case.targets if t.structure_type == StructureType.STATION}

def _lobes_from(case: Case) -> List[str]:
    return sorted({t.site for t in case.targets if t.structure_type == StructureType.LOBE})

def _sedation_lines(case: Case, kb: CodingKB) -> List[CodeLine]:
    lines: List[CodeLine] = []
    s = case.sedation
    if not s: return lines
    total = s.total_minutes or 0
    # CPT: do not report moderate sedation if <10 minutes
    if total < 10:
        return lines

    # Choose initial code by age and provider
    age = getattr(case, "patient_age_years", None)
    if s.provided_by_proceduralist:
        initial = "99151" if (age is not None and age < 5) else "99152"
        lines.append(CodeLine(
            code=initial,
            rationale=f"Moderate sedation by proceduralist {total} min; initial 15 min"
        ))
        # Additional units: each 15 min beyond 22 min threshold (i.e., 23–37 => 1, 38–52 => 2, …)
        addl = max(0, ceil(max(0, total - 22) / 15))
        for i in range(addl):
            lines.append(CodeLine(
                code="99153",
                rationale=f"Additional 15 min unit ({i+1})"
            ))
    else:
        initial = "99155" if (age is not None and age < 5) else "99156"
        lines.append(CodeLine(
            code=initial,
            rationale=f"Moderate sedation by different provider {total} min; initial 15 min"
        ))
        addl = max(0, ceil(max(0, total - 22) / 15))
        for i in range(addl):
            lines.append(CodeLine(
                code="99157",
                rationale=f"Additional 15 min unit ({i+1})"
            ))
    return lines

def _apply_bilateral_modifiers(lines: List[CodeLine], case: Case, kb: CodingKB) -> List[CodeLine]:
    """
    Add -50 when clearly bilateral and the code is eligible.
    Conservative defaults focus on pleural procedures; override via KB global_principles.bilateral_eligible_codes.
    """
    is_bilateral = bool(PATTERNS['bilateral'].search(case.report_text))
    if not is_bilateral:
        return lines
    elig = set(kb.bilateral_eligible_codes())
    for cl in lines:
        if cl.code == "31622":
            continue  # diagnostic bronch is inherently bilateral; do not append -50
        if cl.code in elig and "-50" not in cl.modifiers:
            cl.modifiers.append("-50")
    return lines

def code_case(case: Case, kb: CodingKB) -> CodeBundle:
    b = CodeBundle()
    procs = [i.proc_id for i in case.items]
    
    # Propagate extractor warnings into the bundle
    if case.parsing_warnings:
        b.warnings.extend(case.parsing_warnings)
    
    # Add any explicitly mentioned CPT codes
    if hasattr(case, 'explicit_cpts') and case.explicit_cpts:
        for cpt in case.explicit_cpts:
            # Look up the CPT in our KB to get description
            desc = kb.describe(cpt)
            if not desc:
                for p in kb.iter_procs():
                    if cpt in p.get("cpt", []):
                        desc = p.get("name", "")
                        break
            b.professional.append(CodeLine(
                code=cpt, 
                rationale="Explicitly documented in report",
                description=desc or f"CPT {cpt}"
            ))

    # Map procedures via KB (avoid duplicates with explicit codes)
    already_added = {cl.code for cl in b.professional}
    
    for pid in procs:
        # Skip dilation if stent is present (31631/31636 include dilation)
        if pid == "airway_dilation_only" and any(s in procs for s in ["tracheal_stent_insertion", "bronchial_stent_insertion"]):
            continue
            
        try:
            p = kb.find_proc(pid)
        except KeyError:
            continue  # Skip if not in KB
        # CPT/HCPCS listing
        for c in p.get("cpt", []) or p.get("hcpcs", []) or []:
            if c not in already_added:
                b.professional.append(CodeLine(
                    code=c, 
                    rationale=f"Detected {p['name']} via report/KB synonyms",
                    description=kb.describe(c) or p.get("name")
                ))
                already_added.add(c)
        # OPPS packaging notes
        opps = p.get("opps", {})
        if opps.get("packaged") or opps.get("status_indicator") == "N":
            b.opps_notes.append(opps.get("note") or "Add-on packaged under OPPS (SI=N).")

    # EBUS station counting (31652 vs 31653)
    if "ebus_tbna" in procs:
        st = _stations_from(case)
        # Remove any pre-added 31652/31653
        b.professional = [cl for cl in b.professional if cl.code not in ("31652","31653")]
        if len(st) >= 3:
            b.professional.append(CodeLine(code="31653", rationale=f"EBUS sampling of ≥3 stations: {sorted(st)}"))
        elif len(st) >= 1:
            b.professional.append(CodeLine(code="31652", rationale=f"EBUS sampling of 1–2 stations: {sorted(st)}"))
        else:
            # No stations documented - default to 31652 with warning
            b.professional.append(CodeLine(code="31652", rationale="EBUS-TBNA (stations not specified)"))
            b.documentation_gaps.append("List specific lymph node stations sampled (e.g., 4R, 7, 10L).")

    # TBLB lobes (31628 +31632 x additional)
    if "tblb_forceps_or_cryo" in procs:
        lobes = _lobes_from(case)
        b.professional = [cl for cl in b.professional if cl.code not in ("31628","+31632")]
        if lobes:
            b.professional.append(CodeLine(code="31628", rationale=f"TBLB first lobe {lobes[0]}"))
            addl = max(0, len(lobes) - 1)
            if addl:
                b.professional.append(CodeLine(code="+31632", quantity=addl,
                                  rationale=f"Additional lobe(s) beyond first: {addl}"))
        else:
            b.professional.append(CodeLine(code="31628", rationale="TBLB performed; lobe not specified"))
            b.documentation_gaps.append("Specify lobe(s) biopsied for TBLB (e.g., RUL).")
    
    # TBNA lobes (31629 +31633 x additional) - only if not EBUS-TBNA
    if "transbronchial_needle_aspiration" in procs and "ebus_tbna" not in procs:
        lobes = _lobes_from(case)
        b.professional = [cl for cl in b.professional if cl.code not in ("31629","+31633")]
        if lobes:
            b.professional.append(CodeLine(code="31629", rationale=f"TBNA first lobe {lobes[0]}"))
            addl = max(0, len(lobes) - 1)
            if addl:
                b.professional.append(CodeLine(code="+31633", quantity=addl,
                                  rationale=f"TBNA additional lobe(s): {addl}"))

    # Radial/diagnostic EBUS +31654 only if no linear sampling
    if "ebus_without_tbna" in procs or "radial_ebus_peripheral" in procs:
        # Check if already added to avoid duplication
        if not any(cl.code == "+31654" for cl in b.professional):
            if not any(cl.code in ("31652","31653") for cl in b.professional):
                b.professional.append(CodeLine(code="+31654", rationale="Radial EBUS for peripheral lesion"))

    # Navigation +31627 (packaged under OPPS per KB)
    if "nav_bronchoscopy" in procs:
        # Check if already added to avoid duplication
        if not any(cl.code == "+31627" for cl in b.professional):
            b.professional.append(CodeLine(code="+31627", rationale="Computer‑assisted navigation performed"))
            b.opps_notes.append("Navigation (+31627): Status Indicator N under OPPS—no separate facility payment.")

    # Thoracentesis and chest tubes (with/without imaging)
    text = case.report_text.lower()
    if "thoracentesis" in procs:
        guided = ("ultrasound" in text) or ("ct" in text) or ("fluoro" in text)
        b.professional.append(CodeLine(code=("32555" if guided else "32554"),
                               rationale=("Thoracentesis with imaging" if guided else "Thoracentesis without imaging")))
    if "pleural_drainage_catheter_non_tunneled" in procs:
        guided = ("ultrasound" in text) or ("ct" in text)
        b.professional.append(CodeLine(code=("32557" if guided else "32556"),
                               rationale=("Pleural drainage with imaging" if guided else "Pleural drainage without imaging")))
    if "ipc_tunneled_pleural_catheter" in procs:
        b.professional.append(CodeLine(code="32550", rationale="Tunneled pleural catheter (IPC) insertion"))

    # Chartis & valves basic guidance notes
    if "chartis_assessment" in procs:
        b.professional.append(CodeLine(code="31634", rationale="Balloon occlusion/Chartis CV assessment"))
    if "endobronchial_valves" in procs:
        b.professional.append(CodeLine(code="31647", rationale="Valve placement initial lobe"))
    
    # Stent procedures with proper CPT mapping
    if "tracheal_stent_insertion" in procs:
        # Check if already added to avoid duplication
        if not any(cl.code == "31631" for cl in b.professional):
            b.professional.append(CodeLine(code="31631", rationale="Tracheal stent placement"))
        # Remove any dilation-only code (31630) since 31631 includes dilation
        b.professional = [cl for cl in b.professional if cl.code != "31630"]
    
    if "bronchial_stent_insertion" in procs:
        # Check if already added to avoid duplication
        if not any(cl.code == "31636" for cl in b.professional):
            b.professional.append(CodeLine(code="31636", rationale="Bronchial stent placement first bronchus"))
            # TODO: Add logic to detect multiple distinct bronchi for +31637
            # For now, check if report mentions multiple bronchi
            if any(phrase in text for phrase in ["both mainstem", "bilateral stent", "two stent", "multiple stent"]):
                b.professional.append(CodeLine(code="+31637", quantity=1, rationale="Additional bronchial stent"))
        # Remove any dilation-only code
        b.professional = [cl for cl in b.professional if cl.code != "31630"]
    
    # Whole lung lavage
    if "whole_lung_lavage" in procs:
        b.professional.append(CodeLine(code="32997", rationale="Whole lung lavage"))
    
    # Airway dilation handled in KB processing above (skipped if stent present)
    
    # Tumor excision vs destruction
    if "tumor_excision_bronchoscopic" in procs:
        # Check if already added to avoid duplication
        if not any(cl.code == "31640" for cl in b.professional):
            b.professional.append(CodeLine(code="31640", rationale="Bronchoscopic tumor excision via snare + specimen"))
        # Suppress conflicting codes when excision is present
        b.professional = [cl for cl in b.professional if cl.code not in ("31641", "31631", "31636")]  # No destruction or stent codes
    elif "tumor_destruction_bronchoscopic" in procs:
        if not any(cl.code == "31641" for cl in b.professional):
            b.professional.append(CodeLine(code="31641", rationale="Bronchoscopic tumor destruction"))

    # Sedation lines
    b.professional.extend(_sedation_lines(case, kb))
    
    # Bilateral modifiers (apply -50 where appropriate)
    b.professional = _apply_bilateral_modifiers(b.professional, case, kb)
    
    # Fill in missing descriptions from KB (for sedation/add-ons, etc.)
    for cl in b.professional:
        if not cl.description:
            cl.description = kb.describe(cl.code)

    # Diagnostic bronchoscopy (31622) suppression per CPT:
    # 31622 is bundled when ANY other bronchoscopic primary code is reported.
    all_codes = [cl.code for cl in b.professional]
    if "31622" in all_codes:
        # Primaries that suppress 31622 (allow add-ons like +31627 and +31654 to coexist with 31622)
        suppressors = {
            "31623","31624","31625","31626","31628","31629","31630","31631","31633","31634",
            "31636","31640","31641","31643","31645","31646","31647","31651","31652","31653"
        }
        if any(c in suppressors for c in all_codes):
            b.professional = [cl for cl in b.professional if cl.code != "31622"]
            b.warnings.append("Diagnostic bronchoscopy (31622) suppressed—bundled into other bronchoscopy codes.")
    # refresh
    all_codes = [cl.code for cl in b.professional]
    
    # NCCI/compliance warnings & doc checks (high-level)
    if any(c in all_codes for c in ["31652","31653"]) and "31628" in all_codes:
        b.warnings.append("NCCI: Avoid 31628 with 31652/31653 for the same target; allow only if distinct targets (consider -59).")
    if "31634" in all_codes and any(c in all_codes for c in ["31647","31651"]):
        b.warnings.append("NCCI: Do not report 31634 with 31647/31651 in the same session.")

    # Documentation checks from KB - only check sedation if not under GA
    mins = kb.compliance.get("documentation_minimums", [])
    ga_present = bool(PATTERNS['general_anesthesia'].search(case.report_text)) if 'general_anesthesia' in PATTERNS else False
    
    if any("sedation" in m.lower() for m in mins) and not ga_present:
        if not case.sedation or not (case.sedation.start_time and case.sedation.end_time):
            b.documentation_gaps.append("Sedation start/stop times not documented.")
        if case.sedation and not case.sedation.independent_observer_documented:
            b.documentation_gaps.append("Independent trained observer for sedation not documented.")
    # Station documentation is now handled in EBUS section above

    # PCS suggestions (examples from KB)
    pcs = kb.gp.get("facility_vs_professional", {}).get("icd10_pcs_crosswalk_examples", {})
    
    # Excision takes precedence for PCS mapping
    if "31640" in all_codes:  # Tumor excision
        # Determine location - default to tracheal if not clearly bronchial
        if "trachea" in case.report_text.lower():
            b.icd10_pcs_suggestions.append(pcs.get("tracheal_excision", "0BB18ZZ"))
        else:
            b.icd10_pcs_suggestions.append(pcs.get("bronchial_excision", "0BBK8ZX"))
    elif "31631" in all_codes:  # Tracheal stent
        b.icd10_pcs_suggestions.append(pcs.get("tracheal_stent_insertion", "0BH18DZ"))
    elif "31636" in all_codes:  # Bronchial stent
        b.icd10_pcs_suggestions.append(pcs.get("bronchial_stent_insertion", "0BH48DZ"))
    elif "31622" in all_codes:  # Only if diagnostic bronch wasn't suppressed
        b.icd10_pcs_suggestions.append(pcs.get("bronchoscopy_inspection","0BJ08ZZ"))
    
    if any(c in all_codes for c in ["31652","31653"]):
        b.icd10_pcs_suggestions.append(pcs.get("mediastinal_lymph_node_ebus_tbna","07B74ZX"))
    
    if "32997" in all_codes:  # Whole lung lavage
        b.icd10_pcs_suggestions.append(pcs.get("whole_lung_lavage", "0B9K8ZZ"))

    return b