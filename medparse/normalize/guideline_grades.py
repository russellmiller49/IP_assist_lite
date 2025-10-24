"""Guideline recommendation extraction with grade normalization."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel

from medparse.ingest.models import PageData


class GuidelineRecommendation(BaseModel):
    """Individual guideline recommendation with grade and evidence."""
    number: str
    text: str
    grade: Optional[str] = None
    strength_scale: Optional[str] = None  # GRADE, ACCP, SIGN, etc.
    evidence_level: Optional[str] = None
    consensus_percentage: Optional[float] = None
    voting_results: Optional[str] = None
    page: Optional[int] = None


# Grade scale mappings
GRADE_SCALES = {
    'GRADE': {
        'strong': ['strong', '⊕⊕⊕⊕', '⊕⊕⊕○'],
        'conditional': ['conditional', 'weak', '⊕⊕○○', '⊕○○○']
    },
    'ACCP': {
        '1A': 'strong_high',
        '1B': 'strong_moderate',
        '1C': 'strong_low',
        '2A': 'weak_high',
        '2B': 'weak_moderate',
        '2C': 'weak_low'
    },
    'SIGN': {
        'A': 'high',
        'B': 'moderate',
        'C': 'low',
        'D': 'very_low',
        'GPP': 'good_practice_point'
    }
}


def parse_guideline_recommendations(
    sections: Dict[str, str],
    pages: List[PageData]
) -> List[GuidelineRecommendation]:
    """Extract recommendations with boundary detection and grade normalization.

    Args:
        sections: Document sections
        pages: All pages for page number lookup

    Returns:
        List of GuidelineRecommendation objects
    """
    recs = []

    # Look for recommendation sections
    rec_text = sections.get('recommendations', '') or find_recommendation_blocks(pages)
    if not rec_text:
        return []

    # Split into individual recommendations
    rec_blocks = split_recommendations(rec_text)

    for i, block in enumerate(rec_blocks, 1):
        # Extract text (cut at terminal punctuation before topic shift)
        rec_text_clean = bound_recommendation_text(block)

        # Extract grade
        grade, scale = extract_grade(block)

        # Extract evidence level
        evidence_level = extract_evidence_level(block)

        # Extract consensus if present
        consensus = extract_consensus(block)

        # Find page number
        page_num = find_page_for_text(pages, block[:100])

        recs.append(GuidelineRecommendation(
            number=str(i),
            text=rec_text_clean,
            grade=grade,
            strength_scale=scale,
            evidence_level=evidence_level,
            consensus_percentage=consensus.get('percentage'),
            voting_results=consensus.get('votes'),
            page=page_num
        ))

    return recs


def find_recommendation_blocks(pages: List[PageData]) -> str:
    """Find recommendation section in pages.

    Args:
        pages: Pages to search

    Returns:
        Recommendation section text
    """
    rec_headings = ['recommendations', 'guideline recommendations', 'clinical recommendations']

    full_text = '\n'.join('\n'.join(p.lines) for p in pages)

    for heading in rec_headings:
        pattern = rf'(?:^|\n)({re.escape(heading)})[:\s]*\n(.+?)(?=\n\n[A-Z][a-z]+:|\Z)'
        match = re.search(pattern, full_text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(2).strip()

    return ""


def split_recommendations(text: str) -> List[str]:
    """Split text into individual recommendations using anchors.

    Args:
        text: Recommendations section text

    Returns:
        List of recommendation blocks
    """
    # Pattern 1: Numeric anchors (1., 2., etc.)
    if re.search(r'^\d+\.', text, re.MULTILINE):
        blocks = re.split(r'\n(?=\d+\.)', text)
        return [b.strip() for b in blocks if b.strip()]

    # Pattern 2: "Recommendation:" headers
    if 'recommendation:' in text.lower():
        blocks = re.split(r'\n(?=Recommendation:)', text, flags=re.IGNORECASE)
        return [b.strip() for b in blocks if b.strip()]

    # Pattern 3: Grade markers (GRADE A, 1A, etc.)
    grade_pattern = r'\n(?=.*(?:GRADE|grade|recommendation)\s+[A-D12])'
    blocks = re.split(grade_pattern, text, flags=re.IGNORECASE)
    if len(blocks) > 1:
        return [b.strip() for b in blocks if b.strip()]

    # Pattern 4: Bullet points or numbered list
    if re.search(r'^[•\-\*]\s+', text, re.MULTILINE):
        blocks = re.split(r'\n(?=[•\-\*]\s+)', text)
        return [b.strip() for b in blocks if b.strip()]

    # Fallback: return as single block
    return [text] if text else []


def bound_recommendation_text(block: str) -> str:
    """Cut recommendation at first terminal punctuation before unrelated narrative.

    Args:
        block: Recommendation text block

    Returns:
        Bounded recommendation text
    """
    # Look for section markers that indicate end of recommendation
    shift_markers = ['Introduction', 'Background', 'Methods', 'Figure', 'Table', 'References']

    sentences = re.split(r'(?<=[.!?])\s+', block)
    bounded = []

    for sentence in sentences:
        # Stop if we hit a section keyword
        if any(marker in sentence for marker in shift_markers):
            break

        bounded.append(sentence)

        # Stop if cumulative length exceeds 500 chars (likely bleed)
        if len(' '.join(bounded)) > 500:
            break

    result = ' '.join(bounded).strip()

    # Remove leading numbering if present
    result = re.sub(r'^\d+\.\s+', '', result)

    return result


def extract_grade(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract and normalize grade.

    Args:
        text: Recommendation text

    Returns:
        Tuple of (grade, scale_name)
    """
    # Try GRADE first
    for strength, patterns in GRADE_SCALES['GRADE'].items():
        for pattern in patterns:
            if pattern.lower() in text.lower():
                return (strength.title(), 'GRADE')

    # Try ACCP
    for grade_code in GRADE_SCALES['ACCP'].keys():
        if re.search(rf'\b{grade_code}\b', text):
            return (grade_code, 'ACCP')

    # Try SIGN
    for grade_letter in GRADE_SCALES['SIGN'].keys():
        if re.search(rf'\bGrade\s+{grade_letter}\b', text, re.IGNORECASE):
            return (grade_letter, 'SIGN')

    # Look for generic "Grade X" pattern
    generic_match = re.search(r'\bGrade\s+([A-D12]+)\b', text, re.IGNORECASE)
    if generic_match:
        return (generic_match.group(1), 'Generic')

    return (None, None)


