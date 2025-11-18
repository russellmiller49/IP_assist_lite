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
    StatisticalResult,
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
    stats_results = _extract_statistical_results(paragraph_store)
    added_stats = _merge_statistical_results(document, stats_results)
    if added_stats:
        modifications["statistical_results_backfilled"] = len(added_stats)

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
    stats_results = _extract_statistical_results(paragraph_store)
    added_stats = _merge_statistical_results(document, stats_results)
    modifications = {"therapeutic_metrics_backfilled": metric_count}
    if added_stats:
        modifications["statistical_results_backfilled"] = len(added_stats)
    return SecondPassPatchResult(
        name=PATCH_NAME,
        applied=True,
        modifications=modifications,
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

_STAT_DECIMAL_GAP_PATTERN = re.compile(r"(?<=\d)\.\s+(?=\d)")
_STAT_NEGATIVE_GAP_PATTERN = re.compile(r"(?<=-)\s+(?=\d)")

_ABSTRACT_RESULT_PATTERN = re.compile(
    r"(?P<g1_count>\d+)\s+of\s+(?P<g1_total>\d+)\s+patients\s*\((?P<g1_value>-?\d+(?:\.\d+)?)%\)\s+in\s+the\s+(?P<g1_label>[^.;,]+?)\s+group.*?"
    r"(?P<g2_count>\d+)\s+of\s+(?P<g2_total>\d+)\s+patients\s*\((?P<g2_value>-?\d+(?:\.\d+)?)%\)\s+in\s+the\s+(?P<g2_label>[^.;,]+?)\s+group.*?"
    r"(?:absolute\s+)?difference(?:,\s*|\s+of\s+)?(?P<difference>-?\d+(?:\.\d+)?)\s+(?:percentage\s+points?|percent).*?"
    r"95%\s+confidence\s+interval(?:\s*\[[^\]]+\])?,\s*(?P<ci_lower>-?\d+(?:\.\d+)?)[\s\u00A0]*to[\s\u00A0]*(?P<ci_upper>-?\d+(?:\.\d+)?).*?"
    r"P[\s\u00A0]*[=<>]\s*(?P<p_value>\d+(?:\.\d+)?)(?:\s*(?:for)?\s*(?P<interpretation>[A-Za-z\-\s]+?))?(?:;|\.|$)",
    flags=re.IGNORECASE | re.DOTALL,
)

_GROUP_PERCENT_PATTERN = re.compile(
    r"(?P<value>-?\d+(?:\.\d+)?)%\s+in\s+the\s+(?P<label>[^.;,]+?)\s+group",
    flags=re.IGNORECASE,
)
_DIFF_PERCENT_WITH_P_PATTERN = re.compile(
    r"(?:mean\s+)?(?:between-group\s+)?difference.*?(?P<difference>-?\d+(?:\.\d+)?)%.*?P[\s\u00A0=]*[<=>]?[\s\u00A0]*(?P<p_value>0?\.\d+)",
    flags=re.IGNORECASE | re.DOTALL,
)


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


def _normalize_stat_text(text: str) -> str:
    """Collapse errant spacing produced by PDF extraction so regexes can match."""
    if not text:
        return text
    normalized = text.replace("−", "-").replace("–", "-").replace("—", "-")
    normalized = _STAT_DECIMAL_GAP_PATTERN.sub(".", normalized)
    normalized = _STAT_NEGATIVE_GAP_PATTERN.sub("", normalized)
    return normalized


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


def _extract_statistical_results(
    paragraph_store: Dict[str, Dict[str, object]],
) -> List[StatisticalResult]:
    results_map: Dict[Tuple[str, str, Optional[float], Optional[float]], StatisticalResult] = {}
    order: List[Tuple[str, str, Optional[float], Optional[float]]] = []
    ordered_entries = _ordered_paragraphs(paragraph_store)
    total = len(ordered_entries)
    for idx, (hash_id, entry) in enumerate(ordered_entries):
        text = str(entry.get("text") or "")
        next_text = ""
        if idx + 1 < total:
            next_entry = ordered_entries[idx + 1][1]
            next_text = str(next_entry.get("text") or "")
        combined_text = f"{text} {next_text}".strip()
        if not text:
            continue
        normalized = _normalize_stat_text(_normalize_whitespace(combined_text))
        lowered = normalized.lower()
        if "p=" not in lowered and "p =" not in lowered and "p =" not in lowered and "p<" not in lowered:
            continue
        for matcher in (_match_abstract_stat_result, _match_percent_diff_stat_result):
            result = matcher(normalized, hash_id)
            if result is None:
                continue
            key = (
                _stat_comparison_key(result.comparison or ""),
                (result.outcome or "").lower(),
                result.difference,
                result.p_value,
            )
            existing = results_map.get(key)
            if existing is None:
                results_map[key] = result
                order.append(key)
                continue
            results_map[key] = _merge_stat_result_entry(result, existing)
            break
    return [results_map[key] for key in order]


def _match_abstract_stat_result(text: str, hash_id: str) -> Optional[StatisticalResult]:
    match = _ABSTRACT_RESULT_PATTERN.search(text)
    if not match:
        return None
    comparison = _format_comparison(match.group("g1_label"), match.group("g2_label"))
    window_start = max(0, match.start() - 200)
    outcome = _infer_outcome_label(text[window_start : match.end()])
    interpretation = match.group("interpretation")
    cleaned_interp = _clean_interpretation(interpretation)
    result = StatisticalResult(
        comparison=comparison,
        outcome=outcome,
        group1_value=_safe_float(match.group("g1_value")),
        group1_n=_safe_int(match.group("g1_total")),
        group2_value=_safe_float(match.group("g2_value")),
        group2_n=_safe_int(match.group("g2_total")),
        difference=_safe_float(match.group("difference")),
        ci_lower=_safe_float(match.group("ci_lower")),
        ci_upper=_safe_float(match.group("ci_upper")),
        p_value=_safe_float(match.group("p_value")),
        interpretation=cleaned_interp,
        test=cleaned_interp or None,
        evidence_refs=[hash_id],
    )
    return result


def _match_percent_diff_stat_result(text: str, hash_id: str) -> Optional[StatisticalResult]:
    groups = list(_GROUP_PERCENT_PATTERN.finditer(text))
    if len(groups) < 2:
        return None
    g1, g2 = groups[0], groups[1]
    diff_subtext = text[g2.end() :]
    diff_match = _DIFF_PERCENT_WITH_P_PATTERN.search(diff_subtext)
    diff_offset = g2.end()
    if not diff_match:
        diff_match = _DIFF_PERCENT_WITH_P_PATTERN.search(text)
        diff_offset = 0
    if not diff_match:
        return None
    comparison = _format_comparison(g1.group("label"), g2.group("label"))
    window_start = max(0, g1.start() - 200)
    diff_end = diff_match.end() + diff_offset
    outcome = _infer_outcome_label(text[window_start:diff_end])
    result = StatisticalResult(
        comparison=comparison,
        outcome=outcome,
        group1_value=_safe_float(g1.group("value")),
        group2_value=_safe_float(g2.group("value")),
        difference=_safe_float(diff_match.group("difference")),
        p_value=_safe_float(diff_match.group("p_value")),
        evidence_refs=[hash_id],
    )
    return result


def _merge_statistical_results(
    document: ArticleDocument,
    stats: List[StatisticalResult],
) -> List[StatisticalResult]:
    if not stats:
        return []
    existing = getattr(document, "statistical_results", []) or []
    seen = {
        (
            entry.comparison or "",
            entry.outcome or "",
            tuple(entry.evidence_refs or []),
        )
        for entry in existing
    }
    appended: List[StatisticalResult] = []
    for stat in stats:
        key = (
            stat.comparison or "",
            stat.outcome or "",
            tuple(stat.evidence_refs or []),
        )
        if key in seen:
            continue
        existing.append(stat)
        appended.append(stat)
        seen.add(key)
    document.statistical_results = existing
    return appended


def _stat_result_quality(result: StatisticalResult) -> int:
    score = 0
def _merge_stat_result_entry(
    primary: StatisticalResult,
    secondary: StatisticalResult,
) -> StatisticalResult:
    merged = primary.model_copy(deep=True)
    for field in (
        "group1_value",
        "group1_n",
        "group2_value",
        "group2_n",
        "difference",
        "ci_lower",
        "ci_upper",
        "p_value",
        "interpretation",
        "test",
    ):
        existing_value = getattr(merged, field)
        new_value = getattr(secondary, field)
        if existing_value is None and new_value is not None:
            setattr(merged, field, new_value)
    refs = set(merged.evidence_refs or [])
    refs.update(secondary.evidence_refs or [])
    merged.evidence_refs = sorted(refs) if refs else None
    return merged


def _format_comparison(label_a: str, label_b: str) -> str:
    def _clean(label: str) -> str:
        cleaned = label.replace("group", "").strip(" .")
        cleaned = re.sub(r"-\s+", "", cleaned)
        return re.sub(r"\s+", " ", cleaned)

    return f"{_clean(label_a)} vs {_clean(label_b)}".strip()


def _stat_comparison_key(value: str) -> str:
    normalized = re.sub(r"-\s+", "", value or "")
    return re.sub(r"\s+", " ", normalized).strip().lower()


def _clean_interpretation(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = value.strip(" .;:,").lower()
    if not cleaned:
        return None
    return cleaned


def _safe_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        cleaned = value.replace(" ", "").replace("−", "-").replace("<", "").replace(">", "")
        return float(cleaned)
    except (TypeError, ValueError, AttributeError):
        return None


def _safe_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value.replace(" ", ""))
    except (TypeError, ValueError, AttributeError):
        return None


def _infer_outcome_label(text: str) -> Optional[str]:
    lowered = text.lower()
    if "diagnostic accuracy" in lowered:
        return "diagnostic_accuracy"
    if "diagnostic yield" in lowered:
        return "diagnostic_yield"
    if "fev" in lowered:
        return "fev1"
    if "walk test" in lowered or "6-minute" in lowered:
        return "six_minute_walk"
    if "pneumothorax" in lowered:
        return "pneumothorax"
    if "hemoptysis" in lowered:
        return "hemoptysis"
    if "complication" in lowered:
        return "complications"
    diag_markers = ("navigational bronchoscopy", "transthoracic needle biopsy", "noninferiority")
    if any(marker in lowered for marker in diag_markers):
        return "diagnostic_accuracy"
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
