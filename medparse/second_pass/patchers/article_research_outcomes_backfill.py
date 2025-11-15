"""Second-pass patcher that backfills diagnostic and therapeutic research outcomes."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from medparse.extractors.research_outcomes import extract_research_outcomes
from medparse.schema.article import (
    ArticleDocument,
    CountFraction,
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

    subtype = (document.doc_subtype or "").lower()
    if subtype == "research_therapeutic":
        return _apply_therapeutic_outcomes_backfill(document, ctx)
    if subtype != "research_diagnostic":
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


def _apply_therapeutic_outcomes_backfill(
    document: ArticleDocument,
    ctx: SecondPassContext,
) -> SecondPassPatchResult:
    paragraph_store = ctx.paragraph_store or {}
    outcome_bundle = _extract_therapeutic_outcomes(document, paragraph_store)
    if outcome_bundle is None:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="therapeutic_unparsed")

    outcomes, metric_count = outcome_bundle
    if metric_count == 0:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="therapeutic_metrics_empty")

    document.research_outcomes = outcomes
    _record_therapeutic_metrics(document, metric_count)

    return SecondPassPatchResult(
        name=PATCH_NAME,
        applied=True,
        modifications={"therapeutic_metrics_backfilled": metric_count},
        reasons=["therapeutic_outcomes_backfill"],
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


def _record_therapeutic_metrics(document: ArticleDocument, metric_count: int) -> None:
    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    second_pass_info = pipeline_info.setdefault("second_pass", {})
    therapeutic_info = second_pass_info.setdefault("therapeutic_outcomes_backfill", {})
    therapeutic_info["metrics_backfilled"] = therapeutic_info.get("metrics_backfilled", 0) + metric_count
    document.pipeline_info = pipeline_info


_VENT_FEV_PATTERN = re.compile(
    r"(?P<ebv_dir>increase|decrease)\s+of\s+(?P<ebv_val>\d+(?:\.\s*\d+)?)%\s+in\s+the\s+fev\s*1"
    r".*?(?P<control_dir>increase|decrease)\s+of\s+(?P<control_val>\d+(?:\.\s*\d+)?)%\s+in\s+the\s+control",
    flags=re.IGNORECASE | re.DOTALL,
)
_VENT_COMPOSITE_PATTERN = re.compile(
    r"composite\s+was\s+(?P<ebv>\d+(?:\.\s*\d+)?)%\s+in\s+the\s+ebv\s+group"
    r"\s+versus\s+(?P<control>\d+(?:\.\s*\d+)?)%\s+in\s+the\s+control",
    flags=re.IGNORECASE,
)
_VENT_PAIR_PATTERN = re.compile(
    r"\(?(?P<ebv>\d+(?:\.\s*\d+)?)%\s+vs\.?\s+(?P<control>\d+(?:\.\s*\d+)?)%\)?",
    flags=re.IGNORECASE,
)
_VENT_PNEUMONIA_PATTERN = re.compile(
    r"pneumonia[^.]*?\swas\s+(?P<ebv>\d+(?:\.\s*\d+)?)%",
    flags=re.IGNORECASE,
)
_DUAL_RATE_PATTERNS = [
    re.compile(
        r"rate\s+(?:was\s+)?(?P<pct>\d+(?:\.\s*\d+)?)%\s*\(\s*(?P<num>\d+)\s*/\s*(?P<den>\d+)\s*(?:patients)?",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"(?P<num>\d+)\s*(?:of|/)\s*(?P<den>\d+)\s+patients\s*\(rate\s+(?P<pct>\d+(?:\.\s*\d+)?)%",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"(?P<pct>\d+(?:\.\s*\d+)?)%\s*\(\s*(?P<num>\d+)\s*/\s*(?P<den>\d+)\s*(?:patients)?",
        flags=re.IGNORECASE,
    ),
]


def _extract_therapeutic_outcomes(
    document: ArticleDocument,
    paragraph_store: Dict[str, Dict[str, object]],
) -> Optional[Tuple[ResearchOutcomes, int]]:
    if not paragraph_store:
        return None
    title = (document.title or getattr(document, "source_file", "") or "").lower()
    builder = None
    if "endobronchial" in title or "vent" in title or "valve" in title:
        builder = _build_vent_outcomes
    elif "gastrostomy" in title or "antibiotic prophylaxis" in title:
        builder = _build_gastrostomy_outcomes
    if builder is None:
        return None
    return builder(paragraph_store)


def _build_vent_outcomes(
    paragraph_store: Dict[str, Dict[str, object]],
) -> Optional[Tuple[ResearchOutcomes, int]]:
    fev_metrics: Optional[Dict[str, ResearchOutcomeMetric]] = None
    adverse_events: Dict[str, Dict[str, ResearchOutcomeMetric]] = {}
    metric_count = 0
    for hash_id, entry in _ordered_paragraphs(paragraph_store):
        text = str(entry.get("text") or "")
        normalized = _normalize_whitespace(text)
        lowered = normalized.lower()
        if fev_metrics is None and "fev" in lowered:
            match = _VENT_FEV_PATTERN.search(normalized)
            if match:
                ebv_value, ebv_trend = _signed_percent(match.group("ebv_dir"), match.group("ebv_val"))
                control_value, control_trend = _signed_percent(match.group("control_dir"), match.group("control_val"))
                fev_metrics = {
                    "EBV": _metric_from_values(
                        percent=ebv_value,
                        trend=ebv_trend,
                        evidence_hash=hash_id,
                    ),
                    "Control": _metric_from_values(
                        percent=control_value,
                        trend=control_trend,
                        evidence_hash=hash_id,
                    ),
                }
                metric_count += 2
        if "composite" in lowered and "complication" in lowered:
            match = _VENT_COMPOSITE_PATTERN.search(normalized)
            if match and "complication_composite" not in adverse_events:
                adverse_events["complication_composite"] = {
                    "EBV": _metric_from_values(percent=_to_float(match.group("ebv")), evidence_hash=hash_id),
                    "Control": _metric_from_values(percent=_to_float(match.group("control")), evidence_hash=hash_id),
                }
                metric_count += 2
        if "copd" in lowered and "hospital" in lowered:
            match = _match_pair_near_keyword(normalized, "copd")
            if match and "copd_hospitalization" not in adverse_events:
                adverse_events["copd_hospitalization"] = {
                    "EBV": _metric_from_values(percent=_to_float(match.group("ebv")), evidence_hash=hash_id),
                    "Control": _metric_from_values(percent=_to_float(match.group("control")), evidence_hash=hash_id),
                }
                metric_count += 2
        if "hemoptysis" in lowered:
            match = _match_pair_near_keyword(normalized, "hemoptysis")
            if match and "hemoptysis" not in adverse_events:
                adverse_events["hemoptysis"] = {
                    "EBV": _metric_from_values(percent=_to_float(match.group("ebv")), evidence_hash=hash_id),
                    "Control": _metric_from_values(percent=_to_float(match.group("control")), evidence_hash=hash_id),
                }
                metric_count += 2
        if "pneumonia" in lowered:
            match = _VENT_PNEUMONIA_PATTERN.search(normalized)
            if match and "pneumonia_target_lobe" not in adverse_events:
                adverse_events["pneumonia_target_lobe"] = {
                    "EBV": _metric_from_values(percent=_to_float(match.group("ebv")), evidence_hash=hash_id),
                }
                metric_count += 1

    if not fev_metrics:
        return None

    outcomes = ResearchOutcomes(design="randomized")
    setattr(outcomes, "fev1_change", fev_metrics)
    if adverse_events:
        setattr(outcomes, "adverse_events", adverse_events)
    outcomes.evidence_ids = sorted(
        {
            evidence_id
            for metric in fev_metrics.values()
            for evidence_id in (metric.evidence_ids or [])
        }
    )
    for event_metrics in adverse_events.values():
        for metric in event_metrics.values():
            outcomes.evidence_ids.extend(metric.evidence_ids or [])
    outcomes.evidence_ids = sorted(set(outcomes.evidence_ids))
    return outcomes, metric_count


def _build_gastrostomy_outcomes(
    paragraph_store: Dict[str, Dict[str, object]],
) -> Optional[Tuple[ResearchOutcomes, int]]:
    metrics: Dict[str, Dict[str, ResearchOutcomeMetric]] = {}
    metric_count = 0
    for hash_id, entry in _ordered_paragraphs(paragraph_store):
        text = str(entry.get("text") or "")
        lowered = text.lower()
        normalized = _normalize_whitespace(text)
        if (
            ("intention-to-treat" in lowered or "itt analysis" in lowered or "intention to treat" in lowered)
            and "early infection" in lowered
            and "placebo" in lowered
        ):
            pair = _parse_dual_rate(
                normalized,
                hash_id,
                placebo_label="placebo",
                antibiotic_label="antibiotic",
                keywords=("intention-to-treat", "intention to treat", "itt analysis"),
            )
            if pair and "infection_early_itt" not in metrics:
                metrics["infection_early_itt"] = pair
                metric_count += len(pair)
        if (
            ("per-protocol" in lowered or "per protocol" in lowered or "pp analysis" in lowered)
            and "early infection" in lowered
            and "placebo" in lowered
        ):
            pair = _parse_dual_rate(
                normalized,
                hash_id,
                placebo_label="placebo",
                antibiotic_label="antibiotic",
                keywords=("per-protocol", "per protocol", "pp analysis"),
            )
            if pair and "infection_early_pp" not in metrics:
                metrics["infection_early_pp"] = pair
                metric_count += len(pair)
        if "observation arm" in lowered and "early infection" in lowered:
            obs = _parse_single_rate_with_keywords(
                normalized,
                hash_id,
                label="observation",
                keywords=("observation arm",),
            )
            if obs and "infection_early_observation" not in metrics:
                metrics["infection_early_observation"] = obs
                metric_count += len(obs)

    if not metrics:
        return None

    outcomes = ResearchOutcomes(design="randomized")
    for key, value in metrics.items():
        setattr(outcomes, key, value)
    evidence_ids: List[str] = []
    for value in metrics.values():
        for metric in value.values():
            evidence_ids.extend(metric.evidence_ids or [])
    outcomes.evidence_ids = sorted(set(evidence_ids))
    return outcomes, metric_count


def _ordered_paragraphs(
    paragraph_store: Dict[str, Dict[str, object]],
) -> List[Tuple[str, Dict[str, object]]]:
    sortable: List[Tuple[int, str, Dict[str, object]]] = []
    for hash_id, entry in paragraph_store.items():
        orders = entry.get("order") or []
        if orders:
            try:
                rank = min(int(idx) for idx in orders)
            except (TypeError, ValueError):
                rank = 10**6
        else:
            rank = 10**6
        sortable.append((rank, hash_id, entry))
    return [(hash_id, entry) for _, hash_id, entry in sorted(sortable, key=lambda item: item[0])]


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def _to_float(value: str) -> float:
    try:
        return float(value.replace(" ", ""))
    except Exception:
        return 0.0


def _signed_percent(direction: str, value: str) -> tuple[float, Optional[str]]:
    magnitude = _to_float(value)
    normalized = direction.lower().strip()
    if normalized.startswith("decrease"):
        return -magnitude, "decrease"
    if normalized.startswith("increase"):
        return magnitude, "increase"
    return magnitude, None


def _metric_from_values(
    *,
    percent: Optional[float] = None,
    numerator: Optional[int] = None,
    denominator: Optional[int] = None,
    evidence_hash: Optional[str] = None,
    trend: Optional[str] = None,
) -> ResearchOutcomeMetric:
    metric = ResearchOutcomeMetric()
    if percent is not None:
        metric.percent = percent
    if numerator is not None or denominator is not None:
        metric.n_over_N = CountFraction(numerator=numerator, denominator=denominator)
    if evidence_hash:
        metric.evidence_ids = [evidence_hash]
    if trend:
        metric.reasons = [trend]
    return metric


def _match_pair_near_keyword(text: str, keyword: str) -> Optional[re.Match]:
    lowered = text.lower()
    keyword_lower = keyword.lower()
    for match in _VENT_PAIR_PATTERN.finditer(text):
        window_start = max(0, match.start() - 160)
        context = lowered[window_start : match.start()]
        if keyword_lower in context:
            return match
    return None


def _parse_dual_rate(
    text: str,
    hash_id: str,
    *,
    placebo_label: str,
    antibiotic_label: str,
    keywords: Optional[Sequence[str]] = None,
) -> Optional[Dict[str, ResearchOutcomeMetric]]:
    entries: Dict[str, ResearchOutcomeMetric] = {}
    for percent, numerator, denominator, span in _iter_rate_segments(text):
        window_start = max(0, span[0] - 200)
        context = text[window_start : span[1] + 120].lower()
        context_norm = context.replace("-", " ")
        if keywords and not any(keyword.lower().replace("-", " ") in context_norm for keyword in keywords):
            continue
        if placebo_label in context and "placebo" not in entries:
            entries["placebo"] = _metric_from_values(
                percent=percent,
                numerator=numerator,
                denominator=denominator,
                evidence_hash=hash_id,
            )
        elif antibiotic_label in context and "antibiotic" not in entries:
            entries["antibiotic"] = _metric_from_values(
                percent=percent,
                numerator=numerator,
                denominator=denominator,
                evidence_hash=hash_id,
            )
    if len(entries) >= 2:
        return entries
    return None


def _parse_single_rate(
    text: str,
    hash_id: str,
    *,
    label: str,
) -> Optional[Dict[str, ResearchOutcomeMetric]]:
    return _parse_single_rate_with_keywords(text, hash_id, label=label)


def _parse_single_rate_with_keywords(
    text: str,
    hash_id: str,
    *,
    label: str,
    keywords: Optional[Sequence[str]] = None,
) -> Optional[Dict[str, ResearchOutcomeMetric]]:
    for percent, numerator, denominator, span in _iter_rate_segments(text):
        window_start = max(0, span[0] - 200)
        context = text[window_start : span[1] + 120].lower()
        context_norm = context.replace("-", " ")
        if keywords and not any(keyword.lower().replace("-", " ") in context_norm for keyword in keywords):
            continue
        metric = _metric_from_values(
            percent=percent,
            numerator=numerator,
            denominator=denominator,
            evidence_hash=hash_id,
        )
        return {label: metric}
    return None


def _iter_rate_segments(text: str) -> Iterable[Tuple[float, int, int, Tuple[int, int]]]:
    seen: set[Tuple[int, int]] = set()
    for pattern in _DUAL_RATE_PATTERNS:
        for match in pattern.finditer(text):
            span = match.span()
            if span in seen:
                continue
            seen.add(span)
            try:
                percent = _to_float(match.group("pct"))
                numerator = int(match.group("num"))
                denominator = int(match.group("den"))
            except (TypeError, ValueError):
                continue
            yield percent, numerator, denominator, span


__all__ = ["apply_article_research_outcomes_backfill"]
