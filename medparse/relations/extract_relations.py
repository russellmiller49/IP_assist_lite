"""Heuristic relation extraction built on UMLS co-occurrence windows."""

from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
from typing import Dict, Iterable, List, Optional, Tuple, Union

from pydantic import BaseModel, Field

from medparse.relations.patterns import (
    detect_conditional,
    detect_negation,
    detect_pattern,
    detect_temporal,
)


class RelationRecord(BaseModel):
    """Normalized triple with optional attributes and evidence text."""

    subject: str
    predicate: str
    object: str
    attributes: Dict[str, object] = Field(default_factory=dict)
    evidence: Optional[str] = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    negated: bool = False
    conditional: bool = False
    temporal: Optional[str] = None
    evidence_refs: List[str] = Field(default_factory=list)


WINDOW_TOKEN_DEFAULT = 200
WINDOW_TOKEN_MIN = 150
WINDOW_TOKEN_MAX = 250
STRIDE_MIN = 75
STRIDE_MAX = 125
MAX_EDGES_PER_PAGE = 300
MAX_EDGES_PER_PAIR = 5
HUB_COUNT_THRESHOLD = 60
HUB_PAGE_RATIO = 0.6
CHAR_PER_TOKEN = 5


CONDITION_SEMTYPES = {"T047", "T046", "T191", "T184", "T033"}
INTERVENTION_SEMTYPES = {"T061", "T062", "T074", "T200", "T195", "T121"}
FACTOR_SEMTYPES = {"T055", "T166", "T130", "T103", "T082"}


def _entity_role(entity: dict) -> str:
    semtypes = {str(code).upper() for code in entity.get("semtypes") or []}
    if semtypes & CONDITION_SEMTYPES:
        return "condition"
    if semtypes & INTERVENTION_SEMTYPES:
        return "intervention"
    if semtypes & FACTOR_SEMTYPES:
        return "factor"
    return "unknown"


def _first_offset(entity: dict) -> Tuple[Optional[int], Optional[int]]:
    offsets = entity.get("offsets") or []
    if not offsets:
        return None, None
    start, end = offsets[0]
    return (
        int(start) if isinstance(start, int) else None,
        int(end) if isinstance(end, int) else None,
    )


def _build_evidence_id(page: int, start: Optional[int], end: Optional[int]) -> str:
    if start is None or end is None:
        return f"page-{page}"
    return f"page-{page}-span-{start}-{end}"


def _context_snippet(
    page_text: str,
    page_label: int,
    left_bounds: Tuple[Optional[int], Optional[int]],
    right_bounds: Tuple[Optional[int], Optional[int]],
) -> tuple[str, List[str]]:
    left_start, left_end = left_bounds
    right_start, right_end = right_bounds
    if left_start is None or right_start is None:
        return "", []
    span_start = max(0, min(left_start, right_start) - 5)
    span_end = min(
        len(page_text),
        max(left_end or left_start, right_end or right_start) + 5,
    )
    snippet = page_text[span_start:span_end].strip()
    if not snippet:
        return "", []
    evidence_id = _build_evidence_id(page_label, span_start, span_end)
    return snippet, [evidence_id]


def _orient_entities(predicate: str, left: dict, right: dict) -> tuple[dict, dict]:
    left_role = _entity_role(left)
    right_role = _entity_role(right)
    subject = left
    obj = right
    if predicate in {"treated_with", "diagnosed_by"}:
        if left_role != "condition" and right_role == "condition":
            subject, obj = right, left
    elif predicate in {"risk_factor_for", "prognostic_factor_for"}:
        if left_role == "condition" and right_role != "condition":
            subject, obj = right, left
    return subject, obj


