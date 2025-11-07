"""Second-pass patcher that mines strict diagnostic yield counts for ATS compliance."""

from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Sequence, Tuple

from medparse.normalize._ats_codes import (
    ATS_CANONICAL_REASONS,
    ATS_REASON_DERIVED,
    ATS_REASON_FOLLOW_UP,
    ATS_REASON_NO_N_OVER_N,
    ATS_REASON_NONSPECIFIC,
)
from medparse.schema.article import ArticleDocument, DiagnosticYield
from medparse.schema.common import BaseDocument, EvidenceSpan

from ..types import SecondPassContext, SecondPassPatchResult

PATCH_NAME = "article_yield_strict_miner"

DIAGNOSTIC_KEY_PATTERN = re.compile(r"diagnostic\s+(yield|rate)", re.IGNORECASE)
PERCENT_PATTERN = re.compile(r"(\d{1,3}(?:[.,]\d{1,2})?)\s*%", re.IGNORECASE)
FRACTION_PATTERN = re.compile(r"(\d{1,4})\s*/\s*(\d{1,4})")
OF_PATTERN = re.compile(r"(\d{1,4})\s+(?:of|out of)\s+(\d{1,4})", re.IGNORECASE)
N_PATTERN = re.compile(r"\bn\s*=\s*(\d{1,4})", re.IGNORECASE)
BIG_N_PATTERN = re.compile(r"\bN\s*=\s*(\d{1,4})")
FOLLOW_UP_PATTERN = re.compile(r"follow[-\s]*up", re.IGNORECASE)
NONSPECIFIC_PATTERN = re.compile(r"\b(atypia|suspicious|nonspecific inflammation)\b", re.IGNORECASE)

ALLOWED_FAILURE_REASONS = {
    ATS_REASON_NO_N_OVER_N,
    ATS_REASON_DERIVED,
    ATS_REASON_NONSPECIFIC,
    ATS_REASON_FOLLOW_UP,
}


def apply_article_yield_strict_miner(document: BaseDocument, ctx: SecondPassContext) -> SecondPassPatchResult:
    if not isinstance(document, ArticleDocument):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="doc_not_article")

    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    second_pass_bucket = pipeline_info.setdefault("second_pass", {})
    applied = second_pass_bucket.get("patches_applied") or []
    if isinstance(applied, list) and PATCH_NAME in applied:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="already_applied")

    subtype = (getattr(document, "doc_subtype", "") or "").lower()
    if subtype != "research_diagnostic":
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason=f"subtype_{subtype or 'unknown'}")

    trigger_issue = False
    for issue in ctx.validation_issues:
        message = str(getattr(issue, "message", "") or "").lower()
        if "diagnostic yield missing" in message:
            trigger_issue = True
            break
    if not trigger_issue:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_validator_trigger")

    paragraphs = _sorted_paragraphs(ctx.paragraph_store)
    candidate = _detect_from_paragraphs(paragraphs)
    if candidate is None:
        candidate = _detect_from_tables(document)

    diagnostic = getattr(document, "diagnostic_yield", None)
    if diagnostic is None:
        diagnostic = DiagnosticYield()

    modifications: Dict[str, int] = {}
    payload: Dict[str, object] = {}
    reasons = sorted(candidate["reasons"]) if candidate else [ATS_REASON_NO_N_OVER_N]

    if candidate and candidate["numerator"] is not None and candidate["denominator"] and not candidate["reasons"]:
        numerator = candidate["numerator"]
        denominator = candidate["denominator"]
        percent = candidate["percent"]
        if percent is None and denominator:
            percent = round((numerator / denominator) * 100.0, 2) if denominator else None

        if numerator is not None:
            diagnostic.numerator = numerator
            modifications["diagnostic_yield_numerator"] = 1
        if denominator:
            diagnostic.denominator = denominator
            modifications["diagnostic_yield_denominator"] = 1
        if percent is not None and not math.isnan(percent):
            diagnostic.value = float(percent)
            diagnostic.reported_value = diagnostic.value / 100.0
            modifications["diagnostic_yield_value"] = 1

        diagnostic.strict = True
        diagnostic.compatible_with_ats = True
        diagnostic.exclusion_reasons = []

        evidence_hashes = sorted(candidate["evidence_keys"])
        if evidence_hashes:
            diagnostic.evidence_refs = evidence_hashes
        snippet = candidate.get("evidence_text") or ""
        if snippet:
            diagnostic.evidence = EvidenceSpan(text=snippet[:200], page=candidate.get("page"), confidence=0.75)

        payload = {
            "strict_yield": True,
            "n": numerator,
            "N": denominator,
            "percent": diagnostic.value,
            "evidence": [{"hash": hash_id} for hash_id in evidence_hashes],
            "reasons": [],
        }
        result_reasons = ["strict_yield_mined"]
    else:
        if candidate:
            numerator = candidate["numerator"]
            denominator = candidate["denominator"]
            if numerator is not None:
                diagnostic.numerator = numerator
            if denominator:
                diagnostic.denominator = denominator
            percent = candidate["percent"]
            if percent is not None and not math.isnan(percent):
                diagnostic.value = float(percent)
                diagnostic.reported_value = diagnostic.value / 100.0
        diagnostic.strict = False
        diagnostic.compatible_with_ats = False
        filtered_reasons = [reason for reason in reasons if reason in ATS_CANONICAL_REASONS]
        if not filtered_reasons:
            filtered_reasons = [ATS_REASON_NO_N_OVER_N]
        diagnostic.exclusion_reasons = filtered_reasons
        payload = {
            "strict_yield": False,
            "reasons": filtered_reasons,
        }
        result_reasons = ["strict_yield_not_found"]

    document.diagnostic_yield = diagnostic
    pipeline_info["ats_yield"] = payload
    pipeline_info["second_pass"] = second_pass_bucket
    document.pipeline_info = pipeline_info

    return SecondPassPatchResult(
        name=PATCH_NAME,
        applied=True,
        modifications=modifications or {"diagnostic_yield_updated": 1},
        reasons=result_reasons,
    )


