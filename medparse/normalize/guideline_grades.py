"""Guideline recommendation extraction with grade normalization."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel

from medparse.ingest.models import PageData

RE_REC_LINE = re.compile(
    r"^\s*(We\s+(recommend|suggest)[^.\n]*?)(?:\.\s*)?(?:\((?:Recommendation\s+grade\s+([A-D]))\))?",
    re.IGNORECASE,
)
RE_REC = re.compile(r"^\s*(?:we\s+(?:recommend|suggest)\b.*)", re.IGNORECASE)
RE_GRADE = re.compile(
    r"(?:Recommendation\s*grade\s+([A-D]))|(GRADE\s*(?:Strong|Weak|Conditional))|(Ungraded|Consensus|Good\s*Practice)",
    re.IGNORECASE,
)
RE_GRADE_WORD = re.compile(r"\b(strong|conditional)\s+recommendation\b", re.IGNORECASE)
RE_CERTAINTY = re.compile(r"\b(very low|low|moderate|high)\s+certainty\b", re.IGNORECASE)


class GuidelineRecommendation(BaseModel):
    """Individual guideline recommendation with grade and evidence."""

    number: Optional[str] = None
    text: str
    grade: Optional[str] = None
    strength: Optional[str] = None  # normalized strength
    strength_scale: Optional[str] = None  # GRADE, ACCP, SIGN, etc.
    evidence_level: Optional[str] = None
    consensus_percentage: Optional[float] = None
    votes: Optional[str] = None
    statement_type: str = "graded"  # graded | ungraded | good_practice | consensus
    page: Optional[int] = None
    page_span: Optional[Tuple[int, int]] = None


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
    recs: List[GuidelineRecommendation] = []

    rec_text = sections.get('recommendations', '') or find_recommendation_blocks(pages)
    rec_blocks = split_recommendations(rec_text) if rec_text else []
    if not rec_blocks:
        rec_blocks = fallback_recommendation_blocks(pages)
    if not rec_blocks:
        return recs

    for i, block in enumerate(rec_blocks, 1):
        if not block.strip():
            continue

        number = extract_number(block) or str(i)
        first_line = block.strip().splitlines()[0] if block.strip() else ""
        line_match = RE_REC_LINE.match(first_line)
        explicit_grade = None
        if line_match and line_match.group(3):
            explicit_grade = line_match.group(3).upper()
        grade, scale, strength, statement_type = extract_grade(block, explicit_grade=explicit_grade)
        evidence_level = extract_evidence_level(block)
        consensus = extract_consensus(block)

        rec_text_clean = bound_recommendation_text(block)
        if not rec_text_clean:
            rec_text_clean = block.strip()

        page_num = find_page_for_text(pages, rec_text_clean[:120])

        recs.append(
            GuidelineRecommendation(
                number=number,
                text=rec_text_clean,
                grade=grade,
                strength=strength,
                strength_scale=scale,
                evidence_level=evidence_level,
                consensus_percentage=consensus.get('percentage'),
                votes=consensus.get('votes'),
                statement_type=statement_type,
                page=page_num,
                page_span=(page_num, page_num) if page_num is not None else None,
            )
        )

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


def fallback_recommendation_blocks(pages: List[PageData]) -> List[str]:
    """Fallback extractor scanning entire document for anchored recommendation lines."""

    blocks: List[str] = []
    current: List[str] = []

    def _flush() -> None:
        nonlocal current
        if not current:
            return
        text = " ".join(current).strip()
        if text:
            normalized = re.sub(r"\s+", " ", text)
            if normalized not in blocks:
                blocks.append(normalized)
        current = []

    for page in pages:
        for raw_line in page.lines or []:
            line = raw_line.strip()
            if not line:
                _flush()
                continue
            if RE_REC.match(line):
                _flush()
                current.append(line)
                continue
            if current:
                if re.match(r"^(?:[-•*]|\d+[\.\)])\s+", line):
                    current.append(line)
                    continue
                if line and line[0].isupper():
                    current.append(line)
                    continue
                _flush()
        _flush()

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_blocks: List[str] = []
    for block in blocks:
        if block in seen:
            continue
        seen.add(block)
        unique_blocks.append(block)
    return unique_blocks


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

    # Pattern 4: Sentences beginning with "We recommend" / "We suggest"
    if re.search(r'\bWe\s+(?:recommend|suggest)\b', text, re.IGNORECASE):
        blocks = re.split(r'(?<=\.)\s+(?=We\s+(?:recommend|suggest))', text)
        if len(blocks) > 1:
            return [b.strip() for b in blocks if b.strip()]

    if RE_REC.search(text):
        paragraphs = re.split(r'\n\s*\n', text)
        rec_blocks = [paragraph.strip() for paragraph in paragraphs if RE_REC.search(paragraph)]
        if rec_blocks:
            return rec_blocks

    # Pattern 5: Bullet points or numbered list
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
    result = re.sub(r'^(?:Recommendation\s*)?(\d+(?:\.\d+)*)[:\-]\s*', '', result, flags=re.IGNORECASE)

    return result


def extract_number(text: str) -> Optional[str]:
    """Extract explicit recommendation numbering (1, 1.1, etc.)."""

    patterns = [
        r'^\s*recommendation\s*(\d+(?:\.\d+)*)',
        r'^\s*(\d+(?:\.\d+)*)\s*(?=[\.:])',
        r'^\s*(\d+(?:\.\d+)*)\s+',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def extract_grade(
    text: str,
    explicit_grade: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], Optional[str], str]:
    """Extract grade details returning (grade, scale, strength, statement_type)."""

    lowered = text.lower()

    if "consensus" in lowered:
        return None, None, None, "consensus"

    if explicit_grade:
        grade_token = explicit_grade.upper()
        strength = normalize_strength("GRADE", grade_token, lowered)
        return grade_token, "GRADE", strength, "graded"

    # Explicit grade tokens with known scales
    grade_patterns = [
        (r'\bgrade\s+(1[abc]|2[abc])\b', 'GRADE'),
        (r'\bgrade\s+([A-D][+\-]?)\b', 'GRADE'),
        (r'\b(1[ABC]|2[ABC])\b', 'ACCP'),
        (r'\b(SIGN)\s*(A|B|C|D|GPP)\b', 'SIGN'),
        (r'\bNICE\s+([A-D1-3])\b', 'NICE'),
    ]

    for pattern, scale in grade_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            if scale == 'SIGN' and len(match.groups()) == 2:
                grade_token = match.group(2).upper()
            else:
                grade_token = match.group(1).upper()

            strength = normalize_strength(scale, grade_token, lowered)
            statement_type = 'graded'
            if grade_token == 'GPP':
                statement_type = 'ungraded'
                grade_token = None
            return grade_token, scale, strength, statement_type

    grade_descriptor = RE_GRADE.search(text)
    if grade_descriptor:
        descriptor = grade_descriptor.group(2)
        trailing = grade_descriptor.group(3)
        if descriptor:
            descriptor_lower = descriptor.lower()
            if "strong" in descriptor_lower:
                return None, "GRADE", "strong", "graded"
            if "weak" in descriptor_lower or "conditional" in descriptor_lower:
                return None, "GRADE", "conditional", "graded"
        if trailing:
            trailing_lower = trailing.lower()
            if "consensus" in trailing_lower:
                return None, None, None, "consensus"
            return None, None, None, "ungraded"

    grade_word = RE_GRADE_WORD.search(text)
    if grade_word:
        descriptor = grade_word.group(1).lower()
        strength = "strong" if descriptor == "strong" else "conditional"
        return None, "GRADE", strength, "graded"

    certainty = RE_CERTAINTY.search(text)
    if certainty:
        certainty_label = f"{certainty.group(1).strip().title()} certainty"
        return None, None, certainty_label, "graded"

    if 'good practice statement' in lowered or 'good practice point' in lowered:
        return None, None, None, 'ungraded'
    if 'ungraded' in lowered or 'no recommendation' in lowered:
        return None, None, None, 'ungraded'

    strength = derive_strength_from_text(lowered)
    statement_type = 'graded' if strength else 'ungraded'
    return None, None, strength, statement_type


def normalize_strength(scale: str, grade: str, lowered_text: str) -> Optional[str]:
    scale_upper = (scale or '').upper()
    grade_upper = (grade or '').upper()

    if scale_upper == 'ACCP':
        return 'strong' if grade_upper.startswith('1') else 'conditional'
    if scale_upper == 'GRADE':
        if 'strong recommendation' in lowered_text:
            return 'strong'
        if 'conditional recommendation' in lowered_text or 'weak recommendation' in lowered_text:
            return 'conditional'
    if scale_upper == 'SIGN':
        if grade_upper in {'A', 'B'}:
            return 'strong'
        if grade_upper in {'C', 'D'}:
            return 'conditional'
    if scale_upper == 'NICE':
        if grade_upper in {'A', '1', '2'}:
            return 'strong'
        if grade_upper in {'B', 'C', '3'}:
            return 'conditional'
    return None


def derive_strength_from_text(lowered_text: str) -> Optional[str]:
    if 'strong recommendation' in lowered_text:
        return 'strong'
    if 'conditional recommendation' in lowered_text or 'weak recommendation' in lowered_text:
        return 'conditional'
    if 'recommend' in lowered_text and 'suggest' not in lowered_text:
        return 'strong'
    if 'we suggest' in lowered_text:
        return 'conditional'
    return None


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

    certainty = RE_CERTAINTY.search(text)
    if certainty:
        return f"{certainty.group(1).strip().title()} certainty"

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
]