def build_cooccurrence(
    entities: Iterable[dict],
    *,
    window: Union[str, int] = "page",
    page_texts: Optional[Dict[int, str]] = None,
) -> List[RelationRecord]:
    """Build capped co-occurrence edges between UMLS entities."""

    if isinstance(window, str) and window == "evidence_span":
        return _legacy_cooccurrence(entities, window)

    window_tokens = _resolve_window_tokens(window)
    stride_tokens = _resolve_stride_tokens(window_tokens)
    window_chars = window_tokens * CHAR_PER_TOKEN

    page_groups, entity_counts, entity_pages = _group_entities_by_page(entities)
    page_map = page_texts or {}
    total_pages = len([page for page in page_groups if page is not None])
    hub_entities = _identify_hub_entities(entity_counts, entity_pages, total_pages)

    relations: List[RelationRecord] = []
    pair_occurrences: Counter[tuple[str, str]] = Counter()

    for page, items in page_groups.items():
        if len(items) < 2:
            continue

        page_label = page if isinstance(page, int) else -1
        page_text = page_map.get(page_label)
        candidates: List[tuple[float, int, Optional[int], tuple[str, str], dict, dict]] = []
        for idx, left in enumerate(items):
            left_cui = left.get("cui")
            if not left_cui or left_cui in hub_entities:
                continue
            for right in items[idx + 1 :]:
                right_cui = right.get("cui")
                if not right_cui or right_cui in hub_entities or right_cui == left_cui:
                    continue

                distance_chars = _min_char_distance(
                    left.get("offsets") or [],
                    right.get("offsets") or [],
                )
                if distance_chars is not None and distance_chars > window_chars:
                    continue

                approx_tokens = (
                    max(1, distance_chars // CHAR_PER_TOKEN)
                    if distance_chars is not None
                    else window_tokens // 2
                )
                score = window_chars - (
                    distance_chars if distance_chars is not None else window_chars // 2
                )
                pair_key = tuple(sorted((left_cui, right_cui)))
                candidates.append(
                    (score, approx_tokens, distance_chars, pair_key, left, right)
                )

        if not candidates:
            continue

        candidates.sort(key=lambda entry: entry[0], reverse=True)
        emitted = 0

        for score, approx_tokens, distance_chars, pair_key, left, right in candidates:
            if emitted >= MAX_EDGES_PER_PAGE:
                break
            if pair_occurrences[pair_key] >= MAX_EDGES_PER_PAIR:
                continue

            attributes: Dict[str, object] = {
                "page": page_label,
                "window_tokens": window_tokens,
                "stride_tokens": stride_tokens,
                "approx_tokens": approx_tokens,
            }
            if distance_chars is not None:
                attributes["distance_chars"] = distance_chars

            evidence = f"page {page_label} window<={window_tokens} tokens"
            evidence_refs: List[str] = [f"page-{page_label}"]
            predicate = "associated_with"
            confidence = 0.55
            negated = False
            conditional_flag = False
            temporal = None

            left_bounds = _first_offset(left)
            right_bounds = _first_offset(right)
            if page_text and left_bounds[0] is not None and right_bounds[0] is not None:
                snippet, refs = _context_snippet(page_text, page_label, left_bounds, right_bounds)
                if snippet:
                    evidence = snippet
                    evidence_refs = refs or evidence_refs
                    pattern = detect_pattern(snippet)
                    if pattern:
                        predicate = pattern.predicate
                        confidence = pattern.confidence
                    negated = detect_negation(snippet)
                    conditional_flag = detect_conditional(snippet)
                    temporal = detect_temporal(snippet)

            subject_entity, object_entity = _orient_entities(predicate, left, right)
            subject = subject_entity.get("cui")
            obj = object_entity.get("cui")
            if not subject or not obj:
                continue

            relations.append(
                RelationRecord(
                    subject=subject,
                    predicate=predicate,
                    object=obj,
                    attributes=attributes,
                    evidence=evidence,
                    confidence=round(confidence, 3),
                    negated=negated,
                    conditional=conditional_flag,
                    temporal=temporal,
                    evidence_refs=evidence_refs,
                )
            )

            pair_occurrences[pair_key] += 1
            emitted += 1

    return relations


def _resolve_window_tokens(window: Union[str, int]) -> int:
    if isinstance(window, int) and window > 0:
        return max(WINDOW_TOKEN_MIN, min(window, WINDOW_TOKEN_MAX))
    return WINDOW_TOKEN_DEFAULT


def _resolve_stride_tokens(window_tokens: int) -> int:
    stride = max(1, window_tokens // 2)
    return max(STRIDE_MIN, min(stride, STRIDE_MAX))


def _group_entities_by_page(
    entities: Iterable[dict],
) -> tuple[Dict[Optional[int], List[dict]], Counter[str], Dict[str, set[int]]]:
    page_groups: Dict[Optional[int], List[dict]] = defaultdict(list)
    entity_counts: Counter[str] = Counter()
    entity_pages: Dict[str, set[int]] = defaultdict(set)

    for entity in entities:
        if not isinstance(entity, dict):
            continue
        cui = entity.get("cui")
        if not cui:
            continue
        page = entity.get("page")
        page_groups[page].append(entity)
        entity_counts[cui] += 1
        if isinstance(page, int):
            entity_pages[cui].add(page)

    return page_groups, entity_counts, entity_pages


def _min_char_distance(
    left_offsets: Iterable[tuple[int, int]],
    right_offsets: Iterable[tuple[int, int]],
) -> Optional[int]:
    distances: List[int] = []
    for l_start, _ in left_offsets:
        for r_start, _ in right_offsets:
            distances.append(abs(l_start - r_start))
    if not distances:
        return None
    return min(distances)


def _identify_hub_entities(
    entity_counts: Counter[str],
    entity_pages: Dict[str, set[int]],
    total_pages: int,
) -> set[str]:
    hubs: set[str] = set()
    for cui, count in entity_counts.items():
        if count >= HUB_COUNT_THRESHOLD:
            hubs.add(cui)
            continue
        pages = entity_pages.get(cui, set())
        meaningful_pages = len(pages)
        if total_pages and meaningful_pages / max(total_pages, 1) >= HUB_PAGE_RATIO:
            hubs.add(cui)
    return hubs


def _legacy_cooccurrence(
    entities: Iterable[dict],
    window: str,
) -> List[RelationRecord]:
    grouped: Dict[Optional[int], List[dict]] = defaultdict(list)
    for entity in entities:
        page = entity.get("page") if isinstance(entity, dict) else None
        grouped[page].append(entity)

    relations: List[RelationRecord] = []
    dedupe: set[tuple[str, str, Optional[int]]] = set()
    window_label = window

    for page, items in grouped.items():
        if len(items) < 2:
            continue
        for left, right in combinations(items, 2):
            cui_left = left.get("cui") if isinstance(left, dict) else None
            cui_right = right.get("cui") if isinstance(right, dict) else None
            if not cui_left or not cui_right or cui_left == cui_right:
                continue

            key = tuple(sorted((cui_left, cui_right))) + (page,)
            if key in dedupe:
                continue
            dedupe.add(key)

            if window == "evidence_span":
                evidence = " | ".join(
                    filter(None, (left.get("text"), right.get("text")))
                ) or None
            else:
                evidence = f"page {page} co-mention"

            attributes: Dict[str, object] = {"page": page, "window": window_label}

            relations.append(
                RelationRecord(
                    subject=cui_left,
                    predicate="associated_with",
                    object=cui_right,
                    attributes=attributes,
                    evidence=evidence,
                    confidence=0.5,
                )
            )

    return relations


__all__ = ["RelationRecord", "build_cooccurrence"]
