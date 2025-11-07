"""Second-pass patcher that backfills guideline recommendation grades."""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from medparse.schema.article import ArticleDocument, GuidelineRecommendation
from medparse.schema.common import BaseDocument

from ..types import SecondPassContext, SecondPassPatchResult

PATCH_NAME = "guideline_grade_backfill"

GRADE_CODE_RE = re.compile(r"\bgrade\s*(?:of\s*)?([12][abc])\b", re.IGNORECASE)
STRENGTH_RE = re.compile(r"\b(strong|conditional|weak)\s+(?:recommendation|suggestion)\b", re.IGNORECASE)
CERTAINTY_RE = re.compile(r"\b(very\s+low|low|moderate|high)\s+(?:certainty|quality|evidence)\b", re.IGNORECASE)
BEST_PRACTICE_RE = re.compile(r"\b(best\s+practice\s+statement)\b", re.IGNORECASE)

STRENGTH_FROM_CODE = {"1": "strong", "2": "conditional"}
QUALITY_FROM_CODE = {"A": "high", "B": "moderate", "C": "low"}


def _collect_context_snippets(rec: GuidelineRecommendation, paragraph_store: Dict[str, Dict[str, object]]) -> List[str]:
    snippets: List[str] = []
    refs: List[str] = []
    if rec.evidence_refs:
        refs.extend(rec.evidence_refs)
    if rec.anchors:
        refs.extend(rec.anchors)
    if rec.evidence and getattr(rec.evidence, "paragraph_hash", None):
        refs.append(rec.evidence.paragraph_hash)
    seen: set[str] = set()
    for ref in refs:
        if not ref or ref in seen:
            continue
        seen.add(ref)
        text = paragraph_store.get(ref, {}).get("text")
        if isinstance(text, str):
            snippets.append(text)

    # Include immediate recommendation text as last resort
    if rec.text:
        snippets.append(rec.text)
    return snippets


def _normalize_best_practice(rec: GuidelineRecommendation) -> None:
    rec.statement_type = "consensus"
    rec.ungraded = True
    rec.ungraded_reason = "best_practice_statement"
    rec.grade = None
    rec.grade_normalized = {"value": "Best Practice Statement", "source": "context"}
    rec.strength = None
    rec.strength_scale = None


def _apply_normalized_payload(rec: GuidelineRecommendation, *, code: Optional[str], strength: Optional[str], certainty: Optional[str]) -> None:
    normalized: Dict[str, object] = {"source": "context"}
    if code:
        normalized["code"] = code
        normalized["scale"] = "CHEST/ATS"
    if strength:
        normalized["strength"] = strength
    if certainty:
        normalized["quality"] = certainty
        normalized["evidence_quality"] = certainty
    if code and certainty:
        normalized["value"] = f"{code} ({strength or ''}, {certainty})".strip(", ")
    rec.grade_normalized = normalized
    if code:
        rec.grade = code
    elif strength:
        rec.grade = strength.title()
    rec.statement_type = "graded"
    rec.ungraded = False
    rec.ungraded_reason = None
    if strength:
        rec.strength = strength
    if certainty:
        rec.evidence_level = certainty


def apply_guideline_grade_backfill(document: BaseDocument, ctx: SecondPassContext) -> SecondPassPatchResult:
    if not isinstance(document, ArticleDocument):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="doc_not_article")

    subtype = (getattr(document, "doc_subtype", "") or "").lower()
    if subtype not in {"guideline", "statement", "classification"}:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason=f"subtype_{subtype or 'unknown'}")

    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    second_pass_bucket = pipeline_info.setdefault("second_pass", {})
    applied = second_pass_bucket.get("patches_applied") or []
    if isinstance(applied, list) and PATCH_NAME in applied:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="already_applied")

    recommendations = document.recommendations or []
    if not recommendations:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_recommendations")

    triggers = [
        issue
        for issue in ctx.validation_issues
        if "grade" in issue.message.lower() or "ungraded" in issue.message.lower()
    ]
    if ctx.mode == "auto" and not triggers:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="auto_mode_no_trigger")

    paragraph_store = ctx.paragraph_store
    backfilled = 0
    retyped = 0

    for rec in recommendations:
        has_grade = bool(rec.grade or (rec.grade_normalized and isinstance(rec.grade_normalized, dict)))
        if has_grade and not rec.ungraded:
            continue

        snippets = _collect_context_snippets(rec, paragraph_store)
        if not snippets:
            continue

        code_match = None
        strength_match = None
        certainty_match = None
        best_practice = False

        for snippet in snippets:
            lowered = snippet.lower()
            if not code_match:
                match = GRADE_CODE_RE.search(snippet)
                if match:
                    code_match = match.group(1).upper()
            if not strength_match:
                match = STRENGTH_RE.search(snippet)
                if match:
                    strength_match = match.group(1).lower()
            if not certainty_match:
                match = CERTAINTY_RE.search(snippet)
                if match:
                    certainty_match = match.group(1).lower()
            if not best_practice and BEST_PRACTICE_RE.search(lowered):
                best_practice = True

        if code_match or strength_match or certainty_match:
            strength = strength_match or STRENGTH_FROM_CODE.get(code_match[0] if code_match else "")
            certainty = certainty_match or QUALITY_FROM_CODE.get(code_match[1] if code_match else "")
            _apply_normalized_payload(rec, code=code_match, strength=strength, certainty=certainty)
            backfilled += 1
        elif best_practice:
            _normalize_best_practice(rec)
            retyped += 1
        else:
            rec.statement_type = "ungraded"
            rec.ungraded = True
            rec.ungraded_reason = "no_grade_phrase_found"
            rec.grade = None
            rec.grade_normalized = {"source": "context", "reason": "no_grade_phrase_found"}
            retyped += 1

    if not backfilled and not retyped:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_changes")

    pipeline_info["grade_backfilled"] = backfilled
    pipeline_info["recommendations_retyped"] = retyped
    pipeline_info.setdefault("second_pass", {}).setdefault("patches_applied", [])
    document.pipeline_info = pipeline_info

    return SecondPassPatchResult(
        name=PATCH_NAME,
        applied=True,
        modifications={
            "grade_backfilled": backfilled,
            "recommendations_retyped": retyped,
        },
        reasons=["guideline_grade_backfill"],
    )
