# SPDX-License-Identifier: MIT
from __future__ import annotations
from typing import Dict, Any, List, Set
from .schema import ExtractedCase

class AdaptedExtraction:
    """
    Thin adapter layer that converts LLM JSON into
    your coder's 'performed items' & context flags.
    """
    def __init__(self):
        self.performed_items: Set[str] = set()
        self.devices_implants: List[str] = []
        self.flags: Dict[str, Any] = {
            "general_anesthesia": False,
            "moderate_sedation": False,
            "airway": "unknown",
            "ebus_stations": set(),  # a set of station labels
        }

    def to_dict(self) -> Dict[str, Any]:
        d = dict(self.flags)
        d["performed_items"] = sorted(self.performed_items)
        d["devices_implants"] = list(self.devices_implants)
        d["ebus_stations"] = sorted(d["ebus_stations"])
        return d

def _normalize_site_detail(s: str | None) -> str | None:
    return s.strip() if s else None

def adapt(case: ExtractedCase) -> AdaptedExtraction:
    """
    Convert ExtractedCase from LLM into performed items and flags
    that match the existing coder's expectations.
    """
    out = AdaptedExtraction()

    # Anesthesia flags
    out.flags["general_anesthesia"] = bool(case.anesthesia.general)
    out.flags["moderate_sedation"] = bool(case.anesthesia.moderate)
    out.flags["airway"] = case.anesthesia.airway

    # EBUS stations
    out.flags["ebus_stations"] = set(case.ebus.stations_sampled or [])

    # Stent logic: only if actually placed
    if case.stent.placed:
        loc = (case.stent.location or "unknown").lower()
        if case.stent.brand:
            out.devices_implants.append(case.stent.brand)
        if case.stent.size:
            out.devices_implants.append(case.stent.size)

        if loc == "trachea":
            out.performed_items.add("tracheal_stent_insertion")
        elif loc == "bronchus" or loc == "both":
            out.performed_items.add("bronchial_stent_insertion")
            # If "both", might need to add tracheal as well
            if loc == "both":
                out.performed_items.add("tracheal_stent_insertion")

    # Procedures
    for p in case.procedures:
        action = p.action
        site = p.site
        method = (p.details or {}).get("method", "").lower()
        site_detail = _normalize_site_detail(p.site_detail)

        if action == "wll":
            out.performed_items.add("whole_lung_lavage")
            continue

        if action == "stent_insertion":
            # Redundant if stent.placed, but keep for extra robustness:
            if site == "trachea":
                out.performed_items.add("tracheal_stent_insertion")
            elif site in ("bronchus", "lobe", "unknown"):
                out.performed_items.add("bronchial_stent_insertion")
            continue

        if action == "dilation":
            out.performed_items.add("airway_dilation_only")
            continue

        if action == "excision":
            # Snare/polypectomy with specimens
            out.performed_items.add("tumor_excision_bronchoscopic")
            continue

        if action == "destruction":
            out.performed_items.add("tumor_destruction_bronchoscopic")
            continue

        if action == "radial_ebus":
            out.performed_items.add("ebus_without_tbna")
            continue

        if action == "ebus_tbna":
            # Linear EBUS TBNA
            out.performed_items.add("ebus_tbna")
            # Stations already captured in flags["ebus_stations"]
            continue

        if action == "biopsy":
            # Map to appropriate biopsy type based on site
            if site == "lobe":
                out.performed_items.add("tblb_forceps_or_cryo")
            else:
                # Generic biopsy - could be mapped to specific types
                # For now, we'll skip unless you have specific mapping
                pass

    return out