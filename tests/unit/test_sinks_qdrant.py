from __future__ import annotations

from typing import List

from qdrant_client.models import PointStruct

from src.graph.sinks.qdrant_sink import QdrantSink


class _StubQdrantClient:
    def __init__(self) -> None:
        self.upserts: List[tuple[str, List[PointStruct]]] = []
        self.collections: set[str] = set()

    def get_collection(self, name: str):
        if name not in self.collections:
            raise ValueError("missing")
        return {}

    def recreate_collection(self, collection_name, vectors_config):
        self.collections.add(collection_name)

    def upsert(self, *, collection_name: str, points: List[PointStruct]):
        self.upserts.append((collection_name, points))


def test_qdrant_sink_upserts_evidence_and_sections() -> None:
    client = _StubQdrantClient()
    sink = QdrantSink(
        client,
        section_collection="ip_sections_v1",
        rec_collection="ip_recs_v1",
        figtab_collection="ip_figtabs_v1",
        embed_fn=lambda text: [float(len(text) % 5), 0.0, 0.0],
    )

    payload = {
        "doc_id": "doc-1",
        "doc_meta": {},
        "sections": [
            {
                "uid": "doc-1:section:s1",
                "doc_id": "doc-1",
                "title": "Intro",
                "text": "Section text",
                "page_start": 1,
                "page_end": 1,
                "spans": [],
            }
        ],
        "nodes": {
            "Recommendation": [
                {
                    "uid": "doc-1:rec:r1",
                    "doc_id": "doc-1",
                    "text": "Use sedation",
                    "section_uid": "doc-1:section:s1",
                }
            ],
            "Stat": [],
            "Figure": [
                {"uid": "doc-1:fig:f1", "doc_id": "doc-1", "caption": "Figure caption", "page": 2}
            ],
            "Table": [
                {"uid": "doc-1:table:t1", "doc_id": "doc-1", "caption": "Table caption", "page": 3}
            ],
        },
        "edges": [],
    }

    sink.upsert(payload)  # type: ignore[arg-type]

    collections = {name for name, _ in client.upserts}
    assert {"ip_sections_v1", "ip_recs_v1", "ip_figtabs_v1"}.issubset(collections)
