"""Async client for the Medparse FastAPI sidecar."""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()


class MedparseError(RuntimeError):
    """Base exception raised for Medparse client failures."""


class MedparseAuthError(MedparseError):
    """Raised when Medparse returns an authentication error."""


class MedparseConfigError(MedparseError):
    """Raised when the Medparse client is misconfigured."""


@dataclass(slots=True)
class MedparseConfig:
    """Runtime configuration for the Medparse client."""

    base_url: str
    api_key: Optional[str] = None
    timeout: float = 30.0
    max_retries: int = 3
    retry_backoff: float = 1.0

    @classmethod
    def from_env(cls) -> "MedparseConfig":
        """Construct settings from environment variables."""

        base_url_raw = (
            os.getenv("MEDPARSE_BASE_URL")
            or os.getenv("MEDPARSE_HTTP_BASE_URL")
            or os.getenv("MEDPARSE_URL", "")
        )
        base_url = base_url_raw.strip().rstrip("/") if base_url_raw else ""
        if not base_url:
            raise MedparseConfigError("MEDPARSE_URL must be configured for Medparse client usage")

        def _read_float(name: str, default: float) -> float:
            value = os.getenv(name)
            if value is None or value.strip() == "":
                return default
            try:
                return float(value)
            except ValueError as exc:  # pragma: no cover - defensive configuration guard
                raise MedparseConfigError(f"Invalid float value for {name}: {value}") from exc

        def _read_int(name: str, default: int) -> int:
            value = os.getenv(name)
            if value is None or value.strip() == "":
                return default
            try:
                return int(value)
            except ValueError as exc:  # pragma: no cover - defensive configuration guard
                raise MedparseConfigError(f"Invalid integer value for {name}: {value}") from exc

        return cls(
            base_url=base_url,
            api_key=(os.getenv("MEDPARSE_API_KEY") or None),
            timeout=_read_float("MEDPARSE_TIMEOUT_SECONDS", 30.0),
            max_retries=_read_int("MEDPARSE_MAX_RETRIES", 3),
            retry_backoff=_read_float("MEDPARSE_RETRY_BACKOFF_SECONDS", 1.0),
        )


class MedparseClient:
    """Thin async wrapper around the Medparse API."""

    def __init__(
        self,
        config: MedparseConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        timeout = httpx.Timeout(config.timeout)
        self._client = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=timeout,
            transport=transport,
        )
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> "MedparseClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001 - FastAPI style signature
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    def _headers(self, extra: Mapping[str, str] | None = None) -> MutableMapping[str, str]:
        headers: MutableMapping[str, str] = {"Accept": "application/json"}
        if self.config.api_key:
            headers["X-API-Key"] = self.config.api_key
        if extra:
            headers.update(extra)
        return headers

    def _backoff_seconds(self, attempt: int) -> float:
        return self.config.retry_backoff * (2 ** max(0, attempt - 1))

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        headers = self._headers(kwargs.pop("headers", None))
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                response = await self._client.request(method, url, headers=headers, **kwargs)
                if response.status_code == 401:
                    raise MedparseAuthError("Medparse returned 401 (check MEDPARSE_API_KEY)")
                response.raise_for_status()
                return response
            except MedparseAuthError:
                raise
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if 500 <= status < 600 and attempt < self.config.max_retries:
                    await asyncio.sleep(self._backoff_seconds(attempt))
                    last_error = exc
                    continue
                raise MedparseError(
                    f"Medparse request failed with status {status}: {exc.response.text}"
                ) from exc
            except httpx.RequestError as exc:
                last_error = exc
                if attempt < self.config.max_retries:
                    await asyncio.sleep(self._backoff_seconds(attempt))
                    continue
                raise MedparseError(f"Medparse request error: {exc}") from exc
        if last_error:
            raise MedparseError(f"Medparse request failed after retries: {last_error}")
        raise MedparseError("Medparse request failed after retries")

    async def healthcheck(self) -> bool:
        response = await self._request("GET", "/healthz")
        try:
            payload = response.json()
        except ValueError as exc:
            raise MedparseError("Medparse health response was not JSON") from exc
        return bool(payload.get("ok"))

    async def version(self) -> dict[str, Any]:
        response = await self._request("GET", "/version")
        try:
            return response.json()
        except ValueError as exc:
            raise MedparseError("Medparse version response was not JSON") from exc

    async def link(self, text: str, *, top_k: int = 20) -> dict[str, Any]:
        if not text or not text.strip():
            raise ValueError("text must be a non-empty string")
        response = await self._request(
            "POST",
            "/link",
            json={"text": text, "top_k": top_k},
        )
        try:
            return response.json()
        except ValueError as exc:
            raise MedparseError("Medparse link response was not JSON") from exc

    async def extract(self, pdf_path: str | Path, *, doc_id: str) -> dict[str, Any]:
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF path does not exist: {path}")
        if not doc_id:
            raise ValueError("doc_id must be provided for Medparse extraction")
        pdf_bytes = path.read_bytes()
        files = {"pdf": (path.name, pdf_bytes, "application/pdf")}
        data = {"doc_id": doc_id}
        response = await self._request("POST", "/extract", files=files, data=data)
        try:
            return response.json()
        except ValueError as exc:
            raise MedparseError("Medparse extract response was not JSON") from exc


def get_client_from_env(*, transport: httpx.AsyncBaseTransport | None = None) -> MedparseClient:
    """Helper to construct a client using environment-driven configuration."""

    config = MedparseConfig.from_env()
    return MedparseClient(config, transport=transport)


__all__ = [
    "MedparseClient",
    "MedparseConfig",
    "MedparseError",
    "MedparseAuthError",
    "MedparseConfigError",
    "get_client_from_env",
]
