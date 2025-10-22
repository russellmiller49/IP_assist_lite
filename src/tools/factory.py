"""Factory helpers for tool transports."""

from __future__ import annotations

import os

import httpx

from config import AppConfig

from adapters.medparse_http_adapter import MedparseHTTPAdapter
from adapters.medparse_mcp_adapter import MedparseMCPAdapter
from .medparse_tool import MedparseTool


def make_medparse_tool() -> MedparseTool:
    """Return a Medparse tool transport based on ``MEDPARSE_TRANSPORT``."""

    cfg = AppConfig()
    transport = os.getenv("MEDPARSE_TRANSPORT", cfg.MEDPARSE_TRANSPORT).lower()
    if transport == "mcp":
        return MedparseMCPAdapter(timeout=cfg.MEDPARSE_TIMEOUT_SECONDS)
    base_url = cfg.MEDPARSE_BASE or cfg.MEDPARSE_BASE_URL or "http://127.0.0.1:8099"
    timeout = httpx.Timeout(
        timeout=cfg.MEDPARSE_TIMEOUT_SECONDS,
        connect=cfg.MEDPARSE_TIMEOUT_CONNECT_SECONDS,
        read=cfg.MEDPARSE_TIMEOUT_READ_SECONDS,
        write=cfg.MEDPARSE_TIMEOUT_WRITE_SECONDS,
        pool=cfg.MEDPARSE_TIMEOUT_POOL_SECONDS,
    )
    return MedparseHTTPAdapter(
        base_url=base_url,
        api_key=cfg.MEDPARSE_API_KEY,
        auth_header_name=cfg.MEDPARSE_AUTH_HEADER_NAME,
        timeout=timeout,
        max_retries=cfg.MEDPARSE_MAX_RETRIES,
        retry_backoff=cfg.MEDPARSE_RETRY_BACKOFF_SECONDS,
        extract_mode=cfg.MEDPARSE_EXTRACT_MODE,
        multipart_field=cfg.MEDPARSE_MULTIPART_FIELD,
    )
