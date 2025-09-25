import asyncio
import json
from pathlib import Path

import httpx
import pytest

from src.adapters.medparse_client import (
    MedparseAuthError,
    MedparseClient,
    MedparseConfig,
    MedparseError,
)


def _make_client(transport: httpx.MockTransport, **config_overrides) -> MedparseClient:
    config = MedparseConfig(base_url="https://medparse.test", **config_overrides)
    return MedparseClient(config, transport=transport)


def test_link_success(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/link"
        payload = json.loads(request.content.decode())
        assert payload["text"] == "massive hemoptysis"
        assert payload["top_k"] == 5
        return httpx.Response(200, json={"doc_id": None, "umls_links": [{"cui": "C123"}]})

    transport = httpx.MockTransport(handler)
    client = _make_client(transport, max_retries=1)

    result = asyncio.run(client.link("massive hemoptysis", top_k=5))
    asyncio.run(client.aclose())

    assert result["umls_links"][0]["cui"] == "C123"


def test_extract_retries_then_succeeds(tmp_path: Path):
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/extract":
            attempts["count"] += 1
            if attempts["count"] == 1:
                return httpx.Response(500, json={"detail": "pipeline busy"})
            return httpx.Response(200, json={"doc_id": "DOC1", "metadata": {}})
        raise AssertionError("Unexpected path")

    transport = httpx.MockTransport(handler)
    client = _make_client(transport, max_retries=2, retry_backoff=0)

    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%EOF")

    result = asyncio.run(client.extract(pdf_path, doc_id="DOC1"))
    asyncio.run(client.aclose())

    assert attempts["count"] == 2
    assert result["doc_id"] == "DOC1"


def test_link_raises_on_auth_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "invalid"})

    transport = httpx.MockTransport(handler)
    client = _make_client(transport, max_retries=1)

    with pytest.raises(MedparseAuthError):
        asyncio.run(client.link("anything"))
    asyncio.run(client.aclose())


def test_link_raises_on_invalid_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json", headers={"content-type": "application/json"})

    transport = httpx.MockTransport(handler)
    client = _make_client(transport, max_retries=1)

    with pytest.raises(MedparseError):
        asyncio.run(client.link("anything"))
    asyncio.run(client.aclose())
