"""Second-pass affiliation heuristics for NEJM-style front-matter."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from medparse.schema.article import Affiliation, ArticleDocument, Author
from medparse.schema.common import BaseDocument

from ..types import SecondPassContext, SecondPassPatchResult

PATCH_NAME = "article_affiliations"
SPLIT_PATTERN = re.compile(r"\s*[;–—]+\s*")
CONSORTIA_PATTERN = re.compile(r"\bfor the [A-Z][\w\s-]+\b", re.IGNORECASE)


def apply_article_affiliations(document: BaseDocument, ctx: SecondPassContext) -> SecondPassPatchResult:
    if not isinstance(document, ArticleDocument):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="doc_not_article")

    authors = document.authors or []
    affiliations = document.affiliations or []

    if not authors or not affiliations:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="missing_people")

    unresolved_before = _count_unresolved(authors)

    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    paragraph_store = ctx.paragraph_store or {}
    candidate_lines = _collect_candidate_lines(paragraph_store)

    split_affiliations, split_added = _split_affiliation_blocks(affiliations)
    consortia_list, filtered_affiliations = _extract_consortia(split_affiliations)

    aff_token_map = _build_affiliation_tokens(filtered_affiliations)
    aff_index_map = {aff.id: idx for idx, aff in enumerate(filtered_affiliations)}
    mapped_count = _map_authors_nearest(authors, candidate_lines, aff_token_map, aff_index_map)

    unresolved_after = _count_unresolved(authors)

    consortia_count = len(consortia_list)
    has_changes = (split_added + consortia_count + mapped_count) > 0
    if not has_changes:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_changes")

    document.affiliations = filtered_affiliations
    pipeline_info["frontmatter_affiliations_unresolved"] = unresolved_after
    if consortia_count:
        consortia_payload = pipeline_info.setdefault("affiliation_consortia", [])
        if isinstance(consortia_payload, list):
            consortia_payload.extend(consortia_list)
        else:
            pipeline_info["affiliation_consortia"] = consortia_list

    document.pipeline_info = pipeline_info

    modifications: Dict[str, int] = {}
    if split_added:
        modifications["affiliations_split"] = split_added
    if consortia_count:
        modifications["affiliations_consortia_removed"] = consortia_count
    if mapped_count:
        modifications["affiliations_mapped"] = mapped_count

    return SecondPassPatchResult(
        name=PATCH_NAME,
        applied=True,
        modifications=modifications,
        reasons=["affiliation_salvage"],
    )


def _count_unresolved(authors: Sequence[Author]) -> int:
    return sum(1 for author in authors if not (author.affiliation_ids or []))


def _split_affiliation_blocks(affiliations: Sequence[Affiliation]) -> Tuple[List[Affiliation], int]:
    new_affiliations: List[Affiliation] = []
    existing_ids = {str(aff.id) for aff in affiliations if aff.id}
    next_id = 1

    def _next_id() -> str:
        nonlocal next_id
        while str(next_id) in existing_ids:
            next_id += 1
        candidate = str(next_id)
        existing_ids.add(candidate)
        next_id += 1
        return candidate

    added = 0
    for affiliation in affiliations:
        text = (affiliation.text or "").strip()
        if not text:
            continue
        segments = [segment.strip() for segment in SPLIT_PATTERN.split(text) if segment.strip()]
        if not segments:
            continue
        base_id = str(affiliation.id) if affiliation.id else _next_id()
        affiliation.id = base_id
        affiliation.text = segments[0]
        new_affiliations.append(affiliation)
        if len(segments) == 1:
            continue
        for segment in segments[1:]:
            new_affiliations.append(
                Affiliation(
                    id=_next_id(),
                    text=segment,
                    department=affiliation.department,
                    institution=affiliation.institution,
                    city=affiliation.city,
                    country=affiliation.country,
                    address=affiliation.address,
                )
            )
            added += 1
    return new_affiliations, added


def _extract_consortia(affiliations: Sequence[Affiliation]) -> Tuple[List[str], List[Affiliation]]:
    consortia: List[str] = []
    filtered: List[Affiliation] = []
    for affiliation in affiliations:
        text_lower = (affiliation.text or "").lower()
        if CONSORTIA_PATTERN.search(text_lower):
            consortia.append(affiliation.text or "")
            continue
        filtered.append(affiliation)
    return consortia, filtered


def _collect_candidate_lines(paragraph_store: Dict[str, Dict[str, object]]) -> List[Tuple[int, str]]:
    ordered_entries: List[Tuple[int, int, str]] = []
    for entry in paragraph_store.values():
        text = entry.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        orders = entry.get("order") or []
        try:
            order_index = min(int(value) for value in orders) if orders else 10**6
        except (TypeError, ValueError):
            order_index = 10**6
        page = entry.get("page")
        if page is not None and page > 2:
            continue
        ordered_entries.append((order_index, int(page or 0), text))
    ordered_entries.sort(key=lambda item: item[0])

    lines: List[Tuple[int, str]] = []
    for order_index, page, text in ordered_entries:
        for raw_line in text.splitlines():
            cleaned = raw_line.strip()
            if cleaned:
                lines.append((page, cleaned))
        if len(lines) >= 120:
            break
    return lines


def _build_affiliation_tokens(affiliations: Sequence[Affiliation]) -> Dict[str, Set[str]]:
    token_map: Dict[str, Set[str]] = {}
    for affiliation in affiliations:
        aff_id = str(affiliation.id or "")
        tokens = _tokenize(affiliation.text)
        if affiliation.institution:
            tokens |= _tokenize(affiliation.institution)
        if affiliation.city:
            tokens.add(affiliation.city.lower())
        token_map[aff_id] = tokens
    return token_map


def _map_authors_nearest(
    authors: Sequence[Author],
    candidate_lines: Sequence[Tuple[int, str]],
    aff_token_map: Dict[str, Set[str]],
    aff_index_map: Dict[str, int],
) -> int:
    if not aff_token_map:
        return 0
    mapped = 0
    line_tokens: List[Tuple[int, Set[str]]]= []
    for idx, (_page, text) in enumerate(candidate_lines):
        line_tokens.append((idx, _tokenize(text)))

    for author in authors:
        if author.affiliation_ids:
            continue
        family = (author.family or "").strip()
        if not family:
            continue
        name_lower = family.lower()
        candidate_indices = [
            idx for idx, (_page, text) in enumerate(candidate_lines) if name_lower in text.lower()
        ]
        best_affiliation = _score_affiliations(candidate_indices, line_tokens, aff_token_map, aff_index_map)
        if best_affiliation is None:
            # Fallback: attempt global best match
            all_indices = list(range(min(len(line_tokens), 20)))
            best_affiliation = _score_affiliations(all_indices, line_tokens, aff_token_map, aff_index_map)
        if best_affiliation:
            author.affiliation_ids = [best_affiliation]
            mapped += 1
    return mapped


def _score_affiliations(
    indices: Sequence[int],
    line_tokens: Sequence[Tuple[int, Set[str]]],
    aff_token_map: Dict[str, Set[str]],
    aff_index_map: Dict[str, int],
) -> Optional[str]:
    best_candidates: List[str] = []
    best_score = 0
    for idx in indices:
        if idx >= len(line_tokens):
            continue
        _, tokens = line_tokens[idx]
        if not tokens:
            continue
        for aff_id, aff_tokens in aff_token_map.items():
            score = len(tokens & aff_tokens)
            if score == 0:
                continue
            if score > best_score:
                best_score = score
                best_candidates = [aff_id]
            elif score == best_score:
                best_candidates.append(aff_id)
    if best_score == 0:
        return None
    if len(best_candidates) == 1:
        return best_candidates[0]
    # Resolve ties by earliest affiliation index
    best_candidates.sort(key=lambda aff_id: aff_index_map.get(aff_id, 10**6))
    return best_candidates[0]


def _tokenize(text: Optional[str]) -> Set[str]:
    if not text:
        return set()
    return {token.lower() for token in re.findall(r"[A-Z][A-Za-z]{2,}", text)}


__all__ = ["apply_article_affiliations"]
