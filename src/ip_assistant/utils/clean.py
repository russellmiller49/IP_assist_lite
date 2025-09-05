"""
Robust text cleaner for medical literature
Handles ligatures, publisher artifacts, and double expansions
"""
import re
import unicodedata
from typing import Optional

# Map of common ligatures and publisher artifacts to clean text
LIGATURE_MAP = {
    r"/uniFB01": "fi",
    r"/uniFB02": "fl", 
    r"/uniFB03": "ffi",
    r"/uniFB04": "ffl",
    r"/C21": "",
    r"/C14": "",
    r"/C15": "",
    r"/C23": "",
    r"/C210": "",
    r"/C211": "",
    # Additional unicode ligatures
    "\ufb01": "fi",  # Direct unicode ligature
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\ufb05": "st",
    "\ufb06": "st",
}

# Patterns for collapsing doubled abbreviation expansions
ABBREV_COLLAPSE = [
    # EBUS patterns
    (r"\b(?:endobronchial ultrasound)\s*\(\s*endobronchial ultrasound\s*\(EBUS\)\s*\)", 
     "endobronchial ultrasound (EBUS)", re.I),
    (r"\b(?:endobronchial ultrasound)\s*\(EBUS\)\s*\(\s*TBNA\)", 
     "endobronchial ultrasound (EBUS) TBNA", re.I),
    # Additional common medical abbreviation collapses
    (r"\b(?:computed tomography)\s*\(\s*computed tomography\s*\(CT\)\s*\)",
     "computed tomography (CT)", re.I),
    (r"\b(?:magnetic resonance imaging)\s*\(\s*magnetic resonance imaging\s*\(MRI\)\s*\)",
     "magnetic resonance imaging (MRI)", re.I),
    (r"\b(?:positron emission tomography)\s*\(\s*positron emission tomography\s*\(PET\)\s*\)",
     "positron emission tomography (PET)", re.I),
    # IP-specific patterns
    (r"\b(?:bronchoscopic lung volume reduction)\s*\(\s*bronchoscopic lung volume reduction\s*\(BLVR\)\s*\)",
     "bronchoscopic lung volume reduction (BLVR)", re.I),
    (r"\b(?:electromagnetic navigation bronchoscopy)\s*\(\s*electromagnetic navigation bronchoscopy\s*\(ENB\)\s*\)",
     "electromagnetic navigation bronchoscopy (ENB)", re.I),
]

def normalize_text(s: Optional[str]) -> str:
    """
    Normalize text by cleaning ligatures, publisher artifacts, and formatting issues.
    
    Args:
        s: Input text string
        
    Returns:
        Cleaned and normalized text
    """
    if not s:
        return ""
    
    # Unicode normalization (NFKC = compatibility decomposition + canonical composition)
    s = unicodedata.normalize("NFKC", s)
    
    # Replace ligatures and publisher artifacts
    for pattern, replacement in LIGATURE_MAP.items():
        s = s.replace(pattern, replacement)
    
    # De-hyphenate line breaks (words split across lines)
    s = re.sub(r"(\w)-\n(\w)", r"\1\2", s)
    
    # Clean up whitespace before newlines
    s = re.sub(r"\s+\n", "\n", s)
    
    # Collapse multiple newlines (max 2)
    s = re.sub(r"\n{3,}", "\n\n", s)
    
    # Collapse doubled abbreviation expansions
    for pattern, replacement, flags in ABBREV_COLLAPSE:
        s = re.sub(pattern, replacement, s, flags=flags)
    
    # Normalize multiple spaces to single space
    s = re.sub(r"\s{2,}", " ", s)
    
    # Remove empty brackets/references
    s = re.sub(r"\[\s*\]", "", s)
    
    # Remove common PDF extraction artifacts
    s = re.sub(r"(?:Page \d+ of \d+)", "", s)
    s = re.sub(r"(?:\d+\s*\|\s*P a g e)", "", s)
    
    # Clean up special characters that often appear as artifacts
    s = re.sub(r"[^\x00-\x7F\u0080-\uFFFF]+", "", s)  # Remove non-standard unicode
    
    # Fix common OCR/extraction issues
    s = re.sub(r"\bfi(?:gure|g\.?)\s*(\d+)", r"Figure \1", s, flags=re.I)
    s = re.sub(r"\btable\s*(\d+)", r"Table \1", s, flags=re.I)
    
    # Remove leading/trailing whitespace
    s = s.strip()
    
    return s


def clean_table_cell(cell: str) -> str:
    """
    Special cleaning for table cells which often have more artifacts.
    
    Args:
        cell: Table cell content
        
    Returns:
        Cleaned cell content
    """
    if not cell:
        return ""
    
    # Apply general normalization
    cell = normalize_text(cell)
    
    # Remove common table artifacts
    cell = re.sub(r"^\s*[-–—]\s*$", "", cell)  # Cells with just dashes
    cell = re.sub(r"^\s*[nN]/[aA]\s*$", "", cell)  # N/A cells
    cell = re.sub(r"^\s*\.\s*$", "", cell)  # Cells with just periods
    
    return cell.strip()


def clean_section_title(title: str) -> str:
    """
    Clean section titles which often have special formatting.
    
    Args:
        title: Section title
        
    Returns:
        Cleaned title
    """
    if not title:
        return ""
    
    # Apply general normalization
    title = normalize_text(title)
    
    # Remove numbering patterns
    title = re.sub(r"^\d+\.?\s*", "", title)  # Leading numbers
    title = re.sub(r"^[IVX]+\.?\s*", "", title)  # Roman numerals
    title = re.sub(r"^[A-Z]\.?\s*", "", title)  # Letter sections
    
    # Normalize case for common section titles
    common_titles = {
        "introduction": "Introduction",
        "methods": "Methods", 
        "results": "Results",
        "discussion": "Discussion",
        "conclusion": "Conclusion",
        "conclusions": "Conclusions",
        "references": "References",
        "abstract": "Abstract",
    }
    
    title_lower = title.lower().strip()
    if title_lower in common_titles:
        title = common_titles[title_lower]
    
    return title.strip()


def remove_citations(text: str) -> str:
    """
    Remove inline citations while preserving readability.
    
    Args:
        text: Text with citations
        
    Returns:
        Text with citations removed
    """
    if not text:
        return ""
    
    # Remove numbered citations [1], [1-3], [1,2,3]
    text = re.sub(r"\[\d+(?:[-,]\d+)*\]", "", text)
    
    # Remove author citations (Author et al., 2020)
    text = re.sub(r"\([A-Z][a-z]+\s+et\s+al\.,?\s+\d{4}\)", "", text)
    
    # Clean up extra spaces left by removal
    text = re.sub(r"\s+", " ", text)
    
    return text.strip()