def _sorted_paragraphs(
    paragraph_store: Dict[str, Dict[str, object]],
) -> List[Tuple[int, str, Dict[str, object]]]:
    paragraphs: List[Tuple[int, str, Dict[str, object]]] = []
    for hash_id, entry in (paragraph_store or {}).items():
        text = entry.get("text")
        if not isinstance(text, str):
            continue
        stripped = text.strip()
        if not stripped:
            continue
        orders = entry.get("order") or []
        try:
            order_index = min(int(value) for value in orders) if orders else 10**6
        except (TypeError, ValueError):
            order_index = 10**6
        paragraphs.append((order_index, hash_id, entry))
    paragraphs.sort(key=lambda item: item[0])
    return paragraphs


def _detect_from_paragraphs(
    paragraphs: Sequence[Tuple[int, str, Dict[str, object]]],
) -> Optional[Dict[str, object]]:
    best: Optional[Dict[str, object]] = None
    for idx, (_order, hash_id, entry) in enumerate(paragraphs):
        text = entry.get("text")
        if not isinstance(text, str):
            continue
        if not DIAGNOSTIC_KEY_PATTERN.search(text):
            continue

        percent = _parse_percent(text)
        counts = _find_counts(paragraphs, idx)
        reasons = set()
        evidence_keys = {hash_id}
        if counts:
            numerator, denominator, count_hashes = counts
            evidence_keys.update(count_hashes)
        else:
            reasons.add(ATS_REASON_NO_N_OVER_N)
            if percent is not None:
                reasons.add(ATS_REASON_DERIVED)
        if counts and percent is None and counts[1]:
            numerator, denominator, _ = counts
            percent = round((numerator / denominator) * 100.0, 2)

        window = range(max(0, idx - 2), min(len(paragraphs), idx + 3))
        for neighbor_idx in window:
            neighbor_text = paragraphs[neighbor_idx][2].get("text")
            if not isinstance(neighbor_text, str):
                continue
            lower = neighbor_text.lower()
            if FOLLOW_UP_PATTERN.search(lower):
                reasons.add(ATS_REASON_FOLLOW_UP)
            if NONSPECIFIC_PATTERN.search(lower):
                reasons.add(ATS_REASON_NONSPECIFIC)

        candidate = {
            "numerator": counts[0] if counts else None,
            "denominator": counts[1] if counts else None,
            "percent": percent,
            "reasons": {reason for reason in reasons if reason in ALLOWED_FAILURE_REASONS},
            "evidence_keys": evidence_keys,
            "page": entry.get("page"),
            "yield_idx": idx,
            "evidence_text": text.strip(),
        }
        best = _choose_better_candidate(best, candidate)
    return best


