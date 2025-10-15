"""MCP transport implementation for Medparse."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Protocol

from .medparse_transport import (
    ExtractRequest,
    ExtractResponse,
    LinkRequest,
    LinkResponse,
    MedparseTransport,
    MedparseTransportError,
)


class _MCPClient(Protocol):
    """Minimal protocol for the MCP client used by the transport."""

    def health(self, *, timeout: float) -> Mapping[str, Any]:
        ...

    def link(self, payload: Mapping[str, Any], *, timeout: float) -> Mapping[str, Any]:
        ...

    def extract(self, payload: Mapping[str, Any], *, timeout: float) -> Mapping[str, Any]:
        ...


class MedparseMCPAdapter(MedparseTransport):
    """Adapter that routes Medparse calls through the MCP bridge."""

    def __init__(self, *, client: Optional[_MCPClient] = None, timeout: float = 30.0) -> None:
        self._timeout = timeout
        self._client = client or self._build_default_client()

    def _build_default_client(self) -> _MCPClient:
        try:
            from ip_mcp_client import MedparseMCPClient  # type: ignore[import]
        except ModuleNotFoundError as exc:
            raise MedparseTransportError(
                "MCP transport requires the ip-mcp-integration client package. "
                "Install it or set MEDPARSE_TRANSPORT=http."
            ) from exc

        return MedparseMCPClient(timeout=self._timeout)

    def health(self) -> bool:
        try:
            result = self._client.health(timeout=self._timeout)
        except Exception as exc:  # pragma: no cover - defensive guard
            raise MedparseTransportError(
                "Medparse MCP transport failed health check. Ensure the MCP server is running or "
                "switch MEDPARSE_TRANSPORT=http."
            ) from exc
        status = result.get("status") if isinstance(result, Mapping) else None
        if isinstance(status, str):
            return status.lower() == "ok"
        return bool(result)

    def link(self, req: LinkRequest) -> LinkResponse:
        payload = {k: v for k, v in req.items() if v is not None}
        if not payload:
            raise ValueError("link request must include text or doc_id for MCP transport.")
        try:
            response = self._client.link(payload, timeout=self._timeout)
        except Exception as exc:
            raise MedparseTransportError(
                "Medparse MCP transport link() call failed. Verify the MCP server is reachable "
                "or switch MEDPARSE_TRANSPORT=http."
            ) from exc
        return _coerce_link_response(response)

    def extract(self, req: ExtractRequest) -> ExtractResponse:
        payload = {k: v for k, v in req.items() if v is not None}
        if not payload:
            raise ValueError("extract request must include url, doc_id, or bytes_b64 for MCP transport.")
        try:
            response = self._client.extract(payload, timeout=self._timeout)
        except Exception as exc:
            raise MedparseTransportError(
                "Medparse MCP transport extract() call failed. Ensure the MCP server is available "
                "or switch MEDPARSE_TRANSPORT=http."
            ) from exc
        return _coerce_extract_response(response)


def _coerce_link_response(response: Any) -> LinkResponse:
    if not isinstance(response, Mapping):
        raise MedparseTransportError("MCP link response must be a mapping.")
    entities = response.get("entities") or []
    spans = response.get("spans") or []
    concepts = response.get("concepts") or []
    if not isinstance(entities, list) or not isinstance(spans, list) or not isinstance(concepts, list):
        raise MedparseTransportError("MCP link response missing expected list fields.")
    return LinkResponse(entities=list(entities), spans=list(spans), concepts=list(concepts))


def _coerce_extract_response(response: Any) -> ExtractResponse:
    if not isinstance(response, Mapping):
        raise MedparseTransportError("MCP extract response must be a mapping.")

    def _as_list(name: str) -> list[dict]:
        value = response.get(name) or []
        if not isinstance(value, list):
            raise MedparseTransportError(f"MCP extract response field '{name}' must be a list.")
        return list(value)

    metadata = response.get("metadata")
    if not isinstance(metadata, Mapping):
        metadata = {}

    result: ExtractResponse = ExtractResponse(
        metadata=dict(metadata),
        sections=_as_list("sections"),
        statistics=_as_list("statistics"),
        relations=_as_list("relations"),
        figures=_as_list("figures"),
        tables=_as_list("tables"),
    )

    recommendations = response.get("recommendations")
    if recommendations is not None:
        if not isinstance(recommendations, list):
            raise MedparseTransportError("MCP extract response field 'recommendations' must be a list.")
        result["recommendations"] = list(recommendations)

    for optional_key in ("quality", "validation"):
        payload_value = response.get(optional_key)
        if payload_value is None:
            continue
        if not isinstance(payload_value, Mapping):
            raise MedparseTransportError(f"MCP extract response field '{optional_key}' must be an object.")
        result[optional_key] = dict(payload_value)

    return result


__all__ = ["MedparseMCPAdapter"]
