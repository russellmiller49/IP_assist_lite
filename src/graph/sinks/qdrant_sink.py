"""Qdrant sink for Medparse evidence payloads."""
from __future__ import annotations

from typing import Any, Callable, List, Sequence

from qdrant_client import QdrantClient
from qdrant_client.http import models as rest_models
from qdrant_client.models import PointStruct

from ...normalize.types import GraphPayload, RecommendationNode


class QdrantSink:
    """Persist Medparse sections and evidence into Qdrant."""

    def __init__(
        self,
        client: QdrantClient,
        *,
        evidence_collection: str,
        section_collection: str,
        embed_fn: Callable[[str], Sequence[float]],
    ) -> None:
        self._client = client
        self._evidence_collection = evidence_collection
        self._section_collection = section_collection
        self._embed = embed_fn

    @classmethod
    def from_config(
        cls,
        config,
        *,
        embed_fn: Callable[[str], Sequence[float]] | None = None,
    ) -> "QdrantSink":  # pragma: no cover - heavy dependency path
        if embed_fn is None:
            raise RuntimeError(
                "An embedding function must be provided to QdrantSink.from_config. "
                "Pass a callable that converts text into vector embeddings."
            )
        client = QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY)
        return cls(
            client,
            evidence_collection=config.QDRANT_COLLECTION_EVIDENCE,
            section_collection=config.QDRANT_COLLECTION_SECTIONS,
            embed_fn=embed_fn,
        )

    def upsert(self, payload: GraphPayload) -> None:
        evidence_points = self._build_evidence_points(payload)
        if evidence_points:
            self._ensure_collection(self._evidence_collection, len(evidence_points[0].vector))
            self._client.upsert(collection_name=self._evidence_collection, points=evidence_points)

        section_points = self._build_section_points(payload)
        if section_points:
            self._ensure_collection(self._section_collection, len(section_points[0].vector))
            self._client.upsert(collection_name=self._section_collection, points=section_points)

    def _build_evidence_points(self, payload: GraphPayload) -> List[PointStruct]:
        doc_id = payload["doc_id"]
        points: List[PointStruct] = []
        recommendations: List[RecommendationNode] = payload.get("nodes", {}).get("Recommendation", [])  # type: ignore[index]
        for rec in recommendations:
            text = rec.get("text", "")
            if not text:
                continue
            vector = list(self._embed(text))
            point_id = f"{doc_id}::rec::{rec['uid']}"
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "uid": rec["uid"],
                        "doc_id": doc_id,
                        "kind": "recommendation",
                        "grade": rec.get("grade"),
                        "section_uid": rec.get("section_uid"),
                        "page": rec.get("page"),
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
            point_id = f"{doc_id}::section::{section['uid']}"
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "uid": section["uid"],
                        "doc_id": doc_id,
                        "kind": "section",
                        "title": section.get("title"),
                        "page_start": section.get("page_start"),
                        "page_end": section.get("page_end"),
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


__all__ = ["QdrantSink"]
