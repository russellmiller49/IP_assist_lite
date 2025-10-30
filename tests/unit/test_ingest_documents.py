from __future__ import annotations

import base64
from pathlib import Path

import pytest

from src.jobs.ingest_documents import ingest_pdf


class _StubTransport:
    def __init__(self) -> None:
        self.requests: list[dict] = []

    def health(self):  # pragma: no cover - not used
        return True

    def link(self, payload):  # pragma: no cover - not used
        raise NotImplementedError

    def extract(self, payload):
        self.requests.append(payload)
        return {
            "metadata": {"doc_id": payload["doc_id"], "title": "Test"},
            "sections": [],
            "statistics": [],
            "relations": [],
            "figures": [],
            "tables": [],
        }


def test_ingest_pdf_encodes_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF")

    transport = _StubTransport()

    graph_payload, summary = ingest_pdf(pdf, transport=transport, sinks=[])

    assert graph_payload["doc_id"] == "sample"
    assert summary.counts["sections"] == 0
    assert transport.requests
    encoded = transport.requests[0]["bytes_b64"]
    assert base64.b64decode(encoded.encode("utf-8")) == b"%PDF-1.4\n%EOF"
