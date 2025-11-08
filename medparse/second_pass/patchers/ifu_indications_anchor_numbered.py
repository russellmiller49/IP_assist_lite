"""Second-pass patcher that lifts numbered indications headings for IFUs."""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from medparse.schema.common import BaseDocument
from medparse.schema.ifu import IFUDocument

from ..types import SecondPassContext, SecondPassPatchResult

PATCH_NAME = "ifu_indications_anchor_numbered"

HEADING_RE = re.compile(r"^(?:\d+\.){1,3}\s*indications?\s+for\s+use\b.*", re.IGNORECASE)
NUMBERED_HEADING_RE = re.compile(r"^(?:\d+\.){1,3}\s+\S+", re.IGNORECASE)
INTENDED_USE_RE = re.compile(r"^(?:\d+\.){1,3}\s*intended\s+use\b|^intended\s+use\b", re.IGNORECASE)
DOT_LEADER_RE = re.compile(r"[.·…]{2,}")
CAPTION_RE = re.compile(r"^(figure|table|image|video)\\b", re.IGNORECASE)
SENTENCE_SPLIT_RE = re.compile(r"[.!?]+\\s+")


def _ordered_entries(paragraph_store: Dict[str, Dict[str, object]]) -> List[Dict[str, object]]:
    ordered: List[Tuple[int, int, Dict[str, object]]] = []
    for hash_id, entry in paragraph_store.items():
        text = entry.get("text")
        page = entry.get("page")
        if not isinstance(text, str) or not isinstance(page, int):
            continue
        orders = entry.get("order") or []
        order_index = 10**6
        if isinstance(orders, (list, tuple)):
            for raw in orders:
                try:
                    candidate = int(raw)
                except (TypeError, ValueError):
                    continue
                order_index = min(order_index, candidate)
        ordered.append((page, order_index, {**entry, "hash": hash_id}))
    ordered.sort(key=lambda item: (item[0], item[1]))
    return [entry for _, _, entry in ordered]


def _clean_line(text: str) -> str:
    cleaned = text.strip()
    cleaned = DOT_LEADER_RE.sub(" ", cleaned)
    cleaned = re.sub(r"-\\s+", "", cleaned)
    cleaned = re.sub(r"\\s+", " ", cleaned)
    return cleaned.strip(" .-")


def _looks_like_toc(line: str) -> bool:
    return bool(re.search(r"[.·…]{2,}\\s*\\d+$", line))


def _looks_like_caption(line: str) -> bool:
    return bool(CAPTION_RE.match(line))


def _extract_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            return text.strip()
    return ""


def _collect_body_lines(
    entries: List[Dict[str, object]],
    start_idx: int,
    start_line_idx: int,
    toc_mask: set[int],
) -> Tuple[List[str], List[str]]:
    collected: List[str] = []
    evidence_ids: List[str] = []
    for entry_idx in range(start_idx, len(entries)):
        entry = entries[entry_idx]
        page = entry.get("page")
        if isinstance(page, int) and page in toc_mask:
            continue
        text = entry.get("text")
        if not isinstance(text, str):
            continue
        lines = text.splitlines()
        line_start = start_line_idx + 1 if entry_idx == start_idx else 0
        for raw_line in lines[line_start:]:
            stripped = raw_line.strip()
            if not stripped:
                continue
            cleaned = _clean_line(stripped)
            if not cleaned or _looks_like_toc(cleaned):
                continue
            if NUMBERED_HEADING_RE.match(cleaned) or INTENDED_USE_RE.match(cleaned):
                return collected, evidence_ids
            if _looks_like_caption(cleaned):
                continue
            collected.append(cleaned)
            hash_id = entry.get("hash")
            if hash_id is not None:
                hash_str = str(hash_id)
                if hash_str not in evidence_ids:
                    evidence_ids.append(hash_str)
        if len(collected) >= 12:
            break
    return collected, evidence_ids


