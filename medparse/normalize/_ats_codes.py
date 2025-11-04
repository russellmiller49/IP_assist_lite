"""Shared constants and normalization helpers for ATS diagnostic yield reasons."""

from __future__ import annotations

from typing import Optional

ATS_REASON_NO_N_OVER_N = "no_n_over_N"
ATS_REASON_FOLLOW_UP = "follow_up_used_in_numerator"
ATS_REASON_NONSPECIFIC = "nonspecific_counts_included"
ATS_REASON_DERIVED = "derived_counts_from_percent"

ATS_CANONICAL_REASONS = {
    ATS_REASON_NO_N_OVER_N,
    ATS_REASON_FOLLOW_UP,
    ATS_REASON_NONSPECIFIC,
    ATS_REASON_DERIVED,
}

_LEGACY_KEYWORDS = (
    (ATS_REASON_NO_N_OVER_N, ("no_numerator", "missing_n_over", "no n/", "no numerator", "missing numerator", "no denominator", "missing denominator")),
    (ATS_REASON_FOLLOW_UP, ("follow_up", "follow-up", "12-month", "twelve month")),
    (ATS_REASON_DERIVED, ("derived_counts_from_percent", "derived", "percent derived", "percentage derived")),
    (ATS_REASON_NONSPECIFIC, ("nonspecific", "composite", "technical success", "per-lesion", "intermediate", "liberal")),
)


def canonicalize_reason(reason: Optional[str]) -> Optional[str]:
    """Return canonical ATS exclusion reason from arbitrary label."""

    if not reason:
        return None
    if reason in ATS_CANONICAL_REASONS:
        return reason

    lowered = str(reason).strip().lower()
    if not lowered:
        return None

    for canonical, keywords in _LEGACY_KEYWORDS:
        for keyword in keywords:
            if keyword in lowered:
                return canonical
    return None


__all__ = [
    "ATS_REASON_NO_N_OVER_N",
    "ATS_REASON_FOLLOW_UP",
    "ATS_REASON_NONSPECIFIC",
    "ATS_REASON_DERIVED",
    "ATS_CANONICAL_REASONS",
    "canonicalize_reason",
]
