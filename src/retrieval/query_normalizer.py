"""Query normalizer for medical terminology, typos, and abbreviations."""

import re
from dataclasses import dataclass
from typing import Dict, List, Set, Optional
from rapidfuzz import process, fuzz
import logging

logger = logging.getLogger(__name__)

WORD_RE = re.compile(r"[a-zA-Z\-]+")

@dataclass
class QueryNormalizer:
    """Normalize medical queries by fixing typos and expanding abbreviations."""
    
    vocab: Set[str]                # domain lexicon
    synonyms: Dict[str, List[str]] # canonical -> [synonyms]
    min_fuzzy: int = 85            # minimum fuzzy match score
    
    def expand_synonyms(self, query: str) -> str:
        """Expand abbreviations and synonyms to canonical forms."""
        q_low = " " + query.lower() + " "
        
        # Sort by length (longest first) to avoid partial replacements
        for canon, syns in self.synonyms.items():
            all_forms = sorted(set([canon] + syns), key=len, reverse=True)
            for form in all_forms:
                # Match with word boundaries
                pattern = rf"\b{re.escape(form)}\b"
                if re.search(pattern, q_low):
                    q_low = re.sub(pattern, canon, q_low)
                    
        return q_low.strip()
    
    def fuzzy_fix_tokens(self, query: str) -> str:
        """Fix typos using fuzzy matching against medical vocabulary."""
        words = query.split()
        fixed = []
        
        for word in words:
            word_lower = word.lower()
            
            # Skip if already in vocab
            if word_lower in self.vocab:
                fixed.append(word)
                continue
                
            # Try fuzzy matching
            if self.vocab:  # Only if vocab is loaded
                match = process.extractOne(word_lower, self.vocab, scorer=fuzz.ratio)
                if match and match[1] >= self.min_fuzzy:
                    logger.debug(f"Fuzzy corrected: {word} -> {match[0]} (score: {match[1]})")
                    fixed.append(match[0])
                else:
                    fixed.append(word)
            else:
                fixed.append(word)
                
        return " ".join(fixed)
    
    def normalize(self, query: str) -> str:
        """Full normalization pipeline."""
        # First expand synonyms/abbreviations
        expanded = self.expand_synonyms(query)
        
        # Then fix typos
        corrected = self.fuzzy_fix_tokens(expanded)
        
        logger.info(f"Query normalized: '{query}' -> '{corrected}'")
        return corrected


def load_medical_synonyms() -> Dict[str, List[str]]:
    """Load medical synonyms and abbreviations."""
    return {
        "tracheoesophageal fistula": [
            "tef", "te fistula", "tracheo-esophageal fistula",
            "tracheo oesophageal fistula", "tracheo esophageal fistula",
            "esophagorespiratory fistula", "bronchoesophageal fistula",
            "tracheoesophageal fistulae", "t-e fistula"
        ],
        "benign": [
            "nonmalignant", "non-malignant", "acquired non-malignant",
            "non malignant", "nonneoplastic", "non-neoplastic"
        ],
        "malignant": [
            "neoplastic", "cancerous", "tumor-related", "cancer-related"
        ],
        "stent": [
            "airway stent", "tracheal stent", "esophageal stent",
            "self-expanding metallic stent", "sems", "covered stent"
        ],
        "endobronchial ultrasound": [
            "ebus", "ebus-tbna", "linear ebus", "radial ebus", "r-ebus"
        ],
        "transbronchial needle aspiration": [
            "tbna", "ebus-tbna", "eus-fna", "needle aspiration"
        ],
        "electromagnetic navigation bronchoscopy": [
            "enb", "em navigation", "navigational bronchoscopy"
        ],
        "bronchoscopic lung volume reduction": [
            "blvr", "lung volume reduction", "valve therapy"
        ],
        "chronic obstructive pulmonary disease": [
            "copd", "emphysema", "chronic bronchitis"
        ],
        "photodynamic therapy": [
            "pdt", "phototherapy", "light therapy"
        ],
        "argon plasma coagulation": [
            "apc", "argon coagulation", "plasma coagulation"
        ],
        "foreign body": [
            "fb", "aspirated object", "inhaled object"
        ],
        "massive hemoptysis": [
            "life-threatening hemoptysis", "major hemoptysis", 
            "severe hemoptysis", "massive bleeding"
        ],
        "closure": [
            "occlusion", "sealing", "repair", "obliteration"
        ],
        "management": [
            "treatment", "therapy", "intervention", "approach"
        ],
        "complications": [
            "adverse events", "adverse effects", "side effects"
        ],
        "contraindications": [
            "contraindication", "absolute contraindication",
            "relative contraindication", "cautions"
        ],
        "fiducial": [
            "fiducial marker", "fiducials", "marker", "gold marker"
        ],
        "ablation": [
            "thermal ablation", "microwave ablation", "radiofrequency ablation",
            "rfa", "mwa", "cryoablation", "cryo"
        ]
    }


def load_medical_vocab() -> Set[str]:
    """Load medical vocabulary for fuzzy matching."""
    # Start with common medical terms
    base_vocab = {
        "tracheoesophageal", "fistula", "benign", "malignant", "stent",
        "bronchoscopy", "endobronchial", "ultrasound", "transbronchial",
        "aspiration", "biopsy", "ablation", "microwave", "radiofrequency",
        "cryotherapy", "photodynamic", "therapy", "argon", "plasma",
        "coagulation", "electromagnetic", "navigation", "fiducial",
        "marker", "hemoptysis", "pneumothorax", "emphysema", "copd",
        "asthma", "bronchiectasis", "stenosis", "stricture", "obstruction",
        "tumor", "carcinoma", "adenocarcinoma", "squamous", "metastasis",
        "lymph", "node", "mediastinal", "hilar", "peripheral", "central",
        "airway", "trachea", "bronchus", "bronchi", "esophagus", "lung",
        "pleura", "pleural", "effusion", "empyema", "thoracentesis",
        "pleurodesis", "chest", "tube", "drainage", "valve", "coil",
        "management", "treatment", "intervention", "procedure", "technique",
        "complication", "contraindication", "indication", "sedation",
        "anesthesia", "fluoroscopy", "computed", "tomography", "magnetic",
        "resonance", "imaging", "positron", "emission", "radiotherapy"
    }
    
    # Could load from file if available
    import pathlib
    vocab_file = pathlib.Path("data/lexicon/medical_terms.txt")
    if vocab_file.exists():
        file_vocab = {line.strip().lower() 
                     for line in vocab_file.read_text().splitlines() 
                     if line.strip()}
        return base_vocab | file_vocab
    
    return base_vocab


# Create a singleton normalizer
_normalizer: Optional[QueryNormalizer] = None

def get_normalizer() -> QueryNormalizer:
    """Get or create the singleton query normalizer."""
    global _normalizer
    if _normalizer is None:
        _normalizer = QueryNormalizer(
            vocab=load_medical_vocab(),
            synonyms=load_medical_synonyms(),
            min_fuzzy=85
        )
    return _normalizer