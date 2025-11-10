"""Helpers for tracking IFU revision metadata."""

from __future__ import annotations

from typing import Dict, Any

from medparse.schema.ifu import IFUDocument


def sync_revision_status(document: IFUDocument) -> None:
    """Ensure revision status/provenance fields are recorded on the document."""

    pipeline_info: Dict[str, Any] = getattr(document, "pipeline_info", {}) or {}
    if not isinstance(pipeline_info, dict):
        pipeline_info = {}
        document.pipeline_info = pipeline_info

    front_meta = pipeline_info.get("front_matter_meta")
    if not isinstance(front_meta, dict):
        front_meta = {}
        pipeline_info["front_matter_meta"] = front_meta

    revision_value = getattr(document, "revision", None)
    sanitized_flag = bool(pipeline_info.get("front_matter_revision_sanitized"))

    if sanitized_flag and not revision_value:
        status = "sanitized_unusable"
        provenance = "sanitized"
    elif revision_value:
        status = "extracted"
        provenance = "extracted"
    else:
        status = "missing"
        provenance = "missing"

    pipeline_info["revision_status"] = status
    front_meta["revision_status"] = status
    front_meta["revision_provenance"] = provenance


__all__ = ["sync_revision_status"]
