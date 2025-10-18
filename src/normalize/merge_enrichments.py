"""Merge Medparse extraction payloads into graph-friendly structures."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

from adapters.medparse_transport import ExtractResponse
from .types import (
    FigureNode,
    GraphPayload,
    RecommendationNode,
    RelationEdge,
    SectionNode,
    SectionSpan,
    StatNode,
    TableNode,
)


def extract_to_graph_payload(extract_resp: ExtractResponse) -> GraphPayload:
    """Convert a Medparse extraction response into a graph payload."""

    metadata = dict(extract_resp.get("metadata") or {})
    doc_id = _resolve_doc_id(extract_resp, metadata)

    id_map: Dict[str, str] = {}
    sections, section_lookup = _normalise_sections(doc_id, extract_resp.get("sections") or [], id_map)

    nodes: Dict[str, List[Dict[str, Any]]] = {
        "Recommendation": [],
        "Stat": [],
        "Figure": [],
        "Table": [],
    }

    nodes["Recommendation"] = _normalise_recommendations(
        doc_id,
        extract_resp.get("recommendations") or [],
        sections,
        section_lookup,
        id_map,
    )
    nodes["Stat"] = _normalise_statistics(
        doc_id,
        extract_resp.get("statistics") or [],
        sections,
        section_lookup,
        id_map,
    )
    nodes["Figure"] = _normalise_figures(
        doc_id,
        extract_resp.get("figures") or [],
        sections,
        section_lookup,
        id_map,
    )
    nodes["Table"] = _normalise_tables(
        doc_id,
        extract_resp.get("tables") or [],
        sections,
        section_lookup,
        id_map,
    )

    edges = _normalise_relations(extract_resp.get("relations") or [], id_map)

    doc_meta: Dict[str, Any] = dict(metadata)
    if "quality" in extract_resp and extract_resp["quality"] is not None:
        quality = extract_resp["quality"]
        if isinstance(quality, Mapping):
            doc_meta["quality"] = dict(quality)
    if "validation" in extract_resp and extract_resp["validation"] is not None:
        validation = extract_resp["validation"]
        if isinstance(validation, Mapping):
            doc_meta["validation"] = dict(validation)

    return GraphPayload(
        doc_id=doc_id,
        doc_meta=doc_meta,
        sections=sections,
        nodes=nodes,
        edges=edges,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_doc_id(extract_resp: ExtractResponse, metadata: Mapping[str, Any]) -> str:
    candidates: Iterable[Any] = (
        metadata.get("doc_id"),
        metadata.get("document_id"),
        metadata.get("source_id"),
        metadata.get("source_file"),
        extract_resp.get("doc_id") if isinstance(extract_resp, Mapping) else None,
    )
    for candidate in candidates:
        if candidate:
            return str(candidate)
    raise ValueError("Medparse extract response missing doc identifier in metadata.")


def _normalise_sections(
    doc_id: str,
    raw_sections: Iterable[Mapping[str, Any]],
    id_map: MutableMapping[str, str],
) -> Tuple[List[SectionNode], Dict[str, SectionNode]]:
    sections: List[SectionNode] = []
    lookup: Dict[str, SectionNode] = {}

    for index, section in enumerate(raw_sections):
        local_id = str(section.get("id") or section.get("section_id") or index)
        uid = _build_uid(doc_id, "section", local_id)

        spans = _normalise_spans(section)
        page_start, page_end = _determine_page_bounds(section, spans)

        node: SectionNode = SectionNode(
            uid=uid,
            doc_id=doc_id,
            title=str(section.get("title") or section.get("heading") or ""),
            text=str(section.get("text") or section.get("body") or ""),
            page_start=page_start,
            page_end=page_end,
            spans=spans,
        )
        sections.append(node)
        lookup[local_id] = node

        _register_id(id_map, local_id, "section", uid)

    return sections, lookup


def _normalise_spans(section: Mapping[str, Any]) -> List[SectionSpan]:
    candidates = section.get("spans") or section.get("evidence_spans") or []
    if not isinstance(candidates, list):
        return []

    spans: List[SectionSpan] = []
    for idx, span in enumerate(candidates):
        if not isinstance(span, Mapping):
            continue
        raw_id = span.get("id") or f"{idx}"
        span_id = str(raw_id)
        page = _coerce_int(span.get("page") or span.get("page_number"))
        bbox = _coerce_bbox(span.get("bbox") or span.get("bbox_norm"))
        text = span.get("text") or span.get("content")
        spans.append(SectionSpan(id=span_id, page=page, bbox=bbox, text=str(text) if text else None))
    return spans


def _determine_page_bounds(section: Mapping[str, Any], spans: List[SectionSpan]) -> Tuple[Optional[int], Optional[int]]:
    pages: List[int] = []
    for candidate in (
        section.get("page"),
        section.get("page_anchor"),
        section.get("page_start"),
        section.get("page_end"),
    ):
        page_val = _coerce_int(candidate)
        if page_val is not None:
            pages.append(page_val)
    for span in spans:
        if span.get("page") is not None:
            pages.append(span["page"])  # type: ignore[arg-type]
    if not pages:
        return None, None
    return min(pages), max(pages)


def _normalise_recommendations(
    doc_id: str,
    recommendations: Iterable[Mapping[str, Any]],
    sections: List[SectionNode],
    section_lookup: Mapping[str, SectionNode],
    id_map: MutableMapping[str, str],
) -> List[RecommendationNode]:
    nodes: List[RecommendationNode] = []
    for index, rec in enumerate(recommendations):
        if not isinstance(rec, Mapping):
            continue
        local_id = str(rec.get("id") or rec.get("uid") or f"rec-{index}")
        uid = _build_uid(doc_id, "rec", local_id)
        text = str(rec.get("text") or rec.get("statement") or "")
        grade = rec.get("grade") or rec.get("strength") or rec.get("evidence_level")
        page, bbox, span_id = _extract_location(rec)

        node: RecommendationNode = RecommendationNode(
            uid=uid,
            doc_id=doc_id,
            text=text,
            grade=str(grade) if grade is not None else None,
            page=page,
            span_id=span_id,
        )
        if bbox:
            node["bbox"] = bbox  # type: ignore[index]

        section_uid, resolved_span_id = _resolve_section_for_item(rec, page, span_id, sections, section_lookup)
        if section_uid:
            node["section_uid"] = section_uid
        if resolved_span_id:
            node["span_id"] = resolved_span_id

        nodes.append(node)
        _register_id(id_map, local_id, "rec", uid)
    return nodes


def _normalise_statistics(
    doc_id: str,
    statistics: Iterable[Mapping[str, Any]],
    sections: List[SectionNode],
    section_lookup: Mapping[str, SectionNode],
    id_map: MutableMapping[str, str],
) -> List[StatNode]:
    nodes: List[StatNode] = []
    for index, stat in enumerate(statistics):
        if not isinstance(stat, Mapping):
            continue
        local_id = str(stat.get("id") or stat.get("uid") or f"stat-{index}")
        uid = _build_uid(doc_id, "stat", local_id)
        stat_type = str(stat.get("type") or stat.get("stat_type") or stat.get("kind") or "statistic")
        value = _coerce_float(stat.get("value"))
        ci = stat.get("ci") or stat.get("confidence_interval")
        p_value = _coerce_float(stat.get("p_value") or stat.get("pvalue"))
        page, bbox, span_id = _extract_location(stat)

        node: StatNode = StatNode(
            uid=uid,
            doc_id=doc_id,
            stat_type=stat_type,
            value=value,
            ci=str(ci) if ci is not None else None,
            p_value=p_value,
            page=page,
            bbox=bbox,
            span_id=span_id,
        )

        section_uid, resolved_span_id = _resolve_section_for_item(stat, page, span_id, sections, section_lookup)
        if section_uid:
            node["section_uid"] = section_uid
        if resolved_span_id:
            node["span_id"] = resolved_span_id

        nodes.append(node)
        _register_id(id_map, local_id, "stat", uid)
    return nodes


def _normalise_figures(
    doc_id: str,
    figures: Iterable[Mapping[str, Any]],
    sections: List[SectionNode],
    section_lookup: Mapping[str, SectionNode],
    id_map: MutableMapping[str, str],
) -> List[FigureNode]:
    nodes: List[FigureNode] = []
    for index, figure in enumerate(figures):
        if not isinstance(figure, Mapping):
            continue
        local_id = str(figure.get("id") or figure.get("uid") or f"figure-{index}")
        uid = _build_uid(doc_id, "fig", local_id)
        caption = str(figure.get("caption") or figure.get("title") or "")
        image_b64 = figure.get("image_b64") or figure.get("image")
        page, bbox, span_id = _extract_location(figure)

        node: FigureNode = FigureNode(
            uid=uid,
            doc_id=doc_id,
            caption=caption,
            page=page,
            bbox=bbox,
            image_b64=str(image_b64) if image_b64 else None,
            span_id=span_id,
        )

        section_uid, resolved_span_id = _resolve_section_for_item(figure, page, span_id, sections, section_lookup)
        if section_uid:
            node["section_uid"] = section_uid
        if resolved_span_id:
            node["span_id"] = resolved_span_id

        nodes.append(node)
        _register_id(id_map, local_id, "figure", uid)
    return nodes


def _normalise_tables(
    doc_id: str,
    tables: Iterable[Mapping[str, Any]],
    sections: List[SectionNode],
    section_lookup: Mapping[str, SectionNode],
    id_map: MutableMapping[str, str],
) -> List[TableNode]:
    nodes: List[TableNode] = []
    for index, table in enumerate(tables):
        if not isinstance(table, Mapping):
            continue
        local_id = str(table.get("id") or table.get("uid") or f"table-{index}")
        uid = _build_uid(doc_id, "table", local_id)
        caption = str(table.get("caption") or table.get("title") or "")
        csv_path = table.get("csv_path")
        page, bbox, span_id = _extract_location(table)

        node: TableNode = TableNode(
            uid=uid,
            doc_id=doc_id,
            caption=caption,
            page=page,
            bbox=bbox,
            csv_path=str(csv_path) if csv_path else None,
            span_id=span_id,
        )

        section_uid, resolved_span_id = _resolve_section_for_item(table, page, span_id, sections, section_lookup)
        if section_uid:
            node["section_uid"] = section_uid
        if resolved_span_id:
            node["span_id"] = resolved_span_id

        nodes.append(node)
        _register_id(id_map, local_id, "table", uid)
    return nodes


def _normalise_relations(relations: Iterable[Mapping[str, Any]], id_map: Mapping[str, str]) -> List[RelationEdge]:
    edges: List[RelationEdge] = []
    for rel in relations:
        if not isinstance(rel, Mapping):
            continue
        source_id = rel.get("source") or rel.get("subject") or rel.get("subject_id")
        target_id = rel.get("target") or rel.get("object") or rel.get("object_id")
        if not source_id or not target_id:
            continue
        source_uid = _resolve_identifier(id_map, source_id)
        target_uid = _resolve_identifier(id_map, target_id)
        if not source_uid or not target_uid:
            continue
        rel_type = str(rel.get("type") or rel.get("predicate") or "RELATED_TO")
        edges.append(RelationEdge(type=rel_type, source_uid=source_uid, target_uid=target_uid))
    return edges


def _resolve_section_for_item(
    item: Mapping[str, Any],
    page: Optional[int],
    span_id: Optional[str],
    sections: List[SectionNode],
    section_lookup: Mapping[str, SectionNode],
) -> Tuple[Optional[str], Optional[str]]:
    section_hint = item.get("section_id") or item.get("section") or item.get("section_uid")
    if section_hint:
        section = section_lookup.get(str(section_hint))
        if section:
            matched_span_id = span_id or _find_span_on_page(section, page)
            return section["uid"], matched_span_id
    if page is not None:
        section, span = _find_section_for_page(sections, page)
        if section:
            matched_span_id = span_id or (span.get("id") if span else None)
            return section["uid"], matched_span_id
    return None, span_id


def _find_span_on_page(section: SectionNode, page: Optional[int]) -> Optional[str]:
    if page is None:
        return None
    for span in section["spans"]:
        if span.get("page") == page and span.get("id"):
            return str(span["id"])
    return None


def _find_section_for_page(sections: List[SectionNode], page: int) -> Tuple[Optional[SectionNode], Optional[SectionSpan]]:
    for section in sections:
        if section.get("page_start") is not None and section.get("page_end") is not None:
            if section["page_start"] <= page <= section["page_end"]:
                matching_span = _find_span_on_page(section, page)
                span_obj = next((span for span in section["spans"] if span.get("id") == matching_span), None)
                return section, span_obj
        for span in section["spans"]:
            if span.get("page") == page:
                return section, span
    return None, None


def _extract_location(item: Mapping[str, Any]) -> Tuple[Optional[int], Optional[List[float]], Optional[str]]:
    spans = item.get("spans") or item.get("evidence_spans") or []
    if isinstance(spans, list) and spans:
        candidate = spans[0]
        if isinstance(candidate, Mapping):
            page = _coerce_int(candidate.get("page") or candidate.get("page_number"))
            bbox = _coerce_bbox(candidate.get("bbox") or candidate.get("bbox_norm"))
            span_id = candidate.get("id")
            return page, bbox, str(span_id) if span_id else None

    page = _coerce_int(item.get("page") or item.get("page_number") or item.get("page_anchor"))
    bbox = _coerce_bbox(item.get("bbox") or item.get("bbox_norm"))
    return page, bbox, None


def _register_id(id_map: MutableMapping[str, str], local_id: str, prefix: str, uid: str) -> None:
    id_map.setdefault(str(local_id), uid)
    id_map.setdefault(f"{prefix}:{local_id}", uid)


def _resolve_identifier(id_map: Mapping[str, str], identifier: Any) -> Optional[str]:
    if identifier is None:
        return None
    key = str(identifier)
    if key in id_map:
        return id_map[key]
    # Try with common prefixes
    for prefix in ("rec", "stat", "figure", "table", "section"):
        composite = f"{prefix}:{key}"
        if composite in id_map:
            return id_map[composite]
    return None


def _build_uid(doc_id: str, prefix: str, local_id: str) -> str:
    safe_local = local_id.replace(" ", "_")
    return f"{doc_id}:{prefix}:{safe_local}"


def _coerce_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_bbox(value: Any) -> Optional[List[float]]:
    if value is None:
        return None
    if isinstance(value, Mapping):
        # Some payloads use dicts e.g. {"x0":..,"y0":..}
        ordered = [value.get(key) for key in ("x0", "y0", "x1", "y1")]
        if any(v is None for v in ordered):
            return None
        return [_coerce_float(v) or 0.0 for v in ordered]
    if isinstance(value, (list, tuple)) and len(value) == 4:
        coerced = [_coerce_float(v) for v in value]
        if any(v is None for v in coerced):
            return None
        return [v if v is not None else 0.0 for v in coerced]
    return None


__all__ = ["extract_to_graph_payload"]