def _apply_indications_payload(document: IFUDocument, payload: Dict[str, object]) -> None:
    document.indications_for_use = payload
    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    if not isinstance(pipeline_info, dict):
        pipeline_info = {}
    pipeline_info["indications_provenance"] = payload.get("provenance")
    document.pipeline_info = pipeline_info


def apply_ifu_indications_anchor_numbered(document: BaseDocument, ctx: SecondPassContext) -> SecondPassPatchResult:
    if not isinstance(document, IFUDocument):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="doc_not_ifu")

    existing = _extract_text(document.indications_for_use)
    if existing:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="indications_present")

    paragraph_store = ctx.paragraph_store or {}
    ordered_entries = _ordered_entries(paragraph_store)
    if not ordered_entries:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_paragraphs")

    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    if not isinstance(pipeline_info, dict):
        pipeline_info = {}
    toc_info = pipeline_info.get("toc_guard") if isinstance(pipeline_info.get("toc_guard"), dict) else {}
    toc_mask_values = toc_info.get("toc_mask") if isinstance(toc_info, dict) else []
    toc_mask = {int(page) for page in toc_mask_values} if toc_mask_values else set()

    extracted_text = None
    evidence_ids: List[str] = []

    for entry_idx, entry in enumerate(ordered_entries):
        page = entry.get("page")
        if isinstance(page, int) and page in toc_mask:
            continue
        text = entry.get("text")
        if not isinstance(text, str):
            continue
        lines = text.splitlines()
        for line_idx, raw_line in enumerate(lines):
            cleaned = raw_line.strip()
            if not cleaned:
                continue
            if HEADING_RE.match(cleaned):
                body_lines, evidence_ids = _collect_body_lines(ordered_entries, entry_idx, line_idx, toc_mask)
                if len(body_lines) >= 2:
                    extracted_text = " ".join(body_lines)
                    extracted_text = re.sub(r"\\s+", " ", extracted_text).strip()
                break
        if extracted_text:
            break

    modifications: Dict[str, int] = {}
    reasons: List[str] = []

    if extracted_text:
        payload: Dict[str, object] = {
            "text": extracted_text,
            "provenance": "second_pass:indications_numbered",
        }
        if evidence_ids:
            payload["evidence_ids"] = evidence_ids
        _apply_indications_payload(document, payload)
        modifications["indications_for_use"] = 1
        reasons.append("indications_numbered_heading")
    else:
        manufacturer = (document.manufacturer or "").lower()
        if "intuitive" in manufacturer:
            intended = _extract_text(document.intended_use)
            if intended:
                sentences = [segment.strip() for segment in SENTENCE_SPLIT_RE.split(intended) if segment.strip()]
                if sentences and len(sentences) <= 3:
                    payload = {
                        "text": intended.strip(),
                        "provenance": "second_pass:intended_to_indications",
                    }
                    _apply_indications_payload(document, payload)
                    modifications["indications_for_use"] = 1
                    reasons.append("fallback_intended_to_indications")

    if not modifications:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_heading_detected")

    second_pass_bucket = pipeline_info.setdefault("second_pass", {})
    if not isinstance(second_pass_bucket, dict):
        second_pass_bucket = {}
        pipeline_info["second_pass"] = second_pass_bucket

    patches_applied = second_pass_bucket.setdefault("patches_applied", [])
    if PATCH_NAME not in patches_applied:
        patches_applied.append(PATCH_NAME)

    applied_list = second_pass_bucket.setdefault("applied", [])
    if PATCH_NAME not in applied_list:
        applied_list.append(PATCH_NAME)

    reasons_list = second_pass_bucket.setdefault("reasons", [])
    for reason in reasons:
        if reason not in reasons_list:
            reasons_list.append(reason)

    modifications_bucket = second_pass_bucket.setdefault("modifications", {})
    modifications_bucket["indications_for_use"] = modifications_bucket.get("indications_for_use", 0) + 1

    document.pipeline_info = pipeline_info

    return SecondPassPatchResult(
        name=PATCH_NAME,
        applied=True,
        modifications=modifications,
        reasons=reasons,
    )


__all__ = ["apply_ifu_indications_anchor_numbered"]