def extract_evidence_level(text: str) -> Optional[str]:
    """Extract evidence level (Level I, II, III, etc.).

    Args:
        text: Recommendation text

    Returns:
        Evidence level string or None
    """
    # Pattern: Level I, Level II, etc.
    match = re.search(r'\bLevel\s+([IVX]+|[1-4])\b', text, re.IGNORECASE)
    if match:
        return match.group(1).upper()

    # Pattern: Quality of evidence: High/Moderate/Low
    match = re.search(r'Quality of evidence:\s*(High|Moderate|Low|Very low)', text, re.IGNORECASE)
    if match:
        return match.group(1).title()

    return None


def extract_consensus(text: str) -> Dict[str, Optional[any]]:
    """Extract consensus percentage and voting results.

    Args:
        text: Recommendation text

    Returns:
        Dictionary with percentage and votes
    """
    consensus_data = {'percentage': None, 'votes': None}

    # Pattern: "consensus: 95%" or "95% consensus"
    pct_match = re.search(r'(\d+)%\s*consensus|consensus[:\s]+(\d+)%', text, re.IGNORECASE)
    if pct_match:
        pct_str = pct_match.group(1) or pct_match.group(2)
        consensus_data['percentage'] = float(pct_str)

    # Pattern: voting results "12/15 agreed" or "(15 yes, 2 no, 1 abstain)"
    vote_match = re.search(r'(\d+)/(\d+)\s+(?:agreed|approved|voted)', text, re.IGNORECASE)
    if vote_match:
        consensus_data['votes'] = f"{vote_match.group(1)}/{vote_match.group(2)}"
        # Calculate percentage if not already set
        if consensus_data['percentage'] is None:
            numerator = int(vote_match.group(1))
            denominator = int(vote_match.group(2))
            if denominator > 0:
                consensus_data['percentage'] = (numerator / denominator) * 100

    return consensus_data


def find_page_for_text(pages: List[PageData], text_snippet: str) -> Optional[int]:
    """Find page number containing text snippet.

    Args:
        pages: Pages to search
        text_snippet: Text to find

    Returns:
        Page number (0-indexed) or None
    """
    # Normalize text for comparison
    snippet_norm = re.sub(r'\s+', ' ', text_snippet.lower()).strip()

    for i, page in enumerate(pages):
        page_text = '\n'.join(page.lines).lower()
        page_norm = re.sub(r'\s+', ' ', page_text).strip()

        if snippet_norm[:50] in page_norm:
            return i

    return None


__all__ = [
    "parse_guideline_recommendations",
    "GuidelineRecommendation",
    "extract_grade",
    "GRADE_SCALES",
]
