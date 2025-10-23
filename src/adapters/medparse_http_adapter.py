"""HTTP implementation of the Medparse transport."""
from __future__ import annotations

import base64
import binascii
import time
from typing import Any, Dict, Mapping, Optional, cast

import httpx

from .medparse_transport import (
    ExtractRequest,
    ExtractResponse,
    LinkRequest,
    LinkResponse,
    MedparseTransport,
    MedparseTransportError,
)


def _normalize_timeout(value: float | httpx.Timeout | None) -> httpx.Timeout:
    if isinstance(value, httpx.Timeout):
        return value
    if value is None:
        raise ValueError("timeout must be provided for Medparse HTTP transport")
    return httpx.Timeout(value)


class MedparseHTTPAdapter(MedparseTransport):
    """HTTP transport that talks directly to the Medparse FastAPI sidecar."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: Optional[str],
        auth_header_name: Optional[str] = None,
        timeout: float | httpx.Timeout | None,
        max_retries: int,
        retry_backoff: float,
        client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
        extract_mode: str = "auto",
        multipart_field: str = "pdf",
    ) -> None:
        if not base_url:
            raise ValueError("base_url must be provided for Medparse HTTP transport")

        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._auth_header_name = (auth_header_name or "X-API-Key").strip() or "X-API-Key"
        self._timeout = _normalize_timeout(timeout)
        self._max_retries = max(1, max_retries)
        self._retry_backoff = max(0.0, retry_backoff)
        self._extract_mode = (extract_mode or "auto").lower()
        if self._extract_mode not in {"auto", "json", "multipart"}:
            raise ValueError("extract_mode must be one of {'auto', 'json', 'multipart'}")
        self._multipart_field = (multipart_field or "pdf").strip() or "pdf"
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=self._base_url,
            timeout=self._timeout,
            transport=transport,
        )
        if self._owns_client:
            try:
                self.preflight()
            except Exception:
                self._client.close()
                raise

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> "MedparseHTTPAdapter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001 - context manager protocol
        self.close()

    def preflight(self) -> bool:
        """Execute a readiness probe before first request."""
        return self.health()

    def _headers(self, extra: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
        headers: Dict[str, str] = {"Accept": "application/json"}
        if self._api_key:
            header_name = self._auth_header_name or "X-API-Key"
            if header_name.lower() == "x-api-key":
                headers[header_name] = self._api_key
            else:
                headers[header_name] = f"Bearer {self._api_key}"
        if extra:
            headers.update(dict(extra))
        return headers

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = self._headers(kwargs.pop("headers", None))

        for attempt in range(1, self._max_retries + 1):
            try:
                response = self._client.request(method, path, headers=headers, **kwargs)
                if response.status_code == 401:
                    raise MedparseTransportError("Medparse HTTP transport received 401 (check API key)")
                if response.status_code >= 500 and attempt < self._max_retries:
                    self._sleep(attempt)
                    continue
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code >= 500 and attempt < self._max_retries:
                    self._sleep(attempt)
                    continue
                raise MedparseTransportError(
                    f"Medparse HTTP request failed with status {exc.response.status_code}: {exc.response.text}"
                ) from exc
            except httpx.RequestError as exc:
                if attempt < self._max_retries:
                    self._sleep(attempt)
                    continue
                raise MedparseTransportError(f"Medparse HTTP request error: {exc}") from exc

        raise MedparseTransportError("Medparse HTTP request exhausted retry attempts")

    def _sleep(self, attempt: int) -> None:
        delay = self._retry_backoff * (2 ** max(0, attempt - 1))
        if delay > 0:
            time.sleep(delay)

    def health(self) -> bool:
        response = self._request("GET", "/healthz")
        if response.headers.get("content-type", "").startswith("application/json"):
            try:
                payload = response.json()
            except ValueError as exc:
                raise MedparseTransportError("Medparse /healthz response was not JSON") from exc
            return bool(payload.get("ok", True))
        return response.status_code == 200

    def link(self, req: LinkRequest) -> LinkResponse:
        payload = _filter_payload(req)
        if not payload:
            raise ValueError("link request must include at least one of text or doc_id")
        response = self._request("POST", "/link", json=payload)
        try:
            data = response.json()
        except ValueError as exc:
            raise MedparseTransportError("Medparse /link response was not JSON") from exc
        return _ensure_link_response(data)

    def extract(self, req: ExtractRequest) -> ExtractResponse:
        doc_id = req.get("doc_id")
        bytes_b64 = req.get("bytes_b64")
        url = req.get("url")
        doc_type = req.get("doc_type")

        def _build_json_payload() -> Dict[str, Any]:
            payload: Dict[str, Any] = {}
            if doc_id:
                payload["doc_id"] = doc_id
            if bytes_b64:
                payload["pdf"] = bytes_b64
            if url:
                payload["url"] = url
            if doc_type:
                payload["doc_type"] = doc_type
            if not payload:
                raise ValueError("extract request requires url, doc_id, or bytes_b64")
            return payload

        def _json_attempt() -> ExtractResponse:
            payload = _build_json_payload()
            try:
                response = self._request("POST", "/extract", json=payload)
            except MedparseTransportError as exc:  # pragma: no cover - exercised via fallback paths
                keys = ", ".join(sorted(payload.keys())) or "<none>"
                raise MedparseTransportError(
                    f"{exc} (Medparse /extract payload keys: {keys})"
                ) from exc
            try:
                data = response.json()
            except ValueError as exc:
                raise MedparseTransportError("Medparse /extract response was not JSON") from exc
            return _ensure_extract_response(cast(Dict[str, Any], data))

        def _form_attempt() -> ExtractResponse:
            payload = _build_json_payload()
            try:
                response = self._request("POST", "/extract", data=payload)
            except MedparseTransportError as exc:  # pragma: no cover - defensive fallback
                keys = ", ".join(sorted(payload.keys())) or "<none>"
                raise MedparseTransportError(
                    f"{exc} (Medparse /extract form payload keys: {keys})"
                ) from exc
            try:
                data = response.json()
            except ValueError as exc:
                raise MedparseTransportError("Medparse /extract response was not JSON") from exc
            return _ensure_extract_response(cast(Dict[str, Any], data))

        def _multipart_attempt(field_name: str) -> ExtractResponse:
            if not bytes_b64:
                raise MedparseTransportError("multipart extract requires bytes_b64 in the request payload")
            try:
                pdf_bytes = base64.b64decode(bytes_b64.encode("utf-8"))
            except (ValueError, binascii.Error) as exc:
                raise MedparseTransportError("Invalid base64 content provided for bytes_b64") from exc

            files = {
                field_name: ("document.pdf", pdf_bytes, "application/pdf"),
            }
            data: Dict[str, Any] = {}
            if doc_id:
                data["doc_id"] = doc_id
            if doc_type:
                data["doc_type"] = doc_type

            response = self._request("POST", "/extract", files=files, data=data)
            try:
                data_json = response.json()
            except ValueError as exc:
                raise MedparseTransportError("Medparse /extract response was not JSON") from exc
            return _ensure_extract_response(cast(Dict[str, Any], data_json))

        def _is_unprocessable(exc: MedparseTransportError) -> bool:
            cause = exc
            while cause is not None:
                inner = getattr(cause, "__cause__", None)
                if isinstance(inner, httpx.HTTPStatusError):
                    return inner.response.status_code == 422
                if inner is None:
                    break
                if isinstance(inner, MedparseTransportError):
                    cause = inner
                else:
                    cause = getattr(inner, "__cause__", None)
            return False

        def _multipart_sequence() -> ExtractResponse:
            field_order: list[str] = []
            for candidate in (self._multipart_field, "pdf", "file"):
                if candidate and candidate not in field_order:
                    field_order.append(candidate)

            last_error: MedparseTransportError | None = None
            for index, field_name in enumerate(field_order):
                try:
                    return _multipart_attempt(field_name)
                except MedparseTransportError as exc:
                    last_error = exc
                    # Base64 issues or exhausted candidates should surface immediately.
                    message = str(exc)
                    if "Invalid base64" in message or "requires bytes_b64" in message:
                        raise
                    # Continue to next field when available; otherwise propagate.
                    if index == len(field_order) - 1:
                        raise
                    continue

            if last_error is not None:
                raise last_error
            raise MedparseTransportError("Medparse multipart attempts exhausted")

        mode = self._extract_mode
        if mode == "json":
            return _json_attempt()
        if mode == "multipart":
            return _multipart_sequence()

        # auto mode
        try:
            return _json_attempt()
        except MedparseTransportError as exc:
            if not _is_unprocessable(exc):
                raise
            try:
                return _form_attempt()
            except MedparseTransportError as exc_form:
                if not _is_unprocessable(exc_form):
                    raise
            return _multipart_sequence()


def _filter_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _ensure_link_response(payload: Any) -> LinkResponse:
    if not isinstance(payload, dict):
        raise MedparseTransportError("Medparse /link response must be a JSON object.")
    entities = payload.get("entities") or []
    spans = payload.get("spans") or []
    concepts = payload.get("concepts") or []
    if not isinstance(entities, list) or not isinstance(spans, list) or not isinstance(concepts, list):
        raise MedparseTransportError("Medparse /link response missing expected list fields.")
    return LinkResponse(entities=list(entities), spans=list(spans), concepts=list(concepts))


def _ensure_extract_response(payload: Any) -> ExtractResponse:
    if not isinstance(payload, dict):
        raise MedparseTransportError("Medparse /extract response must be a JSON object.")

    def _as_list(key: str) -> list[Dict[str, Any]]:
        value = payload.get(key) or []
        if not isinstance(value, list):
            raise MedparseTransportError(f"Medparse /extract response field '{key}' must be a list.")
        return list(value)

    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    result: ExtractResponse = ExtractResponse(
        metadata=dict(metadata),
        sections=_as_list("sections"),
        statistics=_as_list("statistics"),
        relations=_as_list("relations"),
        figures=_as_list("figures"),
        tables=_as_list("tables"),
    )

    for optional_key in ("recommendations", "quality", "validation"):
        if optional_key in payload:
            value = payload.get(optional_key)
            if optional_key == "recommendations":
                if value is None:
                    continue
                if not isinstance(value, list):
                    raise MedparseTransportError(
                        f"Medparse /extract response field '{optional_key}' must be a list."
                    )
                result["recommendations"] = list(value)
            else:
                if value is None:
                    continue
                if not isinstance(value, dict):
                    raise MedparseTransportError(
                        f"Medparse /extract response field '{optional_key}' must be an object."
                    )
                result[optional_key] = dict(value)

    return result


__all__ = ["MedparseHTTPAdapter"]
