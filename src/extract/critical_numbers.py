"""
Critical number and pattern extraction for medical content
Includes devices, CPT/wRVU, energy settings, complications, etc.
"""
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field


# Comprehensive patterns for critical medical information
CRITICAL_PATTERNS = {
    # Devices & systems
    "valve_brand": r"\b(zephyr|spiration)\b",
    "chartis": r"\bchartis\b",
    "navigation_system": r"\b(enb|electromagnetic navigation|vbn|virtual bronchoscopic navigation|btpna)\b",
    
    # CPT / wRVU / Billing
    "cpt_code": r"\b(?:(?:\+)?\s?)(\d{5})\b",
    "wRVU": r"\b(?:w?RVU|relative value unit)s?\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)",
    "global_period": r"\b(\d{1,3})\s*day\s+global\b",
    
    # Ablation / PDT parameters  
    "pdt_params": r"\b(630\s*nm|200\s*J/cm)\b",
    "energy_settings": r"(\d+(?:\.\d+)?)\s*(?:W|watts)",
    "ablation_duration": r"(\d+(?:\.\d+)?)\s*(?:seconds?|minutes?)\s+(?:ablation|treatment)",
    "temperature": r"(\d+)\s*°?[CF]\b",
    
    # BLVR selection criteria
    "collateral_ventilation": r"\bcollateral ventilation\b|\bfissure (?:integrity|completeness)\b",
    "fissure_integrity": r"(\d+(?:\.\d+)?)\s*%\s*(?:fissure|intact)",
    "tlv_reduction": r"(\d+(?:\.\d+)?)\s*%\s*(?:TLV|target lobe volume)",
    
    # Complications/risks
    "percent_risk": r"(\d+(?:\.\d+)?)\s*%.*?\b(risk|incidence|rate|complication|mortality|morbidity)\b",
    "pneumothorax_rate": r"pneumothorax.*?(\d+(?:\.\d+)?)\s*%",
    "bleeding_rate": r"(?:bleeding|hemorrhage|hemoptysis).*?(\d+(?:\.\d+)?)\s*%",
    "air_leak_threshold": r"prolonged air leak.*?(?:beyond|over|more than)\s*(\d+)\s*days",
    
    # Equipment specifications
    "needle_gauge": r"\b(\d{1,2})\s*G(?:auge)?\b|\b(\d{1,2})-?\s*gauge\b",
    "scope_diameter": r"\b(\d+(?:\.\d+)?)\s*mm\s*(?:scope|bronchoscope|diameter)\b",
    "stent_dimensions": r"\b(\d+)\s*x\s*(\d+)\s*mm\b",
    "catheter_french": r"\b(\d+)\s*F(?:rench|r)?\b",
    
    # Procedural numbers
    "procedure_time": r"(?:procedure|operative)\s+time.*?(\d+(?:\.\d+)?)\s*(?:minutes?|hours?)",
    "hospital_stay": r"(?:length of stay|LOS|hospital stay).*?(\d+(?:\.\d+)?)\s*days",
    "follow_up_period": r"follow[- ]?up.*?(\d+)\s*(?:days?|weeks?|months?|years?)",
    
    # Fiducial markers
    "fiducial_count": r"\b(\d+)[-\s]?(?:to|–)[-\s]?(\d+)\s*(?:fiducial|marker)s?\b",
    "fiducial_spacing": r"(\d+(?:\.\d+)?)\s*(?:to|–)\s*(\d+(?:\.\d+)?)\s*cm\s*(?:apart|spacing)",
    
    # Training/competency numbers
    "training_cases": r"(\d+)\s*(?:supervised|cases?|procedures?)\s*(?:to achieve|for|until)\s*competenc",
    "maintenance_volume": r"(\d+)\s*(?:cases?|procedures?)\s*/\s*(?:year|annually)",
}

# Safety-specific patterns  
SAFETY_PATTERNS = {
    "sems_benign_warning": r"\b(?:uncovered metal stent|SEMS).{0,50}(benign|resectable).{0,50}(contraindicat|avoid|not recommended)",
    "pdt_precautions": r"photosensitivit(?:y|ies)|skin.*eye protection|up to\s*(\d+)\s*weeks",
    "balloon_tamponade": r"\b(balloon (?:occlusion|tamponade))\b",
    "coagulopathy_warning": r"(?:coagulopathy|INR|anticoagula).{0,30}(contraindicat|defer|correct|hold)",
    "pregnancy_warning": r"pregnan(?:cy|t).{0,30}(contraindicat|avoid|defer|risk)",
}


