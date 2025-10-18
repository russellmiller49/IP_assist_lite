"""Factory helpers for tool transports."""

from __future__ import annotations

import os

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
    return MedparseHTTPAdapter(
        base_url=cfg.MEDPARSE_BASE_URL or "http://127.0.0.1:8099",
        api_key=cfg.MEDPARSE_API_KEY,
        auth_header_name=cfg.MEDPARSE_AUTH_HEADER_NAME,
        timeout=cfg.MEDPARSE_TIMEOUT_SECONDS,
        max_retries=cfg.MEDPARSE_MAX_RETRIES,
        retry_backoff=cfg.MEDPARSE_RETRY_BACKOFF_SECONDS,
    )
