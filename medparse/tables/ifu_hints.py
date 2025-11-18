"""Heuristics that recover sterilization tables that layout extraction misses."""

from __future__ import annotations

import re
from typing import Iterable, List, Sequence

from medparse.ingest.models import PageData
TIME_PATTERN = re.compile(
    r"(\d[\d\s\-\u2013\u2014/().°]*?(?:seconds?|sec|minutes?|mins?|hours?|hrs?))\b",
    re.IGNORECASE,
)


def detect_sterilization_table_hints(
    pages: Sequence[PageData],
    existing_tables: Iterable[dict] | None = None,
) -> List[dict]:
    """Return synthetic sterilization tables built from inline instructions."""

    if _has_sterilization_table(existing_tables):
        return []

    tables: List[dict] = []
    for page in pages:
        lines = list(page.lines or [])
        if not lines:
            continue
        for idx, line in enumerate(lines):
            lowered = line.lower()
            if "steriliz" not in lowered or "temperature" not in lowered or "exposure" not in lowered:
                continue
            rows = _collect_rows(lines[idx + 1 : idx + 8])
            if not rows:
                continue
            heading_path = _heading_path(page, idx)
            heading_path.extend(_neighbor_sections(lines, idx))
            tables.append(
                {
                    "title": "Sterilization parameters",
                    "headers": ["Sterilizer", "Temperature", "Exposure time"],
                    "rows": rows,
                    "page": page.number,
                    "caption": line.strip(),
                    "footnotes": [],
                    "heading_path": heading_path,
                    "rows_truncated": True,
                }
            )
            break
    return tables


def _has_sterilization_table(existing_tables: Iterable[dict] | None) -> bool:
    if not existing_tables:
        return False
    for table in existing_tables:
        if not isinstance(table, dict):
            continue
        text = " ".join(
            [
                str(table.get("title") or ""),
                str(table.get("caption") or ""),
            ]
        ).lower()
        if "steriliz" in text and "temperature" in text:
            return True
    return False


def _collect_rows(lines: Sequence[str]) -> List[List[str]]:
    rows: List[List[str]] = []
    for raw_line in lines:
        stripped = (raw_line or "").strip()
        if not stripped:
            if rows:
                break
            continue
        parsed = _parse_row(stripped)
        if not parsed:
            if rows:
                break
            continue
        rows.append(parsed)
    return rows


def _parse_row(line: str) -> List[str] | None:
    if not line:
        return None
    first_digit = next((idx for idx, char in enumerate(line) if char.isdigit()), -1)
    if first_digit <= 0:
        return None
    sterilizer = line[:first_digit].strip(" -–—|,:.")
    payload = line[first_digit:].strip()
    if not sterilizer or not payload:
        return None
    time_match = TIME_PATTERN.search(payload)
    if not time_match:
        return None
    time_value = time_match.group(1).strip()
    temperature = payload[: time_match.start()].strip(" -–—|,:.")
    if not temperature:
        return None
    sterilizer = re.sub(r"\s{2,}", " ", sterilizer)
    temperature = temperature.replace("", "°")
    time_value = time_value.replace("", "°")
    return [sterilizer, temperature, time_value]


def _heading_path(page: PageData, line_idx: int) -> List[str]:
    headings = sorted(page.headings or [], key=lambda h: h.line_index)
    path: List[str] = []
    for heading in headings:
        if heading.line_index <= line_idx and heading.title:
            path.append(heading.title.strip())
    return path[-3:]


def _neighbor_sections(lines: Sequence[str], anchor_idx: int) -> List[str]:
    keywords: List[str] = []
    start = max(0, anchor_idx - 5)
    end = min(len(lines), anchor_idx + 6)
    for idx in range(start, end):
        text = (lines[idx] or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if "reprocess" in lowered and "Reprocessing" not in keywords:
            keywords.append("Reprocessing")
        if "steriliz" in lowered and "Sterilization" not in keywords:
            keywords.append("Sterilization")
    return keywords


__all__ = ["detect_sterilization_table_hints"]
