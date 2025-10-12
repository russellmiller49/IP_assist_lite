"""ATS 2024 strict diagnostic yield normalization."""

from typing import Mapping

from medparse.types.base import EvidenceSpan
from medparse.types.yield_defs import DiagnosticYieldStrict

STRICT_DEFINITION_SNIPPET = (
    "ATS 2024 strict yield: numerator = specific benign or malignant diagnosis "
    "established during the procedural encounter; nonspecific findings are nondiagnostic; "
    "denominator = all attempted/performed."
)


def compute_strict_yield(numerator: int, denominator: int) -> DiagnosticYieldStrict:
    """Compute ATS strict diagnostic yield with validation."""
    if denominator <= 0:
        raise ValueError("Denominator must be greater than zero for ATS strict yield.")
    if numerator < 0 or numerator > denominator:
        raise ValueError("Numerator must be between 0 and denominator for ATS strict yield.")

    yield_pct = round((numerator / denominator) * 100, 1)
    evidence = EvidenceSpan(text=STRICT_DEFINITION_SNIPPET, page=1)
    return DiagnosticYieldStrict(
        numerator=numerator,
        denominator=denominator,
        yield_pct=yield_pct,
        evidence=evidence,
    )


NON_DIAGNOSTIC_KEYWORDS = (
    "nonspecific",
    "non-specific",
    "atypia",
    "suspicious",
    "indeterminate",
    "insufficient",
    "inadequate",
    "no diagnosis",
    "fibrosis",
)


def strict_numerator_from_categories(categories: Mapping[str, int]) -> int:
    """Return the numerator for ATS strict yield, excluding nondiagnostic labels."""
    numerator = 0
    for label, count in categories.items():
        if count <= 0:
            continue
        lowered = label.lower()
        if any(keyword in lowered for keyword in NON_DIAGNOSTIC_KEYWORDS):
            continue
        numerator += count
    return numerator
