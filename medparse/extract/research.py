"""Extractor for research study documents."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Sequence

from medparse.config import ExtractionConfig
from medparse.ingest.pdf_reader import PageContent, iter_pages
from medparse.normalize.ats_yield import compute_strict_yield
from medparse.types.base import EvidenceSpan
from medparse.types.research import Outcome, ResearchDocument
from medparse.types.yield_defs import NondiagnosticCounts


def extract_research(pdf_path: Path, config: Optional[ExtractionConfig] = None) -> ResearchDocument:
    """Extract structured research document data."""
    config = config or ExtractionConfig()
    pages = list(iter_pages(pdf_path))

    full_text = _normalize_text(pages)
    lower_text = full_text.lower()

    design = _extract_design(lower_text)
    n_patients = _extract_first_int(lower_text, r"(\d{2,4})\s+patients")
    n_lesions = _extract_first_int(lower_text, r"(\d{2,4})\s+peripheral\s+pulmonary\s+lesions")

    outcomes: List[Outcome] = []
    diagnostic_yield_pct = _append_outcome(
        pages,
        outcomes,
        pattern=r"([^.]*diagnostic yield[^.]*?\d+(?:\.\d+)?%)",
        name="Diagnostic yield",
    )
    _append_outcome(
        pages,
        outcomes,
        pattern=r"([^.]*molecular adequacy[^.]*?\d+(?:\.\d+)?%)",
        name="Molecular adequacy",
    )
    if not _append_table_outcome(pages, outcomes, label="Pneumothorax"):
        _append_outcome(
            pages,
            outcomes,
            pattern=r"([^.]*pneumothorax[^.]*?(\d+(?:\.\d+)?%)|\d+\s*\(\s*\d+(?:\.\d+)?%\s*\))",
            name="Pneumothorax",
        )

    denominator = n_patients or n_lesions
    specific_count = _extract_specific_diagnosis_count(lower_text)
    nondiagnostic = _extract_nondiagnostic_counts(lower_text)

    total_nondiagnostic = (
        nondiagnostic.atypia_or_suspicious
        + nondiagnostic.nonspecific_inflammation
        + nondiagnostic.other_nondiagnostic
    )

    if specific_count is None and denominator:
        remaining = denominator - total_nondiagnostic
        if remaining > 0:
            specific_count = remaining

    ats_yield = None
    if specific_count is not None and denominator:
        numerator = min(max(specific_count, 0), denominator)
        try:
            ats_yield = compute_strict_yield(numerator, denominator)
        except ValueError:
            ats_yield = None

    document = ResearchDocument(
        doc_type="research",
        source_file=str(pdf_path),
        page_count=len(pages),
        design=design,
        n_patients=n_patients,
        n_lesions=n_lesions,
        outcomes=outcomes,
        ats_yield=ats_yield,
        nondiagnostic=nondiagnostic,
    )

    if config.fail_fast and not outcomes:
        raise ValueError("Research extractor produced no outcomes.")

    return document


def _normalize_text(pages: Sequence[PageContent]) -> str:
    text = " ".join(page.text for page in pages)
    text = text.replace("-\n", "")
    text = text.replace("\n", " ")
    return re.sub(r"\s+", " ", text)


def _extract_design(lower_text: str) -> Optional[str]:
    for keyword in ("retrospective", "prospective", "randomized", "observational"):
        if keyword in lower_text:
            return keyword
    return None


def _extract_first_int(lower_text: str, pattern: str) -> Optional[int]:
    match = re.search(pattern, lower_text)
    if not match:
        return None
    return int(match.group(1))


def _append_outcome(
    pages: Sequence[PageContent],
    outcomes: List[Outcome],
    pattern: str,
    name: str,
) -> Optional[float]:
    regex = re.compile(pattern, re.IGNORECASE)
    match = regex.search(" ".join(page.text for page in pages))
    if not match:
        return None

    snippet = re.sub(r"\s+", " ", match.group(0)).strip()
    percent_match = re.search(r"(\d+(?:\.\d+)?)%", snippet)
    value = float(percent_match.group(1)) if percent_match else None

    evidence = _find_evidence_span(pages, snippet)
    outcomes.append(
        Outcome(
            name=name,
            value=value,
            unit="percent" if value is not None else None,
            evidence=evidence,
        )
    )
    return value


def _append_table_outcome(
    pages: Sequence[PageContent],
    outcomes: List[Outcome],
    label: str,
) -> Optional[float]:
    target = label.lower()
    for page in pages:
        for idx, line in enumerate(page.lines):
            if target in line.lower():
                window = " ".join(page.lines[idx : idx + 3])
                match = re.search(r"(\d+)\s*\((\d+(?:\.\d+)?)%\)", window)
                if match:
                    percent = float(match.group(2))
                    evidence = EvidenceSpan(text=window.strip(), page=page.number)
                    outcomes.append(
                        Outcome(
                            name=label,
                            value=percent,
                            unit="percent",
                            evidence=evidence,
                        )
                    )
                    return percent
    return None


def _find_evidence_span(pages: Sequence[PageContent], snippet: str) -> EvidenceSpan:
    lowered = snippet.lower()[:80]
    for page in pages:
        if lowered and lowered in page.text.lower():
            return EvidenceSpan(text=snippet[:200], page=page.number)
    return EvidenceSpan(text=snippet[:200], page=1)


def _extract_specific_diagnosis_count(lower_text: str) -> Optional[int]:
    patterns = [
        r"specific diagnosis(?:es)? (?:was|were)?\s*made in\s*(\d+)",
        r"confirmed specific diagnosis(?:es)? (?:was|were)?\s*made in\s*(\d+)",
        r"(\d+)\s+(?:patients|cases)\s+had\s+a\s+specific\s+diagnosis",
        r"(\d+)\s+specific\s+(?:benign|malignant)",
    ]
    for pattern in patterns:
        match = re.search(pattern, lower_text)
        if match:
            return int(match.group(1))
    return None


def _extract_nondiagnostic_counts(lower_text: str) -> NondiagnosticCounts:
    atypia = 0
    nonspecific = 0
    for match in re.finditer(r"(\d+)\s+(?:cases|samples|patients)[^\.]*atypia", lower_text):
        atypia += int(match.group(1))
    for match in re.finditer(r"(\d+)\s+(?:cases|samples|patients)[^\.]*suspicious", lower_text):
        atypia += int(match.group(1))
    for match in re.finditer(
        r"(\d+)\s+(?:diagnoses|cases|samples)[^\.]*non[-\s]?specific", lower_text
    ):
        nonspecific += int(match.group(1))

    return NondiagnosticCounts(
        atypia_or_suspicious=atypia,
        nonspecific_inflammation=nonspecific,
        other_nondiagnostic=0,
    )
