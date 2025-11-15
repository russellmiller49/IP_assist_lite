"""Second-pass patcher that normalizes ATS definitions into key-value pairs."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from medparse.schema.article import ArticleDocument, DefinitionEntry, EnhancedTable
from medparse.second_pass.types import SecondPassContext, SecondPassPatchResult

PATCH_NAME = "article_definitions_keyvalue_backfill"

_ALIAS_MAP: Dict[str, str] = {
    "diagnostic yield": "diagnostic_yield",
    "strict diagnostic yield": "diagnostic_yield",
    "strict diagnostic": "diagnostic_yield",
    "sensitivity": "sensitivity",
    "specificity": "specificity",
    "positive predictive value": "ppv",
    "positive predictive": "ppv",
    "ppv": "ppv",
    "negative predictive value": "npv",
    "negative predictive": "npv",
    "npv": "npv",
    "diagnostic accuracy": "diagnostic_accuracy",
}

_LIST_PATTERN = re.compile(
    r"^(?P<term>[A-Z][A-Za-z\s%]+?)\s*[:\-–]\s*(?P<body>.+)$",
    re.DOTALL,
)

_NUMBERED_SECTION_RE = re.compile(r"(?P<num>\d+)\.\s*(?P<section>.*?)(?=(?:\d+\.\s)|$)", re.DOTALL)
_NUMBERED_BREAK_RE = re.compile(r"\s\d+\.\s")
_ALIAS_PRIORITY = sorted(_ALIAS_MAP.items(), key=lambda item: len(item[0]), reverse=True)


def apply_article_definitions_keyvalue_backfill(
    document: ArticleDocument,
    ctx: SecondPassContext,
) -> SecondPassPatchResult:
    if not isinstance(document, ArticleDocument):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="doc_not_article")

    subtype = (document.doc_subtype or "").lower()
    if subtype not in {"statement", "guideline"}:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="subtype")

    paragraph_store = ctx.paragraph_store or {}
    table_definitions = _extract_table_definitions(document.tables or [], paragraph_store)
    source = "definitions_table" if table_definitions else None
    if not table_definitions:
        table_definitions = _extract_list_definitions(paragraph_store)
        if table_definitions:
            source = "definitions_list"

    if not table_definitions:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_definitions_found")

    existing = dict(document.definitions or {})
    applied = 0
    for key, entry in table_definitions.items():
        if key in existing and existing[key].text == entry.text:
            # Preserve richer evidence refs if new entry lacks them.
            if entry.evidence_refs and not existing[key].evidence_refs:
                existing[key] = entry
            continue
        existing[key] = entry
        applied += 1

    if applied == 0:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="already_normalized")

    document.definitions = existing
    reasons = [source] if source else ["definitions_backfill"]
    modifications = {"definitions_backfilled": applied}
    return SecondPassPatchResult(
        name=PATCH_NAME,
        applied=True,
        reasons=reasons,
        modifications=modifications,
    )


def _extract_table_definitions(
    tables: Sequence[EnhancedTable],
    paragraph_store: Dict[str, Dict[str, object]],
) -> Dict[str, DefinitionEntry]:
    if not tables:
        return {}

    for table in tables:
        if not _looks_like_definition_table(table):
            continue
        mapping: Dict[str, DefinitionEntry] = {}
        caption_refs = _match_evidence_refs(table.caption or "", paragraph_store)
        for row in table.rows or []:
            if not row or len(row) < 2:
                continue
            term = (row[0] or "").strip()
            body = " ".join((cell or "").strip() for cell in row[1:] if cell).strip()
            canonical = _canonical_key(term)
            if not canonical or not body:
                continue
            refs = _match_evidence_refs(body, paragraph_store)
            if not refs:
                refs = caption_refs
            mapping[canonical] = DefinitionEntry(text=body, evidence_refs=refs or [])
        if mapping:
            # Only use the first matching table; tables are ordered top-to-bottom.
            return mapping
    return {}


def _extract_list_definitions(paragraph_store: Dict[str, Dict[str, object]]) -> Dict[str, DefinitionEntry]:
    mapping: Dict[str, DefinitionEntry] = {}
    for hash_id, entry in _iter_paragraph_entries(paragraph_store):
        text = (entry.get("text") or "").strip()
        if not text:
            continue
        numbered_segments = _extract_numbered_definitions(text, hash_id)
        for key, value in numbered_segments.items():
            mapping.setdefault(key, value)
        alias_segments = _extract_alias_segments(text, hash_id)
        for key, value in alias_segments.items():
            mapping.setdefault(key, value)
        match = _LIST_PATTERN.match(text)
        if not match:
            continue
        canonical = _canonical_key(match.group("term"))
        if not canonical:
            continue
        if canonical in mapping:
            continue
        body = match.group("body").strip()
        if not body:
            continue
        mapping[canonical] = DefinitionEntry(text=body, evidence_refs=[hash_id])
    return mapping


def _extract_numbered_definitions(text: str, hash_id: str) -> Dict[str, DefinitionEntry]:
    segments: Dict[str, DefinitionEntry] = {}
    for match in _NUMBERED_SECTION_RE.finditer(text):
        section_text = match.group("section").strip()
        if not section_text:
            continue
        title, body = _split_first_sentence(section_text)
        canonical = _resolve_alias_from_text(title) or _resolve_alias_from_text(section_text)
        if not canonical or canonical in segments:
            continue
        normalized_text = f"{match.group('num')}. {section_text}".strip()
        segments[canonical] = DefinitionEntry(text=normalized_text, evidence_refs=[hash_id])
    return segments


def _extract_alias_segments(text: str, hash_id: str) -> Dict[str, DefinitionEntry]:
    lowered = text.lower()
    occurrences: List[Tuple[int, str]] = []
    for alias, canonical in _ALIAS_PRIORITY:
        start = 0
        while True:
            idx = lowered.find(alias, start)
            if idx == -1:
                break
            occurrences.append((idx, canonical))
            start = idx + len(alias)
    if not occurrences:
        return {}
    occurrences.sort(key=lambda item: item[0])
    segments: Dict[str, DefinitionEntry] = {}
    for idx, canonical in occurrences:
        if canonical in segments:
            continue
        end_candidates: List[int] = []
        for other_idx, other_canonical in occurrences:
            if other_idx > idx:
                end_candidates.append(other_idx)
                break
        numbered_match = _NUMBERED_BREAK_RE.search(text, idx + 1)
        if numbered_match:
            end_candidates.append(numbered_match.start())
        end = min(end_candidates) if end_candidates else len(text)
        snippet = text[idx:end].strip(" ;,\n")
        if len(snippet) < 20:
            continue
        segments[canonical] = DefinitionEntry(text=snippet, evidence_refs=[hash_id])
    return segments


def _split_first_sentence(section: str) -> Tuple[str, str]:
    cleaned = section.strip()
    if not cleaned:
        return "", ""
    if "." in cleaned:
        head, _, tail = cleaned.partition(".")
        return head.strip(), tail.strip()
    return cleaned, ""


def _resolve_alias_from_text(text: str) -> Optional[str]:
    normalized = text.lower()
    for alias, canonical in _ALIAS_PRIORITY:
        if alias in normalized:
            return canonical
    return None


def _iter_paragraph_entries(
    paragraph_store: Dict[str, Dict[str, object]],
) -> Iterable[Tuple[str, Dict[str, object]]]:
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
    for _, hash_id, entry in sorted(sortable, key=lambda item: item[0]):
        yield hash_id, entry


def _canonical_key(term: str) -> Optional[str]:
    if not term:
        return None
    normalized = term.strip().lower()
    for alias, field in _ALIAS_MAP.items():
        if alias in normalized:
            return field
    return None


def _looks_like_definition_table(table: EnhancedTable) -> bool:
    caption_lower = (table.caption or "").lower()
    if "definition" in caption_lower and "diagnostic" in caption_lower:
        return True
    header_line = " ".join((table.headers or [[]])[0]).lower() if table.headers else ""
    if "definition" in header_line and "measure" in header_line:
        return True
    return False


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def _match_evidence_refs(
    text: str,
    paragraph_store: Dict[str, Dict[str, object]],
    limit: int = 2,
) -> List[str]:
    normalized = _normalize_whitespace(text or "").lower()
    if not normalized:
        return []
    snippet = normalized[:180]
    hits: List[str] = []
    for hash_id, entry in paragraph_store.items():
        entry_text = _normalize_whitespace(entry.get("text") or "").lower()
        if snippet and snippet[:40] in entry_text:
            hits.append(hash_id)
            if len(hits) >= limit:
                break
    return hits


__all__ = ["apply_article_definitions_keyvalue_backfill"]
