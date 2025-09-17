"""Tokenizer utilities used across the project."""
from __future__ import annotations

import tiktoken


def get_encoder():
    """Return the preferred encoding with a safe fallback."""
    try:
        return tiktoken.get_encoding("o200k_base")
    except Exception:
        return tiktoken.get_encoding("cl100k_base")
