"""Transport abstraction for Medparse integrations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Protocol, TypedDict

from ..config import AppConfig, TransportLiteral


class LinkRequest(TypedDict, total=False):
    text: Optional[str]
    doc_id: Optional[str]
    doc_type: Optional[str]


class LinkResponse(TypedDict):
    entities: List[Dict[str, Any]]
    spans: List[Dict[str, Any]]
    concepts: List[Dict[str, Any]]


class ExtractRequest(TypedDict, total=False):
    url: Optional[str]
    doc_id: Optional[str]
    bytes_b64: Optional[str]
    doc_type: Optional[str]


class ExtractResponse(TypedDict, total=False):
    metadata: Dict[str, Any]
    sections: List[Dict[str, Any]]
    statistics: List[Dict[str, Any]]
    relations: List[Dict[str, Any]]
    figures: List[Dict[str, Any]]
    tables: List[Dict[str, Any]]
    recommendations: List[Dict[str, Any]]
    validation: Dict[str, Any]
    quality: Dict[str, Any]


class MedparseTransport(Protocol):
    """Protocol the Medparse transport implementations must satisfy."""

    def health(self) -> bool:
        """Return ``True`` when the remote service reports healthy."""

    def link(self, req: LinkRequest) -> LinkResponse:
        """Call Medparse concept linking with the provided payload."""

    def extract(self, req: ExtractRequest) -> ExtractResponse:
        """Call Medparse extraction with the provided payload."""


class MedparseTransportError(RuntimeError):
    """Base exception for transport dispatch problems."""


class MedparseTransportDisabledError(MedparseTransportError):
    """Raised when MEDPARSE has been disabled via configuration."""


class MedparseTransportConfigError(MedparseTransportError):
    """Raised when the configuration is insufficient to build a transport."""


@dataclass(slots=True)
class _TransportFactories:
    http: Callable[[AppConfig], MedparseTransport]
    mcp: Callable[[AppConfig], MedparseTransport]


def get_medparse_transport(
    config: AppConfig | None = None,
    *,
    factories: _TransportFactories | None = None,
) -> MedparseTransport:
    """Return an instantiated Medparse transport based on configuration.

    Parameters
    ----------
    config:
        Optional pre-built :class:`AppConfig`. When omitted the environment is read.
    factories:
        Optional override used primarily for testing so callers can provide
        deterministic factories. When omitted the HTTP and MCP factories import
        and instantiate the production adapters.
    """

    cfg = config or AppConfig()

    if not cfg.MEDPARSE_ENABLED:
        raise MedparseTransportDisabledError("Medparse integration disabled (MEDPARSE_ENABLED=0).")

    resolved_factories = factories or _TransportFactories(
        http=_build_http_factory(),
        mcp=_build_mcp_factory(),
    )

    transport: TransportLiteral = cfg.MEDPARSE_TRANSPORT
    if transport == "http":
        return resolved_factories.http(cfg)
    if transport == "mcp":
        return resolved_factories.mcp(cfg)
    raise MedparseTransportConfigError(f"Unsupported MEDPARSE_TRANSPORT value: {transport}")


def _build_http_factory() -> Callable[[AppConfig], MedparseTransport]:
    from .medparse_http_adapter import MedparseHTTPAdapter

    def _factory(cfg: AppConfig) -> MedparseTransport:
        if not cfg.MEDPARSE_BASE_URL:
            raise MedparseTransportConfigError(
                "MEDPARSE_BASE_URL must be configured when MEDPARSE_TRANSPORT=http"
            )
        return MedparseHTTPAdapter(
            base_url=cfg.MEDPARSE_BASE_URL,
            api_key=cfg.MEDPARSE_API_KEY,
            timeout=cfg.MEDPARSE_TIMEOUT_SECONDS,
            max_retries=cfg.MEDPARSE_MAX_RETRIES,
            retry_backoff=cfg.MEDPARSE_RETRY_BACKOFF_SECONDS,
        )

    return _factory


def _build_mcp_factory() -> Callable[[AppConfig], MedparseTransport]:
    from .medparse_mcp_adapter import MedparseMCPAdapter

    def _factory(cfg: AppConfig) -> MedparseTransport:
        return MedparseMCPAdapter(timeout=cfg.MEDPARSE_TIMEOUT_SECONDS)

    return _factory


__all__ = [
    "LinkRequest",
    "LinkResponse",
    "ExtractRequest",
    "ExtractResponse",
    "MedparseTransport",
    "MedparseTransportError",
    "MedparseTransportDisabledError",
    "MedparseTransportConfigError",
    "get_medparse_transport",
]
