"""Second-pass patcher for small IFU leaflets to map intended use into indications."""

from __future__ import annotations

from typing import Dict

from medparse.schema.common import BaseDocument
from medparse.schema.ifu import IFUDocument

from ..types import SecondPassContext, SecondPassPatchResult

PATCH_NAME = "ifu_small_leaflet_map"


def _extract_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            return text.strip()
    return ""


def _strip_boilerplate(text: str) -> str:
    lines = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if "see contraindications" in lowered:
            continue
        if lowered.startswith("see ") and "contraindication" in lowered:
            continue
        lines.append(stripped)
    cleaned = "\n".join(lines).strip()
    if not cleaned and text.strip():
        cleaned = text.strip()
    return cleaned


def _ensure_second_pass_bucket(pipeline_info: Dict[str, object]) -> Dict[str, object]:
    bucket = pipeline_info.setdefault("second_pass", {})
    if not isinstance(bucket, dict):
        bucket = {}
        pipeline_info["second_pass"] = bucket
    return bucket


def apply_ifu_small_leaflet_map(document: BaseDocument, ctx: SecondPassContext) -> SecondPassPatchResult:
    if not isinstance(document, IFUDocument):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="doc_not_ifu")

    existing_text = _extract_text(document.indications_for_use)
    if existing_text:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="indications_present")

    intended_text = _extract_text(document.intended_use)
    if not intended_text:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_intended_use")

    cleaned = _strip_boilerplate(intended_text)
    if not cleaned:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="cleaned_empty")

    document.indications_for_use = {
        "text": cleaned,
        "provenance": "second_pass_smart_map",
    }

    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    if not isinstance(pipeline_info, dict):
        pipeline_info = {}

    second_pass_bucket = _ensure_second_pass_bucket(pipeline_info)

    patches_applied = second_pass_bucket.setdefault("patches_applied", [])
    if PATCH_NAME not in patches_applied:
        patches_applied.append(PATCH_NAME)

    applied_list = second_pass_bucket.setdefault("applied", [])
    if PATCH_NAME not in applied_list:
        applied_list.append(PATCH_NAME)

    reasons_list = second_pass_bucket.setdefault("reasons", [])
    if "indications_present" not in reasons_list:
        reasons_list.append("indications_present")

    modifications_bucket = second_pass_bucket.setdefault("modifications", {})
    modifications_bucket["indications_for_use"] = modifications_bucket.get("indications_for_use", 0) + 1

    meta = second_pass_bucket.setdefault("meta", {})
    meta["indications_for_use"] = meta.get("indications_for_use", 0) + 1

    pipeline_info["indications_fallback_provenance"] = "second_pass_smart_map"
    pipeline_info["second_pass"] = second_pass_bucket
    document.pipeline_info = pipeline_info

    return SecondPassPatchResult(
        name=PATCH_NAME,
        applied=True,
        modifications={"indications_for_use": 1},
        reasons=["indications_present"],
    )


__all__ = ["apply_ifu_small_leaflet_map"]
