"""Lightweight rule-based relation extraction for enriched documents."""

from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
from typing import Dict, Iterable, List, Optional, Union

from pydantic import BaseModel, Field


class RelationRecord(BaseModel):
    """Normalized triple with optional attributes and evidence text."""

    subject: str
    predicate: str
    object: str
    attributes: Dict[str, object] = Field(default_factory=dict)
    evidence: Optional[str] = None


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


def relations_from_outcomes(
    procedure_name: str,
    outcomes: Iterable[dict],
) -> List[RelationRecord]:
    """Generate ``has_complication`` relations from outcome records."""

    relations: List[RelationRecord] = []
    for outcome in outcomes:
        name = outcome.get("name")
        if not name:
            continue

        attributes: Dict[str, object] = {}
        for key in ("percent", "value", "n", "denominator", "ci_lower", "ci_upper"):
            if outcome.get(key) is not None:
                attributes[key] = outcome[key]

        evidence = None
        evidence_data = outcome.get("evidence")
        if isinstance(evidence_data, dict):
            evidence = evidence_data.get("text")

        relations.append(
            RelationRecord(
                subject=procedure_name,
                predicate="has_complication",
                object=name,
                attributes=attributes,
                evidence=evidence,
            )
        )
    return relations


def relations_from_recommendations(
    guideline_title: str,
    recommendations: Iterable[dict],
) -> List[RelationRecord]:
    """Generate ``recommends`` relations from guideline recommendations."""

    relations: List[RelationRecord] = []
    for rec in recommendations:
        text = rec.get("text")
        if not text:
            continue

        attributes: Dict[str, object] = {}
        for key in ("grade", "strength", "evidence_level", "statement_type", "votes"):
            value = rec.get(key)
            if value:
                attributes[key] = value

        evidence = None
        evidence_data = rec.get("evidence")
        if isinstance(evidence_data, dict):
            evidence = evidence_data.get("text")

        relations.append(
            RelationRecord(
                subject=guideline_title,
                predicate="recommends",
                object=text,
                attributes=attributes,
                evidence=evidence,
            )
        )
    return relations


def build_relations(
    *,
    title: str,
    outcomes: Iterable[dict] | None = None,
    recommendations: Iterable[dict] | None = None,
) -> List[RelationRecord]:
    """Convenience wrapper combining outcome and recommendation relations."""

    relations: List[RelationRecord] = []
    if outcomes:
        relations.extend(relations_from_outcomes(title, outcomes))
    if recommendations:
        relations.extend(relations_from_recommendations(title, recommendations))
    return relations


def build_cooccurrence(
    entities: Iterable[dict],
    *,
    window: Union[str, int] = "page",
) -> List[RelationRecord]:
    """Build capped co-occurrence edges between UMLS entities."""

    if isinstance(window, str) and window == "evidence_span":
        return _legacy_cooccurrence(entities, window)

    window_tokens = _resolve_window_tokens(window)
    stride_tokens = _resolve_stride_tokens(window_tokens)
    window_chars = window_tokens * CHAR_PER_TOKEN

    page_groups, entity_counts, entity_pages = _group_entities_by_page(entities)
    total_pages = len([page for page in page_groups if page is not None])
    hub_entities = _identify_hub_entities(entity_counts, entity_pages, total_pages)

    relations: List[RelationRecord] = []
    pair_occurrences: Counter[tuple[str, str]] = Counter()

    for page, items in page_groups.items():
        if len(items) < 2:
            continue

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
        page_label = page if page is not None else -1

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

            relations.append(
                RelationRecord(
                    subject=pair_key[0],
                    predicate="co_occurs_with",
                    object=pair_key[1],
                    attributes=attributes,
                    evidence=evidence,
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
                    predicate="co_occurs_with",
                    object=cui_right,
                    attributes=attributes,
                    evidence=evidence,
                )
            )

    return relations


__all__ = [
    "RelationRecord",
    "build_relations",
    "build_cooccurrence",
    "relations_from_outcomes",
    "relations_from_recommendations",
]
