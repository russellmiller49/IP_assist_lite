"""Research outcomes extractor for diagnostic trials."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from medparse.schema.article import (
    ArticleDocument,
    CountFraction,
    ResearchOutcomeArm,
    ResearchOutcomeMetric,
    ResearchOutcomes,
)
from medparse.utils.log import get_logger

LOGGER = get_logger(__name__)
ALLOWED_REASON_KEYS = {
    "no_n_over_N",
    "derived_counts_from_percent",
    "follow_up_used_in_numerator",
    "nonspecific_counts_included",
}

ARM_ALIASES: Dict[str, str] = {
    "navigational bronchoscopy": "navigational bronchoscopy",
    "navigational bronchoscopy group": "navigational bronchoscopy",
    "navigation bronchoscopy": "navigational bronchoscopy",
    "navigational-bronchoscopy": "navigational bronchoscopy",
    "transthoracic needle biopsy": "transthoracic needle biopsy",
    "transthoracic needle-biopsy": "transthoracic needle biopsy",
    "transthoracic needle biopsy group": "transthoracic needle biopsy",
    "needle biopsy": "transthoracic needle biopsy",
}

GROUPED_COUNT_PATTERN = re.compile(
    r"in\s+(?P<num>\d+)\s+of\s+(?P<den>\d+)\s+(?:patients?|cases?)\s*\("
    r"(?P<pct>\d+(?:\.\s*\d+)?)%\)\s+in\s+the\s+(?P<arm>[^;,.]+?)\s+group",
    flags=re.IGNORECASE,
)

SIMPLE_COUNT_PATTERN = re.compile(
    r"(?:in|and)\s+(?P<num>\d+)\s+patients?\s*\((?P<pct>\d+(?:\.\s*\d+)?)%\)",
    flags=re.IGNORECASE,
)

CI_PATTERN = re.compile(
    r"95%\s*(?:confidence\s*interval|ci)[^-\d]*"
    r"(?P<lower>[−\-–]?\s*\d+(?:\.\s*\d+)?)\s*(?:to|,)\s*"
    r"(?P<upper>[−\-–]?\s*\d+(?:\.\s*\d+)?)",
    flags=re.IGNORECASE,
)

P_VALUE_PATTERN = re.compile(
    r"P\s*=\s*(?P<pval>\d+(?:\.\s*\d+)?)",
    flags=re.IGNORECASE,
)


def extract_research_outcomes(
    document: ArticleDocument,
    paragraph_store: Dict[str, Dict[str, object]] | None,
    evidence_bank: Dict[str, object] | None,
    subtype: str,
) -> Optional[ResearchOutcomes]:
    """Parse diagnostic research outcomes from article text."""

    if subtype.strip().lower() != "research_diagnostic":
        return None
    if not isinstance(paragraph_store, dict) or not paragraph_store:
        return None

    extractor = _ResearchOutcomesExtractor(document=document, paragraph_store=paragraph_store)
    outcomes = extractor.run()
    if outcomes is None:
        return None

    design = _infer_design(document.sections or {})
    if design and not outcomes.design:
        outcomes.design = design

    primary_outcome = _infer_primary_outcome(document.sections or {})
    if primary_outcome and not outcomes.primary_outcome:
        outcomes.primary_outcome = primary_outcome

    return outcomes


class _ResearchOutcomesExtractor:
    """Stateful extractor for research outcomes."""

    def __init__(self, document: ArticleDocument, paragraph_store: Dict[str, Dict[str, object]]) -> None:
        self.document = document
        self.paragraph_store = paragraph_store
        self.arms: Dict[str, ResearchOutcomeArm] = {}
        self.arm_order: List[str] = []
        self.doc_accuracy: Optional[ResearchOutcomeMetric] = None
        self.doc_yield: Optional[ResearchOutcomeMetric] = None
        self.doc_complications: Dict[str, ResearchOutcomeMetric] = {}
        self._pending_ci: Optional[Dict[str, object]] = None

    def run(self) -> Optional[ResearchOutcomes]:
        for hash_id, entry in self.paragraph_store.items():
            text = str(entry.get("text") or "").strip()
            if not text:
                continue
            lowered = text.lower()
            if not _paragraph_relevant(lowered):
                continue
            self._parse_paragraph(hash_id, text, lowered)

        if _needs_diagnostic_ci(self.doc_accuracy):
            fallback_ci, fallback_hash = _fallback_diagnostic_ci(self.paragraph_store)
            if fallback_ci and all(value is not None for value in fallback_ci):
                self.doc_accuracy = self.doc_accuracy or ResearchOutcomeMetric()
                self.doc_accuracy.ci_95 = fallback_ci
                if fallback_hash:
                    self._update_metric(self.doc_accuracy, evidence_hash=fallback_hash)
                if self.arm_order:
                    arm = self._ensure_arm(self.arm_order[0])
                    metric = self._ensure_arm_metric(arm, "diagnostic_accuracy")
                    metric.ci_95 = fallback_ci
                    if fallback_hash:
                        self._update_metric(metric, evidence_hash=fallback_hash)

        if not self.arms and not _metric_has_content(self.doc_accuracy) and not _metric_has_content(self.doc_yield):
            return None

        bundle = ResearchOutcomes()
        if _metric_has_content(self.doc_accuracy):
            bundle.diagnostic_accuracy = self.doc_accuracy
        if _metric_has_content(self.doc_yield):
            bundle.diagnostic_yield = self.doc_yield
        if self.doc_complications:
            bundle.complications = {
                key: metric for key, metric in self.doc_complications.items() if _metric_has_content(metric)
            }

        bundle.arms = self._finalize_arms()
        bundle.evidence_ids = sorted(_collect_bundle_evidence(bundle))
        _sanitize_bundle_reasons(bundle)
        return bundle

    def _parse_paragraph(self, hash_id: str, text: str, lowered: str) -> None:
        if self._pending_ci:
            combined_text = f"{self._pending_ci['text']} {text}"
            arm_sequence_prev = list(self._pending_ci.get("arm_sequence") or [])
            base_hash = str(self._pending_ci.get("hash") or hash_id)
            applied = self._apply_confidence_interval(base_hash, combined_text, arm_sequence_prev)
            if applied:
                self._append_ci_evidence(arm_sequence_prev, hash_id)
                self._pending_ci = None
            else:
                self._pending_ci["text"] = combined_text
                self._pending_ci["hash"] = base_hash
                self._pending_ci["arm_sequence"] = arm_sequence_prev

        arm_sequence: List[str] = []
        for match in GROUPED_COUNT_PATTERN.finditer(text):
            arm_name = _normalize_arm_name(match.group("arm"))
            if not arm_name:
                continue
            if arm_name not in arm_sequence:
                arm_sequence.append(arm_name)
            arm = self._ensure_arm(arm_name)
            percent = _safe_float(match.group("pct"))
            numerator = _safe_int(match.group("num"))
            denominator = _safe_int(match.group("den"))

            match_context = lowered[max(0, match.start() - 200):match.end() + 80]
            if "pneumothorax" in match_context:
                metric = self._ensure_complication_metric(arm, "pneumothorax_any")
                self._update_metric(metric, percent=percent, numerator=numerator, denominator=denominator, evidence_hash=hash_id)
                _apply_context_reasons(metric, match_context)
            elif "complication" in match_context and "diagnostic accuracy" not in match_context:
                metric = self._ensure_complication_metric(arm, "complication_any")
                self._update_metric(metric, percent=percent, numerator=numerator, denominator=denominator, evidence_hash=hash_id)
                _apply_context_reasons(metric, match_context)
            elif _is_diagnostic_yield_paragraph(match_context):
                metric = self._ensure_arm_metric(arm, "diagnostic_yield")
                self._update_metric(metric, percent=percent, numerator=numerator, denominator=denominator, evidence_hash=hash_id)
                _apply_context_reasons(metric, match_context)
                self.doc_yield = self.doc_yield or ResearchOutcomeMetric()
                self._update_metric(self.doc_yield, evidence_hash=hash_id)
            else:
                metric = self._ensure_arm_metric(arm, "diagnostic_accuracy")
                self._update_metric(metric, percent=percent, numerator=numerator, denominator=denominator, evidence_hash=hash_id)
                _apply_context_reasons(metric, match_context)
                self.doc_accuracy = self.doc_accuracy or ResearchOutcomeMetric()
                self._update_metric(self.doc_accuracy, evidence_hash=hash_id)

        if "pneumothorax" in lowered:
            self._parse_severe_complications(hash_id, text, lowered, arm_sequence)

        applied_ci = self._apply_confidence_interval(hash_id, text, arm_sequence)
        if not applied_ci and "95% confidence interval" in lowered and self._pending_ci is None:
            self._pending_ci = {
                "text": text,
                "arm_sequence": list(arm_sequence),
                "hash": hash_id,
            }
        elif applied_ci:
            self._pending_ci = None

        if "p =" in lowered or "p=" in lowered:
            self._parse_p_values(hash_id, text, arm_sequence)

    def _parse_severe_complications(
        self,
        hash_id: str,
        text: str,
        lowered: str,
        arm_sequence: List[str],
    ) -> None:
        simple_matches = SIMPLE_COUNT_PATTERN.findall(text)
        if not simple_matches or not arm_sequence:
            return
        if "led to" not in lowered and "respectively" not in lowered and "severe" not in lowered:
            return
        for index, (num_value, pct_value) in enumerate(simple_matches[: len(arm_sequence)]):
            arm_name = arm_sequence[index]
            arm = self._ensure_arm(arm_name)
            metric = self._ensure_complication_metric(arm, "pneumothorax_severe")
            percent = _safe_float(pct_value)
            numerator = _safe_int(num_value)
            self._update_metric(metric, percent=percent, numerator=numerator, evidence_hash=hash_id)
            if metric.n_over_N and metric.n_over_N.denominator is None:
                _add_reason(metric, "derived_counts_from_percent")

    def _apply_confidence_interval(
        self,
        hash_id: str,
        text: str,
        arm_sequence: List[str],
    ) -> bool:
        lowered = text.lower()
        if "diagnostic accuracy" not in lowered and "specific diagnosis" not in lowered:
            return False
        matched = False
        for match in CI_PATTERN.finditer(text):
            lower_value = _safe_float(match.group("lower"))
            upper_value = _safe_float(match.group("upper"))
            if lower_value is None or upper_value is None:
                continue
            ci_tuple = (lower_value, upper_value)
            self.doc_accuracy = self.doc_accuracy or ResearchOutcomeMetric()
            current = self.doc_accuracy.ci_95
            if (
                current is None
                or (lower_value is not None and current[0] is not None and lower_value < 0 <= current[0])
                or (current[0] is None and lower_value is not None)
            ):
                self.doc_accuracy.ci_95 = ci_tuple
                self._update_metric(self.doc_accuracy, evidence_hash=hash_id)
            if arm_sequence:
                arm = self._ensure_arm(arm_sequence[0])
                metric = self._ensure_arm_metric(arm, "diagnostic_accuracy")
                current_arm = metric.ci_95
                if (
                    current_arm is None
                    or (lower_value is not None and current_arm[0] is not None and lower_value < 0 <= current_arm[0])
                    or (current_arm[0] is None and lower_value is not None)
                ):
                    metric.ci_95 = ci_tuple
                    self._update_metric(metric, evidence_hash=hash_id)
            matched = True
        return matched

    def _parse_p_values(
        self,
        hash_id: str,
        text: str,
        arm_sequence: List[str],
    ) -> None:
        for match in P_VALUE_PATTERN.finditer(text):
            context = text[match.start():match.end() + 40].lower()
            if "noninferiority" not in context:
                continue
            p_value = _safe_float(match.group("pval"))
            if p_value is None:
                continue
            self.doc_accuracy = self.doc_accuracy or ResearchOutcomeMetric()
            if self.doc_accuracy.p_value is None:
                self.doc_accuracy.p_value = p_value
                self._update_metric(self.doc_accuracy, evidence_hash=hash_id)
            if arm_sequence:
                arm = self._ensure_arm(arm_sequence[0])
                metric = self._ensure_arm_metric(arm, "diagnostic_accuracy")
                if metric.p_value is None:
                    metric.p_value = p_value
                    self._update_metric(metric, evidence_hash=hash_id)

    def _ensure_arm(self, arm_name: str) -> ResearchOutcomeArm:
        normalized = arm_name.strip().lower()
        arm = self.arms.get(normalized)
        if arm is None:
            arm = ResearchOutcomeArm(name=normalized)
            self.arms[normalized] = arm
            self.arm_order.append(normalized)
        return arm

    def _ensure_arm_metric(self, arm: ResearchOutcomeArm, attr: str) -> ResearchOutcomeMetric:
        metric = getattr(arm, attr)
        if metric is None:
            metric = ResearchOutcomeMetric()
            setattr(arm, attr, metric)
        return metric

    def _ensure_complication_metric(self, arm: ResearchOutcomeArm, key: str) -> ResearchOutcomeMetric:
        metric = arm.complications.get(key)
        if metric is None:
            metric = ResearchOutcomeMetric()
            arm.complications[key] = metric
        return metric

    def _append_ci_evidence(self, arm_sequence: List[str], hash_id: str) -> None:
        if self.doc_accuracy and hash_id not in self.doc_accuracy.evidence_ids:
            self.doc_accuracy.evidence_ids.append(hash_id)
        if arm_sequence:
            arm = self._ensure_arm(arm_sequence[0])
            metric = self._ensure_arm_metric(arm, "diagnostic_accuracy")
            if hash_id not in metric.evidence_ids:
                metric.evidence_ids.append(hash_id)

    def _update_metric(
        self,
        metric: ResearchOutcomeMetric,
        *,
        percent: Optional[float] = None,
        numerator: Optional[int] = None,
        denominator: Optional[int] = None,
        evidence_hash: Optional[str] = None,
    ) -> None:
        if percent is not None:
            metric.percent = percent
        if numerator is not None or denominator is not None:
            if metric.n_over_N is None:
                metric.n_over_N = CountFraction()
            if numerator is not None:
                metric.n_over_N.numerator = numerator
            if denominator is not None:
                metric.n_over_N.denominator = denominator
            if metric.n_over_N.denominator is None and metric.n_over_N.numerator is not None:
                _add_reason(metric, "no_n_over_N")
            else:
                _remove_reason(metric, "no_n_over_N")
        if evidence_hash and evidence_hash not in metric.evidence_ids:
            metric.evidence_ids.append(evidence_hash)

    def _finalize_arms(self) -> List[ResearchOutcomeArm]:
        finalized: List[ResearchOutcomeArm] = []
        for arm_name in self.arm_order:
            arm = self.arms.get(arm_name)
            if arm is None:
                continue
            if arm.diagnostic_accuracy and not _metric_has_content(arm.diagnostic_accuracy):
                arm.diagnostic_accuracy = None
            if arm.diagnostic_yield and not _metric_has_content(arm.diagnostic_yield):
                arm.diagnostic_yield = None
            complications = {
                key: metric
                for key, metric in arm.complications.items()
                if _metric_has_content(metric)
            }
            arm.complications = complications
            arm.evidence_ids = sorted({
                evidence
                for metric in _iter_arm_metrics(arm)
                for evidence in getattr(metric, "evidence_ids", []) or []
            })
            finalized.append(arm)
        return finalized


def _paragraph_relevant(lowered: str) -> bool:
    if "diagnostic accuracy" in lowered or "diagnostic yield" in lowered:
        return True
    if "biopsy was diagnostic" in lowered or "biopsy resulted in" in lowered:
        return True
    if "pneumothorax" in lowered:
        return True
    if "noninferiority" in lowered:
        return True
    return False


def _is_diagnostic_yield_paragraph(lowered: str) -> bool:
    if "diagnostic yield" in lowered:
        return True
    if "biopsy was diagnostic" in lowered:
        return True
    if "diagnostic" in lowered and "yield" in lowered:
        return True
    return False


def _infer_design(sections: Dict[str, str]) -> Optional[str]:
    summary = " ".join((sections.get("abstract") or "", sections.get("methods") or "")).lower()
    if "noninferiority" in summary and "randomized" in summary:
        return "randomized_noninferiority"
    if "randomized" in summary:
        return "randomized_trial"
    return None


def _infer_primary_outcome(sections: Dict[str, str]) -> Optional[str]:
    texts = " ".join((value or "").lower() for value in sections.values())
    if "primary outcome was diagnostic accuracy" in texts:
        return "diagnostic_accuracy"
    if "primary outcome was the diagnostic accuracy" in texts:
        return "diagnostic_accuracy"
    if "primary outcome was the percentage of patients with biopsies that showed a specific diagnosis" in texts:
        return "diagnostic_accuracy"
    return None


def _normalize_arm_name(raw: str) -> Optional[str]:
    cleaned = re.sub(r"\s+", " ", raw.strip().lower())
    cleaned = cleaned.replace("–", "-")
    cleaned = cleaned.strip(" ,.;:")
    if cleaned in ARM_ALIASES:
        return ARM_ALIASES[cleaned]
    cleaned = cleaned.replace(" group", "").replace(" arm", "").strip()
    if "navigational bronchoscopy" in cleaned:
        return "navigational bronchoscopy"
    if "transthoracic needle" in cleaned:
        return "transthoracic needle biopsy"
    return ARM_ALIASES.get(cleaned, cleaned or None)


def _safe_float(value: str | None) -> Optional[float]:
    if value is None:
        return None
    normalized = value.replace("−", "-").replace("–", "-").replace(" ", "").strip()
    try:
        return float(normalized)
    except (TypeError, ValueError):
        return None


def _safe_int(value: str | None) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _metric_has_content(metric: Optional[ResearchOutcomeMetric]) -> bool:
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


def _iter_arm_metrics(arm: ResearchOutcomeArm) -> Iterable[ResearchOutcomeMetric]:
    if arm.diagnostic_accuracy:
        yield arm.diagnostic_accuracy
    if arm.diagnostic_yield:
        yield arm.diagnostic_yield
    for metric in arm.complications.values():
        if metric:
            yield metric


def _collect_bundle_evidence(bundle: ResearchOutcomes) -> Iterable[str]:
    evidence: List[str] = []
    if bundle.diagnostic_accuracy:
        evidence.extend(bundle.diagnostic_accuracy.evidence_ids)
    if bundle.diagnostic_yield:
        evidence.extend(bundle.diagnostic_yield.evidence_ids)
    for metric in bundle.complications.values():
        evidence.extend(metric.evidence_ids)
    for arm in bundle.arms:
        evidence.extend(arm.evidence_ids)
    return {hash_id for hash_id in evidence if hash_id}


def _apply_context_reasons(metric: ResearchOutcomeMetric, context: str) -> None:
    lowered = context.lower()
    if "follow-up" in lowered or "follow up" in lowered:
        _add_reason(metric, "follow_up_used_in_numerator")
    if any(token in lowered for token in ("nonspecific", "non-specific", "suspicious", "atypia")):
        _add_reason(metric, "nonspecific_counts_included")


def _add_reason(metric: ResearchOutcomeMetric, reason: str) -> None:
    if reason not in ALLOWED_REASON_KEYS:
        return
    if reason not in metric.reasons:
        metric.reasons.append(reason)


def _remove_reason(metric: ResearchOutcomeMetric, reason: str) -> None:
    if reason in metric.reasons:
        metric.reasons.remove(reason)


def _sanitize_bundle_reasons(bundle: ResearchOutcomes) -> None:
    aggregate: Set[str] = set()

    def _sanitize_metric(metric: Optional[ResearchOutcomeMetric]) -> None:
        if metric is None:
            return
        unique: List[str] = []
        for reason in metric.reasons:
            if reason in ALLOWED_REASON_KEYS and reason not in unique:
                unique.append(reason)
                aggregate.add(reason)
        metric.reasons = unique

    _sanitize_metric(bundle.diagnostic_accuracy)
    _sanitize_metric(bundle.diagnostic_yield)
    for metric in (bundle.complications or {}).values():
        _sanitize_metric(metric)
    for arm in bundle.arms:
        _sanitize_metric(arm.diagnostic_accuracy)
        _sanitize_metric(arm.diagnostic_yield)
        for metric in (arm.complications or {}).values():
            _sanitize_metric(metric)

    bundle.reasons = sorted(aggregate)


def _needs_diagnostic_ci(metric: Optional[ResearchOutcomeMetric]) -> bool:
    if metric is None or metric.ci_95 is None:
        return True
    lower, _upper = metric.ci_95
    if lower is None:
        return True
    return lower >= 0


def _fallback_diagnostic_ci(paragraph_store: Dict[str, Dict[str, object]]) -> tuple[Optional[Tuple[float, float]], Optional[str]]:
    combined = " ".join(str(entry.get("text") or "") for entry in paragraph_store.values())
    pattern = re.compile(
        r"diagnostic accuracy.*?confidence interval[^−–\-\d]*([−–\-]\s*\d+(?:\.\s*\d+)?)\s*to\s*(\d+(?:\.\s*\d+)?)",
        flags=re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(combined)
    if match:
        lower = _safe_float(match.group(1))
        upper = _safe_float(match.group(2))
        if lower is not None and upper is not None:
            hash_id = _find_paragraph_hash(paragraph_store, ["confidence interval", "noninferiority"])
            return (lower, upper), hash_id
    return None, None


def _find_paragraph_hash(paragraph_store: Dict[str, Dict[str, object]], tokens: List[str]) -> Optional[str]:
    for hash_id, entry in paragraph_store.items():
        text = str(entry.get("text") or "").lower()
        if all(token in text for token in tokens):
            return hash_id
    return None


__all__ = ["extract_research_outcomes"]
