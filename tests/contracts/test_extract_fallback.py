import base64

import httpx
import pytest

from adapters.medparse_http_adapter import MedparseHTTPAdapter


def _minimal_extract_response() -> dict:
    return {
        "metadata": {},
        "sections": [],
        "statistics": [],
        "relations": [],
        "figures": [],
        "tables": [],
    }


@pytest.mark.parametrize("success_field", ["pdf", "file"])
def test_extract_auto_fallback_to_multipart(success_field: str) -> None:
    call_counter = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        index = call_counter["count"]
        call_counter["count"] += 1
        content_type = request.headers.get("content-type", "")
        if index == 0:
            assert "application/json" in content_type
            return httpx.Response(422, json={"detail": "missing body fields"})
        if index == 1:
            assert "application/x-www-form-urlencoded" in content_type
            return httpx.Response(422, json={"detail": "form unsupported"})

        assert "multipart/form-data" in content_type
        body = request.content.decode("latin1")
        if index == 2:
            assert 'name="pdf"' in body
            if success_field == "pdf":
                return httpx.Response(200, json=_minimal_extract_response())
            return httpx.Response(422, json={"detail": "try file"})

        assert success_field == "file"
        assert 'name="file"' in body
        return httpx.Response(200, json=_minimal_extract_response())

    transport = httpx.MockTransport(handler)
    client = httpx.Client(base_url="http://medparse.test", transport=transport, timeout=5.0)
    adapter = MedparseHTTPAdapter(
        base_url="http://medparse.test",
        api_key=None,
        timeout=5.0,
        max_retries=1,
        retry_backoff=0.0,
        client=client,
    )

    try:
        payload = {"doc_id": "ping", "bytes_b64": base64.b64encode(b"%PDF-FAKE").decode()}
        result = adapter.extract(payload)
    finally:
        adapter.close()

    assert result["sections"] == []
    expected_calls = 3 if success_field == "pdf" else 4
    assert call_counter["count"] == expected_calls


def test_extract_forced_json_mode() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "application/json" in request.headers.get("content-type", "")
        return httpx.Response(200, json=_minimal_extract_response())

    client = httpx.Client(
        base_url="http://medparse.test",
        transport=httpx.MockTransport(handler),
        timeout=5.0,
    )
    adapter = MedparseHTTPAdapter(
        base_url="http://medparse.test",
        api_key=None,
        timeout=5.0,
        max_retries=1,
        retry_backoff=0.0,
        client=client,
        extract_mode="json",
    )

    try:
        payload = {"doc_id": "ping", "bytes_b64": base64.b64encode(b"%PDF-FAKE").decode()}
        result = adapter.extract(payload)
    finally:
        adapter.close()

    assert result["figures"] == []


def test_extract_forced_multipart_mode_fallback() -> None:
    call_counter = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        index = call_counter["count"]
        call_counter["count"] += 1
        assert "multipart/form-data" in request.headers.get("content-type", "")
        body = request.content.decode("latin1")
        if index == 0:
            assert 'name="pdf"' in body
            return httpx.Response(422, json={"detail": "missing file field"})
        assert 'name="file"' in body
        return httpx.Response(200, json=_minimal_extract_response())

    client = httpx.Client(
        base_url="http://medparse.test",
        transport=httpx.MockTransport(handler),
        timeout=5.0,
    )
    adapter = MedparseHTTPAdapter(
        base_url="http://medparse.test",
        api_key=None,
        timeout=5.0,
        max_retries=1,
        retry_backoff=0.0,
        client=client,
        extract_mode="multipart",
    )

    try:
        payload = {"doc_id": "ping", "bytes_b64": base64.b64encode(b"%PDF-FAKE").decode()}
        result = adapter.extract(payload)
    finally:
        adapter.close()

    assert result["tables"] == []
    assert call_counter["count"] == 2


def test_extract_auto_retries_next_field_on_server_error() -> None:
    call_counter = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        index = call_counter["count"]
        call_counter["count"] += 1
        content_type = request.headers.get("content-type", "")
        if index == 0:
            assert "application/json" in content_type
            return httpx.Response(422, json={"detail": "missing pdf"})
        if index == 1:
            assert "application/x-www-form-urlencoded" in content_type
            return httpx.Response(422, json={"detail": "still missing"})
        assert "multipart/form-data" in content_type
        body = request.content.decode("latin1")
        if index == 2:
            assert 'name="pdf"' in body
            return httpx.Response(500, json={"detail": "internal"})
        assert 'name="file"' in body
        return httpx.Response(200, json=_minimal_extract_response())

    client = httpx.Client(
        base_url="http://medparse.test",
        transport=httpx.MockTransport(handler),
        timeout=5.0,
    )
    adapter = MedparseHTTPAdapter(
        base_url="http://medparse.test",
        api_key=None,
        timeout=5.0,
        max_retries=1,
        retry_backoff=0.0,
        client=client,
    )

    try:
        payload = {"doc_id": "ping", "bytes_b64": base64.b64encode(b"%PDF-FAKE").decode()}
        result = adapter.extract(payload)
    finally:
        adapter.close()

    assert result["metadata"] == {}
    assert call_counter["count"] == 4


def test_extract_auto_form_fallback_before_multipart() -> None:
    call_counter = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        index = call_counter["count"]
        call_counter["count"] += 1
        content_type = request.headers.get("content-type", "")
        if index == 0:
            assert "application/json" in content_type
            return httpx.Response(422, json={"detail": "missing"})
        if index == 1:
            assert "application/x-www-form-urlencoded" in content_type
            body = request.content.decode("utf-8")
            assert "pdf=" in body and "doc_id=" in body
            return httpx.Response(200, json=_minimal_extract_response())
        pytest.fail("Multipart fallback should not occur when form succeeds")

    client = httpx.Client(
        base_url="http://medparse.test",
        transport=httpx.MockTransport(handler),
        timeout=5.0,
    )
    adapter = MedparseHTTPAdapter(
        base_url="http://medparse.test",
        api_key=None,
        timeout=5.0,
        max_retries=1,
        retry_backoff=0.0,
        client=client,
    )

    try:
        payload = {"doc_id": "ping", "bytes_b64": base64.b64encode(b"%PDF-FAKE").decode()}
        result = adapter.extract(payload)
    finally:
        adapter.close()

    assert result["metadata"] == {}
    assert call_counter["count"] == 2
