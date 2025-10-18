"""Qdrant sink for Medparse evidence payloads."""
from __future__ import annotations

from typing import Any, Callable, List, Sequence

from qdrant_client import QdrantClient
from qdrant_client.http import models as rest_models
from qdrant_client.models import PointStruct

from normalize.types import GraphPayload, RecommendationNode


class QdrantSink:
    """Persist Medparse sections and evidence into Qdrant."""

    def __init__(
        self,
        client: QdrantClient,
        *,
        section_collection: str,
        rec_collection: str,
        figtab_collection: str,
        embed_fn: Callable[[str], Sequence[float]],
    ) -> None:
        self._client = client
        self._section_collection = section_collection
        self._rec_collection = rec_collection
        self._figtab_collection = figtab_collection
        self._embed = embed_fn

    @classmethod
    def from_config(
        cls,
        config,
        *,
        embed_fn: Callable[[str], Sequence[float]] | None = None,
    ) -> "QdrantSink":  # pragma: no cover - heavy dependency path
        if embed_fn is None:
            embed_fn = _default_embedder
        client = QdrantClient(
            url=config.QDRANT_URL,
            api_key=config.QDRANT_API_KEY,
            timeout=60,
            prefer_grpc=False,
            check_compatibility=False,
        )
        return cls(
            client,
            section_collection=config.QDRANT_COLLECTION_SECTIONS,
            rec_collection=config.QDRANT_COLLECTION_RECS,
            figtab_collection=config.QDRANT_COLLECTION_FIGTABS,
            embed_fn=embed_fn,
        )

    def upsert(self, payload: GraphPayload) -> None:
        section_points = self._build_section_points(payload)
        if section_points:
            self._ensure_collection(self._section_collection, len(section_points[0].vector))
            self._client.upsert(collection_name=self._section_collection, points=section_points)

        rec_points = self._build_recommendation_points(payload)
        if rec_points:
            self._ensure_collection(self._rec_collection, len(rec_points[0].vector))
            self._client.upsert(collection_name=self._rec_collection, points=rec_points)

        figtab_points = self._build_figtab_points(payload)
        if figtab_points:
            self._ensure_collection(self._figtab_collection, len(figtab_points[0].vector))
            self._client.upsert(collection_name=self._figtab_collection, points=figtab_points)

    def _build_recommendation_points(self, payload: GraphPayload) -> List[PointStruct]:
        doc_id = payload["doc_id"]
        points: List[PointStruct] = []
        support_counts = _support_counts(payload)
        recommendations: List[RecommendationNode] = payload.get("nodes", {}).get("Recommendation", [])  # type: ignore[index]
        for rec in recommendations:
            text = rec.get("text", "")
            if not text:
                continue
            vector = list(self._embed(text))
            point_id = f"{doc_id}::rec::{rec.get('uid') or rec.get('id')}"
            node_id = rec.get("uid") or rec.get("id")
            if not node_id:
                continue
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "doc_id": doc_id,
                        "node_id": node_id,
                        "kind": "recommendation",
                        "text": text,
                        "grade": rec.get("grade"),
                        "page": rec.get("page"),
                        "span_id": rec.get("span_id"),
                        "section_uid": rec.get("section_uid"),
                        "supported_by": support_counts.get(node_id, 0),
                    },
                )
            )
        return points

    def _build_section_points(self, payload: GraphPayload) -> List[PointStruct]:
        doc_id = payload["doc_id"]
        points: List[PointStruct] = []
        for section in payload.get("sections", []):
            text = section.get("text", "")
            if not text:
                continue
            vector = list(self._embed(text))
            section_id = section.get("uid") or section.get("id")
            if not section_id:
                continue
            point_id = f"{doc_id}::section::{section_id}"
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "doc_id": doc_id,
                        "node_id": section_id,
                        "doc_id": doc_id,
                        "kind": "section",
                        "title": section.get("title"),
                        "page_start": section.get("page_start"),
                        "page_end": section.get("page_end"),
                        "text": text,
                    },
                )
            )
        return points

    def _build_figtab_points(self, payload: GraphPayload) -> List[PointStruct]:
        doc_id = payload["doc_id"]
        points: List[PointStruct] = []
        nodes = payload.get("nodes", {})
        figure_nodes = nodes.get("Figure", []) if isinstance(nodes, dict) else []
        table_nodes = nodes.get("Table", []) if isinstance(nodes, dict) else []

        for figure in figure_nodes:
            caption = figure.get("caption", "")
            if not caption:
                continue
            vector = list(self._embed(caption))
            node_id = figure.get("uid") or figure.get("id")
            if not node_id:
                continue
            points.append(
                PointStruct(
                    id=f"{doc_id}::figure::{node_id}",
                    vector=vector,
                    payload={
                        "doc_id": doc_id,
                        "node_id": node_id,
                        "kind": "figure",
                        "caption": caption,
                        "page": figure.get("page"),
                        "bbox": figure.get("bbox"),
                        "section_uid": figure.get("section_uid"),
                    },
                )
            )

        for table in table_nodes:
            caption = table.get("caption", "")
            if not caption:
                continue
            vector = list(self._embed(caption))
            node_id = table.get("uid") or table.get("id")
            if not node_id:
                continue
            points.append(
                PointStruct(
                    id=f"{doc_id}::table::{node_id}",
                    vector=vector,
                    payload={
                        "doc_id": doc_id,
                        "node_id": node_id,
                        "kind": "table",
                        "caption": caption,
                        "page": table.get("page"),
                        "bbox": table.get("bbox"),
                        "section_uid": table.get("section_uid"),
                    },
                )
            )

        return points

    def _ensure_collection(self, collection_name: str, vector_dim: int) -> None:
        try:
            self._client.get_collection(collection_name)
            return
        except Exception:  # pragma: no cover - depends on qdrant client behaviour
            pass
        self._client.recreate_collection(
            collection_name=collection_name,
            vectors_config=rest_models.VectorParams(size=vector_dim, distance=rest_models.Distance.COSINE),
        )


def _default_embedder(text: str) -> Sequence[float]:
    length = float(len(text) or 1)
    return [length, length % 3, (length % 5) / 5.0]


def _support_counts(payload: GraphPayload) -> dict[str, int]:
    counts: dict[str, int] = {}
    for edge in payload.get("edges", []):
        if str(edge.get("type")) != "SUPPORTED_BY":
            continue
        source = edge.get("source_uid") or edge.get("source_id")
        if not source:
            continue
        counts[source] = counts.get(source, 0) + 1
    return counts


__all__ = ["QdrantSink"]
