"""
Contraindication extraction for medical procedures
"""
import re
from typing import List, Dict, Any
from dataclasses import dataclass


@dataclass
class Contraindication:
    """Represents a contraindication."""
    condition: str
    severity: str  # absolute, relative, caution
    context: str
    procedure: str = ""


class ContraindicationExtractor:
    """Extract contraindications from medical text."""
    
    # Patterns for contraindication detection
    CONTRAINDICATION_PATTERNS = {
        "absolute": [
            r"absolute(?:ly)?\s+contraindicat",
            r"must\s+not\s+(?:be\s+)?(?:perform|use)",
            r"strictly\s+(?:avoid|prohibited)",
            r"never\s+(?:perform|use)",
        ],
        "relative": [
            r"relative(?:ly)?\s+contraindicat",
            r"should\s+(?:be\s+)?avoid",
            r"generally\s+(?:not\s+)?recommend",
            r"use\s+with\s+caution",
            r"defer\s+(?:until|unless)",
        ],
        "caution": [
            r"caution\s+(?:should\s+be|is)\s+(?:exercised|advised)",
            r"careful(?:ly)?\s+consider",
            r"risk[- ]benefit\s+(?:analysis|assessment)",
        ]
    }
    
    # Specific medical conditions that are contraindications
    CONDITION_PATTERNS = {
        "coagulopathy": r"(?:uncorrected\s+)?coagulopathy|bleeding\s+diathesis|INR\s*>\s*\d+(?:\.\d+)?",
        "thrombocytopenia": r"thrombocytopenia|platelet(?:s)?\s*<\s*\d+",
        "anticoagulation": r"(?:therapeutic\s+)?anticoagulat|warfarin|heparin|DOAC|NOAC",
        "pregnancy": r"pregnan(?:cy|t)",
        "hemodynamic_instability": r"hemodynamic(?:ally)?\s+(?:unstable|instability)",
        "respiratory_failure": r"(?:severe\s+)?respiratory\s+failure|hypox(?:ia|emia)",
        "increased_icp": r"(?:increased|elevated)\s+(?:intracranial\s+)?(?:ICP|pressure)",
        "facial_trauma": r"facial\s+(?:trauma|fracture)|maxillofacial\s+injury",
        "cervical_spine": r"cervical\s+spine\s+(?:injury|instability|fracture)",
        "benign_stenosis": r"benign\s+(?:tracheal\s+)?stenosis|resectable\s+(?:disease|lesion)",
        "infection": r"active\s+(?:infection|tuberculosis)|untreated\s+(?:infection|abscess)",
        "myocardial_infarction": r"(?:recent\s+)?(?:MI|myocardial\s+infarction)|acute\s+coronary",
        "pulmonary_hypertension": r"(?:severe\s+)?pulmonary\s+hypertension|PAH",
    }
    
    # Procedure-specific contraindications
    PROCEDURE_CONTRAINDICATIONS = {
        "bronchoscopy": ["coagulopathy", "thrombocytopenia", "hemodynamic_instability"],
        "ebus": ["coagulopathy", "anticoagulation", "pulmonary_hypertension"],
        "rigid_bronchoscopy": ["cervical_spine", "facial_trauma", "increased_icp"],
        "sems": ["benign_stenosis"],
        "blvr": ["active_infection", "pulmonary_hypertension"],
        "pdt": ["porphyria", "photosensitivity"],
        "percutaneous_tracheostomy": ["coagulopathy", "cervical_spine", "infection"],
    }
    
    def extract(self, text: str) -> List[Contraindication]:
        """Extract contraindications from text."""
        contraindications = []
        
        # Find contraindication statements
        for severity, patterns in self.CONTRAINDICATION_PATTERNS.items():
            for pattern in patterns:
                for match in re.finditer(pattern, text, re.I):
                    # Extract context around match
                    start = max(0, match.start() - 200)
                    end = min(len(text), match.end() + 200)
                    context = text[start:end]
                    
                    # Look for specific conditions
                    conditions = self._extract_conditions(context)
                    
                    # Identify procedure if mentioned
                    procedure = self._identify_procedure(context)
                    
                    for condition in conditions:
                        contraindications.append(
                            Contraindication(
                                condition=condition,
                                severity=severity,
                                context=context.strip(),
                                procedure=procedure
                            )
                        )
        
        # Also look for condition-first patterns
        contraindications.extend(self._extract_condition_first_patterns(text))
        
        return contraindications
    
    def _extract_conditions(self, context: str) -> List[str]:
        """Extract medical conditions from context."""
        conditions = []
        
        for condition_name, pattern in self.CONDITION_PATTERNS.items():
            if re.search(pattern, context, re.I):
                conditions.append(condition_name.replace("_", " "))
        
        return conditions
    
    def _identify_procedure(self, context: str) -> str:
        """Identify the procedure being discussed."""
        procedures = {
            "bronchoscopy": r"\bbronchoscop",
            "ebus": r"\bEBUS\b|endobronchial\s+ultrasound",
            "rigid_bronchoscopy": r"\brigid\s+bronchoscop",
            "sems": r"\bSEMS\b|self[- ]expanding\s+metal(?:lic)?\s+stent",
            "blvr": r"\bBLVR\b|bronchoscopic\s+lung\s+volume",
            "pdt": r"\bPDT\b|photodynamic\s+therapy",
            "percutaneous_tracheostomy": r"percutaneous\s+(?:dilational\s+)?tracheostomy",
            "ablation": r"ablation|radiofrequency|microwave|cryo",
        }
        
        for proc_name, pattern in procedures.items():
            if re.search(pattern, context, re.I):
                return proc_name
        
        return ""
    
    def _extract_condition_first_patterns(self, text: str) -> List[Contraindication]:
        """Extract patterns where condition comes before contraindication mention."""
        contraindications = []
        
        # Pattern: "Coagulopathy is a contraindication to..."
        pattern = r"(\w+(?:\s+\w+)?)\s+(?:is|are|remains?)\s+(?:a|an)?\s*(?:absolute|relative)?\s*contraindicat"
        
        for match in re.finditer(pattern, text, re.I):
            condition = match.group(1)
            severity = "relative"  # Default
            
            if "absolute" in match.group(0).lower():
                severity = "absolute"
            
            # Get wider context
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 100)
            context = text[start:end]
            
            procedure = self._identify_procedure(context)
            
            contraindications.append(
                Contraindication(
                    condition=condition,
                    severity=severity,
                    context=context.strip(),
                    procedure=procedure
                )
            )
        
        return contraindications
    
    def get_structured_contraindications(self, text: str) -> Dict[str, List[Dict]]:
        """Get contraindications organized by procedure."""
        contraindications = self.extract(text)
        
        structured = {}
        for contra in contraindications:
            proc = contra.procedure or "general"
            
            if proc not in structured:
                structured[proc] = []
            
            structured[proc].append({
                "condition": contra.condition,
                "severity": contra.severity,
                "context": contra.context[:200] + "..." if len(contra.context) > 200 else contra.context
            })
        
        return structured