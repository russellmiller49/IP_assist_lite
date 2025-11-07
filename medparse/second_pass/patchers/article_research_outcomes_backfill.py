"""Second-pass patcher that backfills diagnostic research outcomes."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from medparse.extractors.research_outcomes import extract_research_outcomes
from medparse.schema.article import (
    ArticleDocument,
    ResearchOutcomeArm,
    ResearchOutcomeMetric,
    ResearchOutcomes,
)
from medparse.second_pass.types import SecondPassContext, SecondPassPatchResult

PATCH_NAME = "article_research_outcomes_backfill"


def apply_article_research_outcomes_backfill(
    document: ArticleDocument,
    ctx: SecondPassContext,
) -> SecondPassPatchResult:
    if not isinstance(document, ArticleDocument):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="doc_not_article")

    if (document.doc_subtype or "").lower() != "research_diagnostic":
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="subtype")

    existing = getattr(document, "research_outcomes", None)
    needs_accuracy, needs_yield = _research_outcomes_needed(existing)
    if not needs_accuracy and not needs_yield:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_missing_outcomes")

    paragraph_store = getattr(document, "paragraph_store", {}) or {}
    evidence_bank = getattr(document, "evidence_bank", {}) or {}

    extracted = extract_research_outcomes(document, paragraph_store, evidence_bank, document.doc_subtype or "")
    if extracted is None:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="extractor_empty")

    result_outcomes, accuracy_count, yield_count, complication_count = _merge_outcomes(existing, extracted)
    if accuracy_count == 0 and yield_count == 0 and complication_count == 0:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_updates")

    document.research_outcomes = result_outcomes
    _record_backfill_metrics(document, accuracy_count, yield_count, complication_count)

    modifications: Dict[str, int] = {}
    if accuracy_count:
        modifications["diagnostic_accuracy_backfilled"] = accuracy_count
    if yield_count:
        modifications["diagnostic_yield_backfilled"] = yield_count
    if complication_count:
        modifications["complications_backfilled"] = complication_count

    return SecondPassPatchResult(
        name=PATCH_NAME,
        applied=True,
        modifications=modifications,
        reasons=["research_outcomes_backfill"],
    )


def _research_outcomes_needed(outcomes: Optional[ResearchOutcomes]) -> tuple[bool, bool]:
    if outcomes is None:
        return True, True
    needs_accuracy = not _metric_has_value(getattr(outcomes, "diagnostic_accuracy", None))
    needs_yield = not _metric_has_value(getattr(outcomes, "diagnostic_yield", None))
    for arm in getattr(outcomes, "arms", []) or []:
        needs_accuracy = needs_accuracy or not _metric_has_value(getattr(arm, "diagnostic_accuracy", None))
        needs_yield = needs_yield or not _metric_has_value(getattr(arm, "diagnostic_yield", None))
    return needs_accuracy, needs_yield


def _merge_outcomes(
    existing: Optional[ResearchOutcomes],
    extracted: ResearchOutcomes,
) -> tuple[ResearchOutcomes, int, int, int]:
    if existing is None:
        accuracy_total = _count_accuracy_metrics(extracted)
        yield_total = _count_yield_metrics(extracted)
        complications_total = _count_complication_metrics(extracted)
        return extracted, accuracy_total, yield_total, complications_total

    result = existing.model_copy(deep=True)
    accuracy_updates = 0
    yield_updates = 0
    complication_updates = 0

    result.diagnostic_accuracy, updated = _merge_metric(result.diagnostic_accuracy, extracted.diagnostic_accuracy)
    if updated:
        accuracy_updates += 1
    result.diagnostic_yield, updated = _merge_metric(result.diagnostic_yield, extracted.diagnostic_yield)
    if updated:
        yield_updates += 1

    for comp_key, metric in (extracted.complications or {}).items():
        merged, updated = _merge_metric(result.complications.get(comp_key), metric)
        if updated:
            result.complications[comp_key] = merged
            complication_updates += 1

    existing_arms: Dict[str, ResearchOutcomeArm] = {arm.name: arm for arm in result.arms}
    for new_arm in extracted.arms:
        base = existing_arms.get(new_arm.name)
        if base is None:
            result.arms.append(new_arm)
            accuracy_updates += 1 if _metric_has_value(new_arm.diagnostic_accuracy) else 0
            yield_updates += 1 if _metric_has_value(new_arm.diagnostic_yield) else 0
            complication_updates += len([metric for metric in (new_arm.complications or {}).values() if _metric_has_value(metric)])
            continue
        merged_accuracy, updated = _merge_metric(base.diagnostic_accuracy, new_arm.diagnostic_accuracy)
        if updated:
            base.diagnostic_accuracy = merged_accuracy
            accuracy_updates += 1
        merged_yield, updated = _merge_metric(base.diagnostic_yield, new_arm.diagnostic_yield)
        if updated:
            base.diagnostic_yield = merged_yield
            yield_updates += 1
        for comp_key, metric in (new_arm.complications or {}).items():
            merged_metric, updated = _merge_metric(base.complications.get(comp_key), metric)
            if updated:
                base.complications[comp_key] = merged_metric
                complication_updates += 1

    return result, accuracy_updates, yield_updates, complication_updates


def _merge_metric(
    existing: Optional[ResearchOutcomeMetric],
    new: Optional[ResearchOutcomeMetric],
) -> tuple[Optional[ResearchOutcomeMetric], bool]:
    if new is None or not _metric_has_value(new):
        return existing, False
    if existing is None or not _metric_has_value(existing):
        return new.model_copy(deep=True), True

    merged = existing.model_copy(deep=True)
    updated = False
    if merged.percent is None and new.percent is not None:
        merged.percent = new.percent
        updated = True
    if (merged.n_over_N is None or (merged.n_over_N and merged.n_over_N.numerator is None)) and new.n_over_N is not None:
        merged.n_over_N = new.n_over_N
        updated = True
    if merged.ci_95 is None and new.ci_95 is not None:
        merged.ci_95 = new.ci_95
        updated = True
    if merged.p_value is None and new.p_value is not None:
        merged.p_value = new.p_value
        updated = True
    if merged.evidence_ids is None:
        merged.evidence_ids = []
    new_ids = new.evidence_ids or []
    if new_ids:
        existing_ids = set(merged.evidence_ids)
        for evidence_id in new_ids:
            if evidence_id not in existing_ids:
                merged.evidence_ids.append(evidence_id)
                existing_ids.add(evidence_id)
                updated = True
    return merged, updated


def _metric_has_value(metric: Optional[ResearchOutcomeMetric]) -> bool:
    if metric is None:
        return False
    if metric.percent is not None:
        return True
    if metric.ci_95:
        return True
    if metric.p_value is not None:
        return True
    if metric.n_over_N and (metric.n_over_N.numerator is not None or metric.n_over_N.denominator is not None):
        return True
    if metric.evidence_ids:
        return True
    return False


def _count_accuracy_metrics(outcomes: ResearchOutcomes) -> int:
    total = 1 if _metric_has_value(outcomes.diagnostic_accuracy) else 0
    total += sum(1 for arm in outcomes.arms if _metric_has_value(arm.diagnostic_accuracy))
    return total


def _count_yield_metrics(outcomes: ResearchOutcomes) -> int:
    total = 1 if _metric_has_value(outcomes.diagnostic_yield) else 0
    total += sum(1 for arm in outcomes.arms if _metric_has_value(arm.diagnostic_yield))
    return total


def _count_complication_metrics(outcomes: ResearchOutcomes) -> int:
    total = sum(1 for metric in (outcomes.complications or {}).values() if _metric_has_value(metric))
    for arm in outcomes.arms:
        total += sum(1 for metric in (arm.complications or {}).values() if _metric_has_value(metric))
    return total


def _record_backfill_metrics(
    document: ArticleDocument,
    accuracy_count: int,
    yield_count: int,
    complication_count: int,
) -> None:
    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    second_pass_info = pipeline_info.setdefault("second_pass", {})
    outcomes_info = second_pass_info.setdefault("research_outcomes_backfill", {})
    outcomes_info["accuracy_backfilled"] = outcomes_info.get("accuracy_backfilled", 0) + accuracy_count
    outcomes_info["yield_backfilled"] = outcomes_info.get("yield_backfilled", 0) + yield_count
    outcomes_info["complications_backfilled"] = outcomes_info.get("complications_backfilled", 0) + complication_count
    document.pipeline_info = pipeline_info


__all__ = ["apply_article_research_outcomes_backfill"]
