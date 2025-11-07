"""Second-pass patcher that reconstructs ATS diagnostic yield metadata."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from medparse.normalize._ats_codes import (
    ATS_CANONICAL_REASONS,
    ATS_REASON_DERIVED,
    ATS_REASON_FOLLOW_UP,
    ATS_REASON_NO_N_OVER_N,
)
from medparse.schema.article import ArticleDocument, DiagnosticYield
from medparse.schema.common import BaseDocument

from ..types import SecondPassContext, SecondPassPatchResult

PATCH_NAME = "yield_ats_fixer"

KEYWORDS = ("yield", "diagnostic", "sensitivity", "biopsy", "samples")
FOLLOW_UP_CUES = (
    "including subsequent surgery",
    "including subsequent surgeries",
    "after lobectomy",
    "follow-up bronchoscopy",
    "considered diagnostic if follow-up",
    "including follow-up procedures",
    "after additional biopsy",
)

FRACTION_RE = re.compile(r"(\d{1,4})\s*/\s*(\d{1,4})")
OF_PATTERN_RE = re.compile(r"(\d{1,4})\s+(?:of|out of)\s+(\d{1,4})", re.IGNORECASE)
PERCENT_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")


def _ordered_paragraphs(paragraph_store: Dict[str, Dict[str, object]]) -> List[Tuple[int, str]]:
    ordered: List[Tuple[int, str]] = []
    for entry in paragraph_store.values():
        text = entry.get("text")
        if not isinstance(text, str):
            continue
        if not any(keyword in text.lower() for keyword in KEYWORDS):
            continue
        order_values = entry.get("order") or []
        try:
            order_index = min(int(value) for value in order_values) if order_values else 10**6
        except (TypeError, ValueError):
            order_index = 10**6
        ordered.append((order_index, text))
    ordered.sort(key=lambda item: item[0])
    return ordered


def _scan_percentages(text: str) -> Optional[float]:
    match = PERCENT_RE.search(text)
    if match:
        try:
            return float(match.group(1))
        except (TypeError, ValueError):
            return None
    return None


def _scan_fraction(text: str) -> Optional[Tuple[int, int]]:
    match = FRACTION_RE.search(text)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = OF_PATTERN_RE.search(text)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None


def _collect_neighbor_text(paragraphs: List[Tuple[int, str]], idx: int, window: int) -> List[str]:
    collected: List[str] = []
    for offset in range(-window, window + 1):
        neighbor_idx = idx + offset
        if neighbor_idx < 0 or neighbor_idx >= len(paragraphs):
            continue
        collected.append(paragraphs[neighbor_idx][1])
    return collected


def _has_follow_up_language(snippets: List[str]) -> bool:
    for snippet in snippets:
        lowered = snippet.lower()
        if any(token in lowered for token in FOLLOW_UP_CUES):
            return True
    return False


def apply_yield_ats_fixer(document: BaseDocument, ctx: SecondPassContext) -> SecondPassPatchResult:
    if not isinstance(document, ArticleDocument):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="doc_not_article")

    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    second_pass_bucket = pipeline_info.setdefault("second_pass", {})
    applied = second_pass_bucket.get("patches_applied") or []
    if isinstance(applied, list) and PATCH_NAME in applied:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="already_applied")

    subtype = (getattr(document, "doc_subtype", "") or "").lower()
    if subtype not in {"research", "research_diagnostic", "guideline", "statement", "classification"}:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason=f"subtype_{subtype or 'unknown'}")

    existing = getattr(document, "diagnostic_yield", None)
    if existing and getattr(existing, "numerator", None) and getattr(existing, "denominator", None):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="already_has_counts")

    issue_triggers = [
        issue for issue in ctx.validation_issues if "diagnostic" in issue.message.lower() and "yield" in issue.message.lower()
    ]
    if not issue_triggers and ctx.mode == "auto":
        # Allow auto mode to bail when validators did not flag yield issues.
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="auto_mode_no_trigger")

    ordered_paragraphs = _ordered_paragraphs(ctx.paragraph_store)
    if not ordered_paragraphs:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_candidate_paragraphs")

    numerator: Optional[int] = None
    denominator: Optional[int] = None
    percent_value: Optional[float] = None
    reasons: List[str] = []
    evidence_text: Optional[str] = None
    window = int(ctx.config.get("yield_ats", {}).get("max_proximity_paras", 2)) if isinstance(ctx.config, dict) else 2
    window = max(0, min(window, 4))

    for idx, (_order, text) in enumerate(ordered_paragraphs):
        snippets = _collect_neighbor_text(ordered_paragraphs, idx, window)
        combined = " ".join(snippet for snippet in snippets if snippet)
        fraction = None
        for snippet in snippets:
            fraction = _scan_fraction(snippet)
            if fraction:
                evidence_text = snippet
                break
        if fraction:
            numerator, denominator = fraction
            if OF_PATTERN_RE.search(evidence_text or "") and "/" not in evidence_text:
                if ATS_REASON_NO_N_OVER_N not in reasons:
                    reasons.append(ATS_REASON_NO_N_OVER_N)
            percent_value = _scan_percentages(combined)
        else:
            percent_value = _scan_percentages(combined)
            if percent_value is not None and ATS_REASON_DERIVED not in reasons:
                reasons.append(ATS_REASON_DERIVED)

        if numerator or percent_value:
            if _has_follow_up_language(snippets) and ATS_REASON_FOLLOW_UP not in reasons:
                reasons.append(ATS_REASON_FOLLOW_UP)
            break

    if numerator is None and percent_value is None:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_numeric_signals")

    reasons = [reason for reason in reasons if reason in ATS_CANONICAL_REASONS]
    if existing is None:
        diagnostic = DiagnosticYield()
    else:
        diagnostic = DiagnosticYield.model_validate(existing.model_dump())

    modifications: Dict[str, int] = {}
    if numerator is not None:
        diagnostic.numerator = numerator
        modifications["diagnostic_yield_numerator"] = 1
    if denominator is not None:
        diagnostic.denominator = denominator
        modifications["diagnostic_yield_denominator"] = 1
    if percent_value is not None:
        diagnostic.value = float(percent_value)
        modifications["diagnostic_yield_value"] = 1
    if numerator is None or denominator is None:
        diagnostic.strict = False
        diagnostic.compatible_with_ats = False
    else:
        diagnostic.strict = True and ATS_REASON_FOLLOW_UP not in reasons
        diagnostic.compatible_with_ats = ATS_REASON_FOLLOW_UP not in reasons

    diagnostic.exclusion_reasons = reasons
    if evidence_text and not diagnostic.evidence:
        diagnostic.evidence = None  # evidence pointers added via evidence bank; intentionally left blank

    document.diagnostic_yield = diagnostic
    pipeline_info["ats_yield_reasons"] = list(reasons)
    if reasons:
        pipeline_info.setdefault("second_pass_reasons", {})[PATCH_NAME] = list(reasons)
    pipeline_info.setdefault("second_pass", {}).setdefault("patches_applied", [])
    document.pipeline_info = pipeline_info

    return SecondPassPatchResult(
        name=PATCH_NAME,
        applied=True,
        modifications=modifications or {"diagnostic_yield_updated": 1},
        reasons=["ats_diagnostic_yield_backfill"],
    )
