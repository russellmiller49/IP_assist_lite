"""Second-pass patcher that resolves misclassified research subtypes."""

from __future__ import annotations

import re
from typing import Dict

from medparse.schema.article import ArticleDocument
from medparse.second_pass.types import SecondPassContext, SecondPassPatchResult

PATCH_NAME = "article_subtype_resolve"
_BANNER_PATTERN = re.compile(r"\boriginal\s+article\b", re.IGNORECASE)
_IMRAD_TERMS = {
    "introduction",
    "materials and methods",
    "methods",
    "patients and methods",
    "results",
    "discussion",
}


def apply_article_subtype_resolve(
    document: ArticleDocument,
    ctx: SecondPassContext,
) -> SecondPassPatchResult:
    if not isinstance(document, ArticleDocument):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="doc_not_article")

    subtype = (document.doc_subtype or "").lower()
    if subtype == "research_therapeutic":
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="already_research")

    paragraph_store = ctx.paragraph_store or {}
    if not _has_original_article_banner(paragraph_store):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="banner_missing")

    if not _has_imrad_sections(document):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="imrad_missing")

    document.doc_subtype = "research_therapeutic"
    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    reasons = pipeline_info.setdefault("second_pass_reasons", [])
    if isinstance(reasons, list):
        reason_tag = "doc_subtype:research_therapeutic"
        if reason_tag not in reasons:
            reasons.append(reason_tag)
    document.pipeline_info = pipeline_info

    return SecondPassPatchResult(
        name=PATCH_NAME,
        applied=True,
        reasons=["doc_subtype:research_therapeutic"],
        modifications={"doc_subtype_updated": 1},
    )


def _has_original_article_banner(paragraph_store: Dict[str, Dict[str, object]]) -> bool:
    for entry in paragraph_store.values():
        try:
            page = int(entry.get("page") or 0)
        except (TypeError, ValueError):
            page = 0
        if page > 1:
            continue
        text = entry.get("text")
        if not isinstance(text, str):
            continue
        if _BANNER_PATTERN.search(text):
            return True
    return False


def _has_imrad_sections(document: ArticleDocument) -> bool:
    sections = getattr(document, "sections", {}) or {}
    if not isinstance(sections, dict):
        return False
    normalized = {str(name or "").strip().lower() for name in sections.keys()}
    hits = 0
    for term in _IMRAD_TERMS:
        if term in normalized:
            hits += 1
    return hits >= 3
