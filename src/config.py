"""Application-wide configuration helpers."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, Optional

TransportLiteral = Literal["http", "mcp"]


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "off", "no"}


def _env_str(name: str, default: Optional[str]) -> Optional[str]:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip()
    return value or None


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid float value for {name!s}: {raw!r}") from exc


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid integer value for {name!s}: {raw!r}") from exc


@dataclass(slots=True)
class AppConfig:
    """Configuration sourced from environment variables."""

    MEDPARSE_ENABLED: bool
    MEDPARSE_TRANSPORT: TransportLiteral
    MEDPARSE_BASE_URL: Optional[str]
    MEDPARSE_TIMEOUT_SECONDS: float
    MEDPARSE_API_KEY: Optional[str]
    MEDPARSE_AUTH_HEADER_NAME: Optional[str]
    MEDPARSE_MAX_RETRIES: int
    MEDPARSE_RETRY_BACKOFF_SECONDS: float

    APP_USE_NEO4J: bool
    APP_USE_QDRANT: bool
    APP_SHOW_EVIDENCE: bool

    NEO4J_URI: Optional[str]
    NEO4J_USER: Optional[str]
    NEO4J_PASSWORD: Optional[str]
    NEO4J_DATABASE: Optional[str]

    QDRANT_HOST: str
    QDRANT_PORT: int
    QDRANT_URL: str
    QDRANT_API_KEY: Optional[str]
    QDRANT_COLLECTION_PREFIX: str
    QDRANT_COLLECTION_SECTIONS: str
    QDRANT_COLLECTION_RECS: str
    QDRANT_COLLECTION_FIGTABS: str

    def __init__(self) -> None:
        self.MEDPARSE_ENABLED = _env_bool("MEDPARSE_ENABLED", True)

        transport = (_env_str("MEDPARSE_TRANSPORT", "http") or "http").lower()
        if transport not in {"http", "mcp"}:
            raise ValueError(
                "MEDPARSE_TRANSPORT must be one of {'http', 'mcp'} (case-insensitive)"
            )
        self.MEDPARSE_TRANSPORT = transport  # type: ignore[assignment]

        base_url = _env_str("MEDPARSE_BASE_URL", None) or _env_str(
            "MEDPARSE_HTTP_BASE_URL", "http://127.0.0.1:8099"
        )
        self.MEDPARSE_BASE_URL = base_url.rstrip("/") if base_url else None
        self.MEDPARSE_TIMEOUT_SECONDS = _env_float("MEDPARSE_TIMEOUT_SECONDS", 30.0)
        self.MEDPARSE_API_KEY = _env_str("MEDPARSE_API_KEY", None)
        self.MEDPARSE_AUTH_HEADER_NAME = _env_str("MEDPARSE_AUTH_HEADER_NAME", None)
        self.MEDPARSE_MAX_RETRIES = _env_int("MEDPARSE_MAX_RETRIES", 3)
        self.MEDPARSE_RETRY_BACKOFF_SECONDS = _env_float("MEDPARSE_RETRY_BACKOFF_SECONDS", 1.0)

        self.APP_USE_NEO4J = _env_bool("APP_USE_NEO4J", True)
        self.APP_USE_QDRANT = _env_bool("APP_USE_QDRANT", True)
        self.APP_SHOW_EVIDENCE = _env_bool("APP_SHOW_EVIDENCE", False)

        self.NEO4J_URI = _env_str("NEO4J_URI", "neo4j://localhost:7687")
        self.NEO4J_USER = _env_str("NEO4J_USER", "neo4j")
        self.NEO4J_PASSWORD = _env_str("NEO4J_PASSWORD", None)
        self.NEO4J_DATABASE = _env_str("NEO4J_DATABASE", None)

        self.QDRANT_HOST = _env_str("QDRANT_HOST", "localhost") or "localhost"
        self.QDRANT_PORT = _env_int("QDRANT_PORT", 6333)
        self.QDRANT_URL = _env_str("QDRANT_URL", f"http://{self.QDRANT_HOST}:{self.QDRANT_PORT}") or (
            f"http://{self.QDRANT_HOST}:{self.QDRANT_PORT}"
        )
        self.QDRANT_API_KEY = _env_str("QDRANT_API_KEY", None)
        prefix = _env_str("QDRANT_COLLECTION_PREFIX", "ip") or "ip"
        self.QDRANT_COLLECTION_PREFIX = prefix
        self.QDRANT_COLLECTION_SECTIONS = f"{prefix}_sections"
        self.QDRANT_COLLECTION_RECS = f"{prefix}_recs"
        self.QDRANT_COLLECTION_FIGTABS = f"{prefix}_figtabs"


__all__ = ["AppConfig", "TransportLiteral"]
