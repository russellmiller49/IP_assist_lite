"""Patcher registry for the second-pass orchestrator."""

from __future__ import annotations

from typing import Dict, List

from medparse.second_pass.types import SecondPassPatcher

from .article_affiliation_softmap import apply_affiliation_softmap
from .article_affiliations import apply_article_affiliations
from .article_section_fix import apply_sectionizer_salvage
from .article_yield_strict_miner import apply_article_yield_strict_miner
from .article_research_outcomes_backfill import apply_article_research_outcomes_backfill
from .article_yield_ats_fixer import apply_yield_ats_fixer
from .guideline_grade_backfill import apply_guideline_grade_backfill
from .ifu_frontmatter_backfill import apply_ifu_frontmatter_backfill
from .ifu_indications_fallback import apply_ifu_indications_fallback
from .ifu_intended_use_backfill import apply_ifu_intended_use_backfill
from .ifu_manufacturer_overrides import apply_ifu_manufacturer_overrides
from .ifu_references_anchor import apply_ifu_references_anchor
from .ifu_safety_density_booster import apply_ifu_safety_density_booster
from .ifu_sectionizer_salvage import apply_ifu_sectionizer_salvage
from .ifu_small import apply_ifu_small_leaflet_map
from .ifu_toc_guard_refine import apply_ifu_toc_guard_refine

_ORDERED_PATCHERS: Dict[str, List[SecondPassPatcher]] = {
    "article": [
        apply_yield_ats_fixer,
        apply_sectionizer_salvage,
        apply_article_yield_strict_miner,
        apply_article_research_outcomes_backfill,
        apply_guideline_grade_backfill,
        apply_article_affiliations,
        apply_affiliation_softmap,
    ],
    "guideline": [
        apply_yield_ats_fixer,
        apply_sectionizer_salvage,
        apply_article_yield_strict_miner,
        apply_guideline_grade_backfill,
        apply_article_affiliations,
        apply_affiliation_softmap,
    ],
    "ifu": [
        apply_ifu_frontmatter_backfill,
        apply_ifu_toc_guard_refine,
        apply_ifu_small_leaflet_map,
        apply_ifu_intended_use_backfill,
        apply_ifu_indications_fallback,
        apply_ifu_safety_density_booster,
        apply_ifu_references_anchor,
        apply_ifu_sectionizer_salvage,
        apply_ifu_manufacturer_overrides,
    ],
}


def get_patchers_for(doc_type: str) -> List[SecondPassPatcher]:
    """Return ordered patchers for the supplied document type."""

    normalized = str(doc_type or "").strip().lower()
    if normalized in {"guideline", "article"}:
        normalized = "article"
    return list(_ORDERED_PATCHERS.get(normalized, []))


__all__ = ["get_patchers_for"]
