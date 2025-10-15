"""Factory helpers for tool transports."""

from __future__ import annotations

import os

from .medparse_tool import MedparseTool
from ..adapters.medparse_http_adapter import MedparseHTTPAdapter
from ..adapters.medparse_mcp_adapter import MedparseMCPAdapter


def make_medparse_tool() -> MedparseTool:
    """Return a Medparse tool transport based on ``MEDPARSE_TRANSPORT``."""

    transport = os.getenv("MEDPARSE_TRANSPORT", "http").lower()
    if transport == "mcp":
        return MedparseMCPAdapter()
    return MedparseHTTPAdapter()
