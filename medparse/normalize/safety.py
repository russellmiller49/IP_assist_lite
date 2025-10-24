"""Safety block normalization for IFU documents."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import List, Optional

SEVERITY_RULES = [
    (re.compile(r"^(⚠|warning[:\s])", re.IGNORECASE), "warning"),
    (re.compile(r"^caution[:\s]", re.IGNORECASE), "caution"),
    (re.compile(r"^note[:\s]", re.IGNORECASE), "note"),
]

CATEGORY_KEYWORDS = {
    # Sterility (check first - common)
    "sterile": "sterility",
    "steriliz": "sterility",
    "single-use": "sterility",
    "single use": "sterility",
    "ethylene oxide": "sterility",
    "eo steril": "sterility",
    "disposable": "sterility",

    # Electrical
    "electrical": "electrical",
    "electric": "electrical",
    "shock": "electrical",
    "voltage": "electrical",
    "ac power": "electrical",
    "leakage current": "electrical",
    "iec 60601": "electrical",
    "iec60601": "electrical",
    "grounding": "electrical",

    # Suction
    "suction": "suction",
    "aspiration": "suction",
    "lavage": "suction",
    "bal": "suction",
    "vacuum": "suction",

    # Laser
    "laser": "laser_safety",
    "class i": "laser_safety",
    "class 1": "laser_safety",
    "optical": "laser_safety",
    "beam": "laser_safety",

    # Radiation
    "radiation": "radiation",
    "fluoroscopy": "radiation",
    "x-ray": "radiation",
    "x ray": "radiation",
    "imaging dose": "radiation",

    # Mechanical
    "pinch": "mechanical",
    "crush": "mechanical",
    "buckling": "mechanical",
    "arm": "mechanical",
    "monitor position": "mechanical",
    "movement": "mechanical",

    # Infection
    "infection": "infection",
    "contamination": "infection",
    "cross-contam": "infection",
    "biohazard": "infection",

    # Thermal
    "burn": "thermal",
    "fire": "thermal",
    "heat": "thermal",
    "temperature": "thermal",
    "thermal": "thermal",

    # Chemical
    "chemical": "chemical",
    "cleaning agent": "chemical",
    "disinfect": "chemical",
    "cytotoxic": "chemical",
}


def detect_severity(text: str) -> Optional[str]:
    """Return the normalized severity for a safety block."""

    for pattern, label in SEVERITY_RULES:
        if pattern.match(text.strip()):
            return label
    return None


def categorize_block(text: str, *, parent_heading: str | None = None) -> Optional[str]:
    """Infer a safety category based on keywords in text and parent heading."""

    corpus = f"{parent_heading or ''} {text}".lower()
    for keyword, category in CATEGORY_KEYWORDS.items():
        if keyword in corpus:
            return category
    return None


# Footer and boilerplate patterns to remove
FOOTER_PATTERNS = [
    r'IonSystem,Instruments,andAccessoriesUserManual.*',  # footer
    r'EndofSection$',
    r'^Cautions$',
    r'^Notes$',
    r'^Warnings$',
]
FOOTER_RE = re.compile('|'.join(FOOTER_PATTERNS))


def strip_footer_noise(txt: str) -> str:
    """Remove footer and boilerplate patterns from safety block text."""
    return FOOTER_RE.sub('', txt).strip()


def near_dup(a: str, b: str, thresh: float = 0.97) -> bool:
    """Check if two strings are near-duplicates using sequence matching."""
    return SequenceMatcher(None, a, b).ratio() >= thresh


def dedupe_blocks(blocks: List) -> List:
    """Remove near-duplicate safety blocks and strip footer noise.

    Args:
        blocks: List of SafetyBlock objects

    Returns:
        Deduplicated list with cleaned text
    """
    out = []
    for blk in blocks:
        # Strip footer noise
        t = strip_footer_noise(blk.text)
        if not t:
            continue

        # Check for near-duplicates
        if any(near_dup(t, strip_footer_noise(o.text)) for o in out):
            continue

        # Update block text and add to output
        blk.text = t
        out.append(blk)

    return out


__all__ = ["detect_severity", "categorize_block", "dedupe_blocks", "strip_footer_noise", "near_dup"]
