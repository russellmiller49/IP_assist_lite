"""Deterministic mapping to codes + OPPS/NCCI/doc checks, with bilateral support."""

from math import floor
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
    if total < 10 and not (s.start_time and s.end_time):
        return lines  # too short / undocumented

    if s.provided_by_proceduralist:
        lines.append(CodeLine(code="99152", rationale=f"Moderate sedation by proceduralist {total} min; initial 15 min"))
        addl = max(0, floor(max(0, total - 15) / 15))
        for i in range(addl):
            lines.append(CodeLine(code="99153", rationale=f"Additional 15 min unit ({i+1})"))
    else:
        lines.append(CodeLine(code="99155", rationale=f"Moderate sedation by different provider {total} min; initial 15 min"))
        addl = max(0, floor(max(0, total - 15) / 15))
        for i in range(addl):
            lines.append(CodeLine(code=("99156" if i == 0 else "99157"),
                                  rationale=f"Additional sedation time unit ({i+1})"))
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

    # Radial/diagnostic EBUS +31654 only if no linear sampling
    if "ebus_without_tbna" in procs:
        if not any(cl.code in ("31652","31653") for cl in b.professional):
            b.professional.append(CodeLine(code="+31654", rationale="Diagnostic/radial EBUS without linear TBNA"))

    # Navigation +31627 (packaged under OPPS per KB)
    if "nav_bronchoscopy" in procs:
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

    # Sedation lines
    b.professional.extend(_sedation_lines(case, kb))
    
    # Bilateral modifiers (apply -50 where appropriate)
    b.professional = _apply_bilateral_modifiers(b.professional, case, kb)
    
    # Fill in missing descriptions from KB (for sedation/add-ons, etc.)
    for cl in b.professional:
        if not cl.description:
            cl.description = kb.describe(cl.code)

    # NCCI/compliance warnings & doc checks (high-level)
    all_codes = [cl.code for cl in b.professional]
    if "31622" in all_codes and any(c in all_codes for c in ["31628","31629","31640","31641","31643","31645","31646","31647","31651"]):
        b.warnings.append("NCCI: Diagnostic bronchoscopy (31622) included in surgical bronchoscopy—remove 31622.")
    if any(c in all_codes for c in ["31652","31653"]) and "31628" in all_codes:
        b.warnings.append("NCCI: Avoid 31628 with 31652/31653 for the same target; allow only if distinct targets (consider -59).")
    if "31634" in all_codes and any(c in all_codes for c in ["31647","31651"]):
        b.warnings.append("NCCI: Do not report 31634 with 31647/31651 in the same session.")

    # Documentation checks from KB
    mins = kb.compliance.get("documentation_minimums", [])
    if any("sedation" in m.lower() for m in mins):
        if not case.sedation or not (case.sedation.start_time and case.sedation.end_time):
            b.documentation_gaps.append("Sedation start/stop times not documented.")
        if case.sedation and not case.sedation.independent_observer_documented:
            b.documentation_gaps.append("Independent trained observer for sedation not documented.")
    if any(c in all_codes for c in ["31652","31653"]) and not _stations_from(case):
        b.documentation_gaps.append("List specific lymph node stations (e.g., 4R, 7, 10L).")

    # PCS suggestions (examples from KB)
    pcs = kb.gp.get("facility_vs_professional", {}).get("icd10_pcs_crosswalk_examples", {})
    if any(c in all_codes for c in ["31622"]):
        b.icd10_pcs_suggestions.append(pcs.get("bronchoscopy_inspection","0BJ08ZZ"))
    if any(c in all_codes for c in ["31652","31653"]):
        b.icd10_pcs_suggestions.append(pcs.get("mediastinal_lymph_node_ebus_tbna","07B74ZX"))

    return b