@dataclass
class ExtractedInfo:
    """Container for extracted critical information."""
    devices: List[str] = field(default_factory=list)
    cpt_codes: List[str] = field(default_factory=list)
    wrvus: List[float] = field(default_factory=list)
    energy_settings: List[str] = field(default_factory=list)
    complications: List[Tuple[str, float]] = field(default_factory=list)  # (type, rate)
    equipment_specs: Dict[str, Any] = field(default_factory=dict)
    procedural_numbers: Dict[str, Any] = field(default_factory=dict)
    safety_flags: List[str] = field(default_factory=list)
    fiducial_info: Dict[str, Any] = field(default_factory=dict)
    training_requirements: Dict[str, Any] = field(default_factory=dict)
    blvr_criteria: Dict[str, Any] = field(default_factory=dict)


class CriticalNumberExtractor:
    """Extract critical numbers and patterns from medical text."""
    
    def extract(self, text: str) -> ExtractedInfo:
        """Extract all critical information from text."""
        info = ExtractedInfo()
        
        # Extract devices
        info.devices = self._extract_devices(text)
        
        # Extract CPT codes and wRVUs
        info.cpt_codes = self._extract_cpt_codes(text)
        info.wrvus = self._extract_wrvus(text)
        
        # Extract energy/ablation settings
        info.energy_settings = self._extract_energy_settings(text)
        
        # Extract complications
        info.complications = self._extract_complications(text)
        
        # Extract equipment specifications
        info.equipment_specs = self._extract_equipment_specs(text)
        
        # Extract procedural numbers
        info.procedural_numbers = self._extract_procedural_numbers(text)
        
        # Extract safety flags
        info.safety_flags = self._extract_safety_flags(text)
        
        # Extract fiducial information
        info.fiducial_info = self._extract_fiducial_info(text)
        
        # Extract training requirements
        info.training_requirements = self._extract_training_requirements(text)
        
        # Extract BLVR criteria
        info.blvr_criteria = self._extract_blvr_criteria(text)
        
        return info
    
    def _extract_devices(self, text: str) -> List[str]:
        """Extract device brands and systems."""
        devices = []
        text_lower = text.lower()
        
        # Valve brands
        for match in re.finditer(CRITICAL_PATTERNS["valve_brand"], text_lower):
            devices.append(match.group(1).title())
        
        # Chartis system
        if re.search(CRITICAL_PATTERNS["chartis"], text_lower):
            devices.append("Chartis")
        
        # Navigation systems
        nav_matches = re.findall(CRITICAL_PATTERNS["navigation_system"], text_lower)
        for match in nav_matches:
            if "enb" in match or "electromagnetic" in match:
                devices.append("ENB")
            elif "vbn" in match or "virtual" in match:
                devices.append("VBN")
            elif "btpna" in match:
                devices.append("BTPNA")
        
        return list(set(devices))
    
    def _extract_cpt_codes(self, text: str) -> List[str]:
        """Extract CPT codes."""
        codes = []
        for match in re.finditer(CRITICAL_PATTERNS["cpt_code"], text):
            code = match.group(1)
            # Validate CPT code format (5 digits, typically starts with certain ranges)
            if len(code) == 5 and code.isdigit():
                codes.append(code)
        return list(set(codes))
    
    def _extract_wrvus(self, text: str) -> List[float]:
        """Extract wRVU values."""
        wrvus = []
        for match in re.finditer(CRITICAL_PATTERNS["wRVU"], text, re.I):
            try:
                value = float(match.group(1))
                if 0 < value < 100:  # Reasonable range for wRVUs
                    wrvus.append(value)
            except ValueError:
                continue
        return list(set(wrvus))
    
    def _extract_energy_settings(self, text: str) -> List[str]:
        """Extract energy and ablation settings."""
        settings = []
        
        # Energy in watts
        for match in re.finditer(CRITICAL_PATTERNS["energy_settings"], text, re.I):
            settings.append(f"{match.group(1)}W")
        
        # PDT parameters
        for match in re.finditer(CRITICAL_PATTERNS["pdt_params"], text, re.I):
            settings.append(match.group(1))
        
        # Temperature settings
        for match in re.finditer(CRITICAL_PATTERNS["temperature"], text):
            temp = match.group(0)
            if any(keyword in text[max(0, match.start()-50):match.end()+50].lower() 
                   for keyword in ["ablation", "cryo", "freeze", "heat"]):
                settings.append(temp)
        
        return list(set(settings))
    
    def _extract_complications(self, text: str) -> List[Tuple[str, float]]:
        """Extract complication rates."""
        complications = []
        
        # General complications with percentages
        for match in re.finditer(CRITICAL_PATTERNS["percent_risk"], text, re.I):
            try:
                rate = float(match.group(1))
                comp_type = match.group(2)
                
                # Look for specific complication type in surrounding text
                context = text[max(0, match.start()-100):match.end()+50].lower()
                
                if "pneumothorax" in context:
                    complications.append(("pneumothorax", rate))
                elif any(term in context for term in ["bleeding", "hemorrhage", "hemoptysis"]):
                    complications.append(("bleeding", rate))
                elif "mortality" in context:
                    complications.append(("mortality", rate))
                elif "morbidity" in context:
                    complications.append(("morbidity", rate))
                else:
                    complications.append((comp_type, rate))
            except ValueError:
                continue
        
        # Specific pneumothorax rate
        for match in re.finditer(CRITICAL_PATTERNS["pneumothorax_rate"], text, re.I):
            try:
                rate = float(match.group(1))
                complications.append(("pneumothorax", rate))
            except ValueError:
                continue
        
        # Bleeding rate
        for match in re.finditer(CRITICAL_PATTERNS["bleeding_rate"], text, re.I):
            try:
                rate = float(match.group(1))
                complications.append(("bleeding", rate))
            except ValueError:
                continue
        
        return list(set(complications))
    
    def _extract_equipment_specs(self, text: str) -> Dict[str, Any]:
        """Extract equipment specifications."""
        specs = {}
        
        # Needle gauge
        for match in re.finditer(CRITICAL_PATTERNS["needle_gauge"], text):
            gauge = match.group(1) or match.group(2)
            if gauge:
                specs["needle_gauge"] = f"{gauge}G"
        
        # Scope diameter
        for match in re.finditer(CRITICAL_PATTERNS["scope_diameter"], text):
            specs["scope_diameter"] = f"{match.group(1)}mm"
        
        # Stent dimensions
        for match in re.finditer(CRITICAL_PATTERNS["stent_dimensions"], text):
            specs["stent_dimensions"] = f"{match.group(1)}x{match.group(2)}mm"
        
        # Catheter size
        for match in re.finditer(CRITICAL_PATTERNS["catheter_french"], text):
            specs["catheter_size"] = f"{match.group(1)}Fr"
        
        return specs
    
    def _extract_procedural_numbers(self, text: str) -> Dict[str, Any]:
        """Extract procedural timing and duration."""
        numbers = {}
        
        # Procedure time
        for match in re.finditer(CRITICAL_PATTERNS["procedure_time"], text, re.I):
            numbers["procedure_time"] = match.group(1)
        
        # Hospital stay
        for match in re.finditer(CRITICAL_PATTERNS["hospital_stay"], text, re.I):
            numbers["hospital_stay"] = f"{match.group(1)} days"
        
        # Follow-up period
        for match in re.finditer(CRITICAL_PATTERNS["follow_up_period"], text, re.I):
            numbers["follow_up"] = match.group(0)
        
        # Air leak threshold
        for match in re.finditer(CRITICAL_PATTERNS["air_leak_threshold"], text, re.I):
            numbers["air_leak_threshold"] = f"{match.group(1)} days"
        
        return numbers
    
    def _extract_safety_flags(self, text: str) -> List[str]:
        """Extract safety warnings and contraindications."""
        flags = []
        
        for pattern_name, pattern in SAFETY_PATTERNS.items():
            if re.search(pattern, text, re.I):
                flags.append(pattern_name.replace("_", " ").title())
        
        return flags
    
    def _extract_fiducial_info(self, text: str) -> Dict[str, Any]:
        """Extract fiducial marker specifications."""
        info = {}
        
        # Fiducial count
        for match in re.finditer(CRITICAL_PATTERNS["fiducial_count"], text, re.I):
            info["count"] = f"{match.group(1)}-{match.group(2)}"
        
        # Spacing
        for match in re.finditer(CRITICAL_PATTERNS["fiducial_spacing"], text, re.I):
            info["spacing"] = f"{match.group(1)}-{match.group(2)} cm"
        
        # Check for non-collinear requirement
        if re.search(r"non[- ]?collinear", text, re.I):
            info["arrangement"] = "non-collinear"
        
        return info
    
    def _extract_training_requirements(self, text: str) -> Dict[str, Any]:
        """Extract training and competency requirements."""
        reqs = {}
        
        # Training cases to competency
        for match in re.finditer(CRITICAL_PATTERNS["training_cases"], text, re.I):
            reqs["cases_to_competency"] = int(match.group(1))
        
        # Maintenance volume
        for match in re.finditer(CRITICAL_PATTERNS["maintenance_volume"], text, re.I):
            reqs["annual_maintenance"] = int(match.group(1))
        
        return reqs
    
    def _extract_blvr_criteria(self, text: str) -> Dict[str, Any]:
        """Extract BLVR eligibility criteria."""
        criteria = {}
        
        # Collateral ventilation assessment
        if re.search(CRITICAL_PATTERNS["collateral_ventilation"], text, re.I):
            criteria["collateral_ventilation_assessment"] = True
        
        # Fissure integrity
        for match in re.finditer(CRITICAL_PATTERNS["fissure_integrity"], text, re.I):
            criteria["fissure_integrity"] = f"{match.group(1)}%"
        
        # TLV reduction target
        for match in re.finditer(CRITICAL_PATTERNS["tlv_reduction"], text, re.I):
            criteria["tlv_reduction_target"] = f"{match.group(1)}%"
        
        return criteria