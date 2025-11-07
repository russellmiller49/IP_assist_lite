"""Second-pass patcher that maps affiliations to authors when enrichment is sparse."""

from __future__ import annotations

from typing import Dict, List, Optional

from medparse.schema.article import ArticleDocument, Author
from medparse.schema.common import BaseDocument

from ..types import SecondPassContext, SecondPassPatchResult

PATCH_NAME = "affiliation_softmap"


def _assign_all(authors: List[Author], affiliation_id: str) -> int:
    applied = 0
    for author in authors:
        ids = list(author.affiliation_ids or [])
        if affiliation_id not in ids:
            ids.append(affiliation_id)
            author.affiliation_ids = ids
            applied += 1
    return applied


def apply_affiliation_softmap(document: BaseDocument, ctx: SecondPassContext) -> SecondPassPatchResult:
    if not isinstance(document, ArticleDocument):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="doc_not_article")

    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    second_pass_bucket = pipeline_info.setdefault("second_pass", {})
    applied = second_pass_bucket.get("patches_applied") or []
    if isinstance(applied, list) and PATCH_NAME in applied:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="already_applied")

    authors = document.authors or []
    affiliations = document.affiliations or []
    if not authors or not affiliations:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="missing_people")

    triggers = [
        issue for issue in ctx.validation_issues if "affiliation" in issue.message.lower()
    ]
    if ctx.mode == "auto" and not triggers:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="auto_mode_no_trigger")

    modifications = 0
    if len(affiliations) == 1:
        affiliation_id = affiliations[0].id or "1"
        modifications = _assign_all(authors, affiliation_id)
    else:
        aff_lookup: Dict[str, str] = {}
        for affiliation in affiliations:
            if affiliation.id:
                aff_lookup[str(affiliation.id).lower()] = affiliation.id
        # Fallback mapping by footnote symbols
        for idx, author in enumerate(authors):
            ids = list(author.affiliation_ids or [])
            if ids:
                continue
            mapped_id: Optional[str] = None
            for symbol in author.footnote_symbols or []:
                normalized = str(symbol or "").strip().lower()
                if not normalized:
                    continue
                if normalized in aff_lookup:
                    mapped_id = aff_lookup[normalized]
                    break
            if mapped_id is None:
                # fallback to positional mapping
                if idx < len(affiliations):
                    mapped_id = affiliations[idx].id or str(idx + 1)
            if mapped_id is None:
                continue
            ids.append(mapped_id)
            author.affiliation_ids = list(dict.fromkeys(ids))
            modifications += 1

    if modifications == 0:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_changes")

    pipeline_info["affiliation_softmap_applied"] = True
    pipeline_info.setdefault("second_pass", {}).setdefault("patches_applied", [])
    document.pipeline_info = pipeline_info

    return SecondPassPatchResult(
        name=PATCH_NAME,
        applied=True,
        modifications={"affiliations_mapped": modifications},
        reasons=["affiliation_softmap"],
    )
