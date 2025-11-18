"""Text normalization helpers applied at ingest time."""

from __future__ import annotations

import re
from collections import Counter
from typing import Dict, Mapping, Sequence

FRACTION_MAP = {
    "½": "1/2",
    "⅓": "1/3",
    "⅔": "2/3",
    "¼": "1/4",
    "¾": "3/4",
}
FRACTION_PATTERN = re.compile("|".join(map(re.escape, FRACTION_MAP.keys())))

UNIT_PATTERN = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)(?P<unit>(?:mg|mL|ml|cm|mm|kg|g|L|µm|μm|um|°C|°F|kPa|Pa|psi|Gy|J|mEq|cc|mbar|mmHg))\b"
)
RUN_ON_RE = re.compile(r"(?<=[a-z])(?=[A-Z][a-z])")


def normalize_page_text(text: str) -> tuple[str, Dict[str, int]]:
    if not text:
        return "", {}

    report: Counter[str] = Counter()
    normalized = text

    def _fraction_repl(match: re.Match[str]) -> str:
        report["fractions"] += 1
        return FRACTION_MAP.get(match.group(0), match.group(0))

    normalized = FRACTION_PATTERN.sub(_fraction_repl, normalized)
    if "\u2044" in normalized:
        count = normalized.count("\u2044")
        normalized = normalized.replace("\u2044", "/")
        report["fractions"] += count

    def _unit_repl(match: re.Match[str]) -> str:
        value = match.group("value")
        unit = match.group("unit")
        if match.group(0) == f"{value} {unit}":
            return match.group(0)
        report["unit_spacing"] += 1
        return f"{value} {unit}"

    normalized = UNIT_PATTERN.sub(_unit_repl, normalized)

    def _runon_repl(match: re.Match[str]) -> str:
        report["runons"] += 1
        return " "

    normalized = RUN_ON_RE.sub(_runon_repl, normalized)

    return normalized, dict(report)


def summarize_normalization_reports(pages: Sequence[object]) -> Dict[str, object]:
    summary: Counter[str] = Counter()
    pages_modified = 0
    for page in pages:
        report = getattr(page, "normalization_report", None)
        if not isinstance(report, Mapping) or not report:
            continue
        pages_modified += 1
        for key, value in report.items():
            try:
                summary[key] += int(value)
            except (TypeError, ValueError):
                continue
    if not summary:
        return {}
    return {"pages_modified": pages_modified, "report": dict(summary)}


__all__ = ["normalize_page_text", "summarize_normalization_reports"]
