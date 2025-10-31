import base64
import json
from typing import Dict

import httpx
import pytest

from adapters.medparse_http_adapter import MedparseHTTPAdapter

REQUIRED_KEYS = ("metadata", "sections", "statistics", "relations", "figures", "tables")


def _sample_response() -> Dict[str, object]:
    return {
        "metadata": {"doc_id": "DUMMY"},
        "sections": [],
        "statistics": [],
        "relations": [],
        "figures": [],
        "tables": [],
    }


def _make_adapter(captured: dict, *, api_key: str | None = None, auth_header_name: str | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        captured["json"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json=_sample_response())

    client = httpx.Client(base_url="http://medparse.test", timeout=5.0, transport=httpx.MockTransport(handler))
    adapter = MedparseHTTPAdapter(
        base_url="http://medparse.test",
        api_key=api_key,
        auth_header_name=auth_header_name,
        timeout=5.0,
        max_retries=1,
        retry_backoff=0.0,
        client=client,
    )
    return adapter


def test_extract_contract_accepts_pdf_payload():
    captured: dict = {}
    adapter = _make_adapter(captured, api_key="test-key")
    try:
        payload = {"doc_id": "DUMMY", "bytes_b64": base64.b64encode(b"%PDF-1.4").decode("utf-8")}
        response = adapter.extract(payload)
    finally:
        adapter.close()

    assert captured["json"] == {
        "doc_id": "DUMMY",
        "pdf": payload["bytes_b64"],
    }
    for key in REQUIRED_KEYS:
        assert key in response
    assert response["metadata"]["doc_id"] == "DUMMY"


@pytest.mark.parametrize(
    "auth_header_name, expected_header, expected_value",
    [
        (None, "X-API-Key", "test-key"),
        ("Authorization", "Authorization", "Bearer test-key"),
    ],
)
def test_extract_contract_auth_headers(auth_header_name, expected_header, expected_value):
    captured: dict = {}
    adapter = _make_adapter(captured, api_key="test-key", auth_header_name=auth_header_name)
    try:
        adapter.extract({"doc_id": "DUMMY", "bytes_b64": base64.b64encode(b"pdf").decode("utf-8")})
    finally:
        adapter.close()

    assert captured["headers"][expected_header] == expected_value
