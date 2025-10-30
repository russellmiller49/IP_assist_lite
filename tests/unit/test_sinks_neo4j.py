from __future__ import annotations

from src.graph.sinks.neo4j_sink import Neo4jSink


class _FakeTx:
    def __init__(self) -> None:
        self.queries: list[tuple[str, dict]] = []

    def run(self, query: str, **params) -> None:
        self.queries.append((query, params))


class _FakeSession:
    def __init__(self) -> None:
        self.tx = _FakeTx()

    def __enter__(self) -> "_FakeSession":  # pragma: no cover - context mgmt trivial
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - context mgmt trivial
        return None

    def execute_write(self, fn, payload) -> None:
        fn(self.tx, payload)


class _FakeDriver:
    def __init__(self) -> None:
        self.session_obj = _FakeSession()

    def session(self, database=None) -> _FakeSession:  # noqa: D401 - signature parity
        return self.session_obj

    def close(self) -> None:  # pragma: no cover - nothing to release
        return None


def test_neo4j_sink_generates_relationship_queries() -> None:
    driver = _FakeDriver()
    sink = Neo4jSink(driver, database=None)

    payload = {
        "doc_id": "doc-1",
        "doc_meta": {"title": "Sample"},
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
            "Stat": [
                {
                    "uid": "doc-1:stat:s1",
                    "doc_id": "doc-1",
                    "stat_type": "sensitivity",
                    "value": 0.9,
                }
            ],
            "Figure": [],
            "Table": [],
        },
        "edges": [
            {
                "type": "SUPPORTED_BY",
                "source_uid": "doc-1:rec:r1",
                "target_uid": "doc-1:stat:s1",
            }
        ],
    }

    sink.upsert(payload)  # type: ignore[arg-type]

    queries = driver.session_obj.tx.queries
    assert any("MERGE (d:Document {doc_id" in q for q, _ in queries)
    assert any("HAS_RECOMMENDATION" in q for q, _ in queries)
    assert any("SUPPORTED_BY" in q for q, _ in queries)