def _detect_from_tables(document: ArticleDocument) -> Optional[Dict[str, object]]:
    tables = getattr(document, "tables", []) or []
    for table in tables:
        cells: List[str] = []
        for row in getattr(table, "rows", []) or []:
            for cell in row:
                if isinstance(cell, str):
                    cells.append(cell)
        for cell_text in cells:
            if not isinstance(cell_text, str):
                continue
            if not DIAGNOSTIC_KEY_PATTERN.search(cell_text):
                continue
            percent = _parse_percent(cell_text)
            numerator = denominator = None
            reasons = set()
            fraction = FRACTION_PATTERN.search(cell_text) or OF_PATTERN.search(cell_text)
            if fraction:
                numerator = int(fraction.group(1))
                denominator = int(fraction.group(2))
            if numerator is None or not denominator:
                reasons.add(ATS_REASON_NO_N_OVER_N)
                if percent is not None:
                    reasons.add(ATS_REASON_DERIVED)
            elif percent is None and denominator:
                percent = round((numerator / denominator) * 100.0, 2)
            return {
                "numerator": numerator,
                "denominator": denominator,
                "percent": percent,
                "reasons": {reason for reason in reasons if reason in ALLOWED_FAILURE_REASONS},
                "evidence_keys": set(),
                "page": getattr(table, "page", None),
                "yield_idx": -1,
                "evidence_text": cell_text.strip(),
            }
    return None


def _find_counts(
    paragraphs: Sequence[Tuple[int, str, Dict[str, object]]],
    idx: int,
) -> Optional[Tuple[int, int, set[str]]]:
    window = range(max(0, idx - 2), min(len(paragraphs), idx + 3))
    fraction_candidates: List[Tuple[int, int, int]] = []
    numerator = None
    denominator = None
    numerator_hash: Optional[str] = None
    denominator_hash: Optional[str] = None
    for neighbor_idx in window:
        neighbor_entry = paragraphs[neighbor_idx][2]
        text = neighbor_entry.get("text")
        if not isinstance(text, str):
            continue
        for match in FRACTION_PATTERN.finditer(text):
            fraction_candidates.append((neighbor_idx, int(match.group(1)), int(match.group(2))))
        for match in OF_PATTERN.finditer(text):
            fraction_candidates.append((neighbor_idx, int(match.group(1)), int(match.group(2))))
        if numerator is None:
            n_match = N_PATTERN.search(text)
            if n_match:
                numerator = int(n_match.group(1))
                numerator_hash = paragraphs[neighbor_idx][1]
        if denominator is None:
            big_match = BIG_N_PATTERN.search(text)
            if big_match:
                denominator = int(big_match.group(1))
                denominator_hash = paragraphs[neighbor_idx][1]

    if fraction_candidates:
        fraction_candidates.sort(key=lambda item: (abs(item[0] - idx), -item[2]))
        best_idx, num, denom = fraction_candidates[0]
        if denom:
            return num, denom, {paragraphs[best_idx][1]}
    if numerator is not None and denominator:
        evidence_keys = {key for key in (numerator_hash, denominator_hash) if key}
        return numerator, denominator, evidence_keys
    return None


def _choose_better_candidate(
    current: Optional[Dict[str, object]],
    candidate: Dict[str, object],
) -> Dict[str, object]:
    if current is None:
        return candidate
    current_score = _score_candidate(current)
    candidate_score = _score_candidate(candidate)
    if candidate_score > current_score:
        return candidate
    return current


def _score_candidate(candidate: Dict[str, object]) -> int:
    score = 0
    if candidate.get("numerator") is not None and candidate.get("denominator"):
        score += 5
    if candidate.get("percent") is not None:
        score += 2
    score -= len(candidate.get("reasons") or [])
    return score


def _parse_percent(text: str) -> Optional[float]:
    match = PERCENT_PATTERN.search(text)
    if not match:
        return None
    value = match.group(1).replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return None


__all__ = ["apply_article_yield_strict_miner"]
