"""Backwards-compatible shim for table extraction utilities."""

from medparse.tables.extractor import extract_tables  # noqa: F401

__all__ = ["extract_tables"]
