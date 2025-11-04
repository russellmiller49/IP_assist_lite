"""Helpers to determine whether ATS diagnostic-yield rules should apply."""

from __future__ import annotations

import functools
import re
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

import yaml

from medparse.schema.article import ArticleDocument

TOPICS_PATH = Path(__file__).resolve().parents[2] / "configs" / "_shared" / "article_topics.yaml"


@functools.lru_cache(maxsize=1)
def _load_topics() -> dict:
    if not TOPICS_PATH.exists():
        return {}
    try:
        data = yaml.safe_load(TOPICS_PATH.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            return {}
        return data
    except Exception:
        return {}


def _lower_join(parts: Iterable[str]) -> str:
    return " ".join(part for part in (part.lower() for part in parts if part) if part)


def _contains_any(text: str, terms: Sequence[str]) -> bool:
    return any(term in text for term in terms)


def _tables_contain_terms(article: ArticleDocument, terms: Sequence[str]) -> bool:
    tables = getattr(article, "tables", []) or []
    for table in tables:
        headers = []
        rows = []
        try:
            headers = [" ".join(row) for row in getattr(table, "headers", []) or []]
        except Exception:
            pass
        try:
            rows = [" ".join(row) for row in getattr(table, "rows", []) or []]
        except Exception:
            pass
        table_text = _lower_join(headers + rows)
        if _contains_any(table_text, terms):
            return True
    return False


def is_diagnostic_study(article: ArticleDocument) -> Tuple[bool, List[str]]:
    """Return (applicable, reasons) for ATS diagnostic-yield validation."""

    topics = _load_topics()
    diag_cfg = topics.get("diagnostic", {})
    negative_cfg = topics.get("negative", {})

    primary_terms = [term.lower() for term in diag_cfg.get("primary_terms", []) if isinstance(term, str)]
    procedure_terms = [term.lower() for term in diag_cfg.get("procedure_terms", []) if isinstance(term, str)]
    table_terms = [term.lower() for term in diag_cfg.get("table_terms", []) if isinstance(term, str)]
    negative_terms = [term.lower() for term in negative_cfg.get("terms", []) if isinstance(term, str)]

    reasons: List[str] = []

    subtype = getattr(article, "doc_subtype", None) or ""
    if subtype in {"therapeutic_trial", "practice_management"}:
        return False, [f"doc_subtype:{subtype}"]

    sections = getattr(article, "sections", {}) or {}
    section_text = _lower_join(sections.values())
    title = (article.title or "").lower()
    abstract = sections.get("abstract", "").lower()
    intro = sections.get("introduction", "").lower()

    # Signals for applicability
    positive = False

    def _record(reason: str) -> None:
        if reason not in reasons:
            reasons.append(reason)

    combined_scope_texts = [title, abstract, intro, section_text]

    for segment in combined_scope_texts:
        if not segment:
            continue
        for primary in primary_terms:
            if primary in segment:
                for proc in procedure_terms:
                    pattern = rf"{re.escape(primary)}.*{re.escape(proc)}|{re.escape(proc)}.*{re.escape(primary)}"
                    if re.search(pattern, segment):
                        positive = True
                        _record(f"primary_term:{primary}|procedure:{proc}")
                        break
                if positive:
                    break
        if positive:
            break

    if getattr(article, "yield_definitions_present", False):
        positive = True
        _record("yield_definitions_present")

    if table_terms and _tables_contain_terms(article, table_terms):
        positive = True
        _record("table_contains_diagnostic_terms")

    negative_hits = []
    for term in negative_terms:
        if term and _contains_any(section_text, [term]):
            negative_hits.append(term)

    if negative_hits and not positive:
        for term in negative_hits:
            _record(f"negative_term:{term}")
        return False, reasons or ["topic_out_of_scope"]

    if not positive:
        _record("missing_diagnostic_cues")
        return False, reasons

    _record("diagnostic_cues_detected")
    return True, reasons


__all__ = ["is_diagnostic_study"]
