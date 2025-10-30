from __future__ import annotations

import httpx
import pytest

from src.adapters.medparse_http_adapter import MedparseHTTPAdapter
from src.adapters.medparse_mcp_adapter import MedparseMCPAdapter
from src.adapters.medparse_transport import (
    ExtractRequest,
    LinkRequest,
    MedparseTransportConfigError,
    MedparseTransportDisabledError,
    MedparseTransportError,
    _TransportFactories,
    get_medparse_transport,
)
from src.config import AppConfig


def _build_http_adapter(handler: httpx.MockTransport) -> MedparseHTTPAdapter:
    client = httpx.Client(base_url="http://medparse.test", transport=handler, timeout=5.0)
    return MedparseHTTPAdapter(
        base_url="http://medparse.test",
        api_key=None,
        timeout=5.0,
        max_retries=1,
        retry_backoff=0.0,
        client=client,
    )


def test_http_adapter_preflight_runs_when_client_owned() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"ok": True})

    adapter = MedparseHTTPAdapter(
        base_url="http://medparse.test",
        api_key=None,
        timeout=httpx.Timeout(5.0),
        max_retries=1,
        retry_backoff=0.0,
        transport=httpx.MockTransport(handler),
    )
    assert calls == ["/healthz"]
    adapter.close()


def test_http_adapter_link_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/healthz":
            return httpx.Response(200, json={"ok": True})
        assert request.url.path == "/link"
        return httpx.Response(
            200,
            json={
                "entities": [{"id": "c1"}],
                "spans": [{"id": "s1"}],
                "concepts": [{"cui": "C123"}],
            },
        )

    adapter = _build_http_adapter(httpx.MockTransport(handler))
    assert adapter.health() is True

    response = adapter.link(LinkRequest(text="hemoptysis"))
    assert response["concepts"][0]["cui"] == "C123"
    adapter.close()


def test_http_adapter_extract_failure_on_500() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/extract":
            return httpx.Response(500, json={"detail": "pipeline unavailable"})
        return httpx.Response(200, json={"ok": True})

    adapter = _build_http_adapter(httpx.MockTransport(handler))
    with pytest.raises(MedparseTransportError):
        adapter.extract(ExtractRequest(doc_id="doc-1"))
    adapter.close()


class _StubMCPClient:
    def __init__(self) -> None:
        self.link_calls: list[dict] = []
        self.extract_calls: list[dict] = []

    def health(self, *, timeout: float) -> dict[str, str]:
        return {"status": "ok"}

    def link(self, payload: dict, *, timeout: float) -> dict:
        self.link_calls.append(payload)
        return {"entities": [], "spans": [], "concepts": [{"cui": "C999"}]}

    def extract(self, payload: dict, *, timeout: float) -> dict:
        self.extract_calls.append(payload)
        return {
            "metadata": {"doc_id": payload.get("doc_id", "unknown")},
            "sections": [],
            "statistics": [],
            "relations": [],
            "figures": [],
            "tables": [],
        }


def test_mcp_adapter_uses_stub_client() -> None:
    client = _StubMCPClient()
    adapter = MedparseMCPAdapter(client=client, timeout=5.0)

    assert adapter.health() is True

    link = adapter.link(LinkRequest(text="bronchial valve"))
    assert link["concepts"][0]["cui"] == "C999"
    assert client.link_calls[0]["text"] == "bronchial valve"

    extract = adapter.extract(ExtractRequest(doc_id="doc-x"))
    assert extract["metadata"]["doc_id"] == "doc-x"
    assert client.extract_calls[0]["doc_id"] == "doc-x"
    # No close method on stubbed client required


def test_get_medparse_transport_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDPARSE_ENABLED", "0")

    with pytest.raises(MedparseTransportDisabledError):
        get_medparse_transport(AppConfig())


def test_get_medparse_transport_custom_factories(monkeypatch: pytest.MonkeyPatch) -> None:
    class _DummyTransport:
        def __init__(self, flavour: str) -> None:
            self.flavour = flavour

        def health(self) -> bool:
            return True

        def link(self, req: LinkRequest):
            raise AssertionError("not used")

        def extract(self, req: ExtractRequest):
            raise AssertionError("not used")

    monkeypatch.setenv("MEDPARSE_ENABLED", "1")
    monkeypatch.setenv("MEDPARSE_TRANSPORT", "mcp")

    factories = _TransportFactories(
        http=lambda cfg: _DummyTransport("http"),  # type: ignore[arg-type]
        mcp=lambda cfg: _DummyTransport("mcp"),  # type: ignore[arg-type]
    )

    transport = get_medparse_transport(AppConfig(), factories=factories)
    assert isinstance(transport, _DummyTransport)
    assert transport.flavour == "mcp"


def test_http_factory_requires_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDPARSE_ENABLED", "1")
    monkeypatch.setenv("MEDPARSE_TRANSPORT", "http")
    monkeypatch.setenv("MEDPARSE_HTTP_BASE_URL", "")

    config = AppConfig()
    with pytest.raises(MedparseTransportConfigError):
        get_medparse_transport(config)
