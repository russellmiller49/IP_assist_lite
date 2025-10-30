import asyncio
from types import SimpleNamespace

import pytest

from src.retrieval import retriever_v2


class _StubTransport:
    def __init__(self) -> None:
        self.requests = []

    def health(self) -> bool:  # pragma: no cover - simple boolean
        return True

    def link(self, payload):
        self.requests.append(payload)
        return {
            "concepts": [
                {"preferred_name": "Bronchial Thermoplasty"},
                {"label": "Asthma"},
            ]
        }

    def extract(self, payload):  # pragma: no cover - not used in this test
        raise NotImplementedError


def test_retriever_enriches_query_with_medparse(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _StubTransport()

    queries: list[str] = []

    monkeypatch.setenv("MEDPARSE_ENABLED", "1")
    monkeypatch.setenv("MEDPARSE_TRANSPORT", "http")
    monkeypatch.setenv("APP_USE_QDRANT", "0")

    monkeypatch.setattr(retriever_v2, "get_medparse_transport", lambda cfg: transport)

    def fake_search(query: str, store: str, top_k: int = 8):
        queries.append(query)
        return [{"id": "chunk-1", "score": 0.99, "text": "", "payload": {}}]

    monkeypatch.setattr(retriever_v2, "_search_named", fake_search)
    monkeypatch.setattr(retriever_v2, "choose_store", lambda q: SimpleNamespace(store="chunks", confidence=0.6))
    monkeypatch.setattr(
        retriever_v2,
        "_collect_evidence",
        lambda query, cfg: {
            "recommendation_hits": [],
            "section_hits": [],
            "evidence_items": [],
            "evidence_summary": {"recommendations": 0, "stats": 0, "figures": 0, "tables": 0},
        },
    )

    result = asyncio.run(retriever_v2.retrieve_with_fallback("airway remodeling"))

    assert "Bronchial Thermoplasty" in result["medparse_terms"]
    assert queries[0].startswith("airway remodeling")
    assert "Bronchial Thermoplasty" in queries[0]
