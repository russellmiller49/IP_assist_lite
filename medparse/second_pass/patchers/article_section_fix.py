"""Second-pass patcher that reconstructs pseudo sections for sparse articles."""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Dict, List, Optional, Set, Tuple

from medparse.schema.article import ArticleDocument
from medparse.schema.common import BaseDocument

from ..types import SecondPassContext, SecondPassPatchResult

PATCH_NAME = "sectionizer_salvage"

SECTION_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "introduction": (
        "introduction",
        "background",
        "objective",
        "aim",
        "purpose",
        "rationale",
    ),
    "methods": (
        "methods",
        "materials and methods",
        "study design",
        "patients and methods",
        "we conducted",
        "we performed",
        "procedure",
        "protocol",
    ),
    "results": (
        "results",
        "findings",
        "outcomes",
        "observations",
        "measurements",
    ),
    "discussion": (
        "discussion",
        "conclusion",
        "conclusions",
        "interpretation",
        "summary",
        "implications",
    ),
}

HEADING_RE = re.compile(r"^\s*(?P<label>[A-Z][A-Za-z\s/-]{3,})[:\-–]?\s*$")
CAPTION_PREFIX_RE = re.compile(r"^(fig(?:ure)?|table|supplementary|video|movie)", re.IGNORECASE)
CITATION_TOKEN_RE = re.compile(r"^(?:\(?\d+(?:,\d+)*\)?|\[\d+(?:,\d+)*\])$")
URL_TOKEN_RE = re.compile(r"(?:https?://|doi\b)", re.IGNORECASE)


def _ordered_paragraphs(paragraph_store: Dict[str, Dict[str, object]]) -> List[Tuple[Optional[int], str]]:
    ordered: List[Tuple[int, Optional[int], str]] = []
    for entry in paragraph_store.values():
        text = entry.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        orders = entry.get("order") or []
        try:
            order_index = min(int(value) for value in orders) if orders else 10**6
        except (TypeError, ValueError):
            order_index = 10**6
        page = entry.get("page") if isinstance(entry.get("page"), int) else None
        ordered.append((order_index, page, text.strip()))
    ordered.sort(key=lambda item: item[0])
    return [(page, text) for _, page, text in ordered]


def _match_section_label(text: str) -> Optional[str]:
    lowered = text.lower()
    heading_match = HEADING_RE.match(text)
    candidate_line = heading_match.group("label").lower() if heading_match else lowered

    for label, keywords in SECTION_KEYWORDS.items():
        for keyword in keywords:
            if candidate_line.startswith(keyword):
                return label
    return None


def _should_drop_section(text: str) -> bool:
    tokens = re.findall(r"[A-Za-z0-9\[\]\(\)\.\-/:]+", text or "")
    if len(tokens) < 10:
        return False
    flagged = 0
    for token in tokens:
        token_lower = token.lower()
        if CAPTION_PREFIX_RE.match(token_lower):
            flagged += 1
            continue
        if CITATION_TOKEN_RE.match(token):
            flagged += 1
            continue
        if URL_TOKEN_RE.search(token_lower):
            flagged += 1
            continue
    return flagged / max(len(tokens), 1) >= 0.40


def apply_sectionizer_salvage(document: BaseDocument, ctx: SecondPassContext) -> SecondPassPatchResult:
    if not isinstance(document, ArticleDocument):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="doc_not_article")

    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    second_pass_bucket = pipeline_info.setdefault("second_pass", {})
    applied = second_pass_bucket.get("patches_applied") or []
    if isinstance(applied, list) and PATCH_NAME in applied:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="already_applied")

    subtype = (getattr(document, "doc_subtype", "") or "").lower()
    min_sections_default = 4 if subtype == "research" else 3
    min_sections = int(ctx.config.get("sectionizer", {}).get("min_sections_research", min_sections_default)) if isinstance(ctx.config, dict) else min_sections_default
    min_sections = max(2, min_sections)

    existing_sections = getattr(document, "sections", {}) or {}
    existing_count = len(existing_sections)

    triggers = [
        issue for issue in ctx.validation_issues if "section" in issue.message.lower()
    ]
    if ctx.mode == "auto" and not triggers and existing_count >= min_sections:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="auto_mode_no_trigger")

    if existing_count >= min_sections and ctx.mode != "always":
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="sections_meet_threshold")

    ordered_entries = _ordered_paragraphs(ctx.paragraph_store)
    if not ordered_entries:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_paragraphs")
    ordered_texts = [paragraph for _, paragraph in ordered_entries]

    sections: "OrderedDict[str, List[str]]" = OrderedDict((label, []) for label in SECTION_KEYWORDS.keys())
    current_label = "introduction"

    heading_last_page: Dict[str, int] = {}
    seen_heading_hashes: Set[str] = set()

    for page, paragraph in ordered_entries:
        if not paragraph:
            continue
        label = _match_section_label(paragraph)
        if label:
            stripped = paragraph.strip()
            words = stripped.split()
            if stripped.endswith(":") or len(words) <= 3:
                continue  # treat short heading-like paragraphs as anchors only
            heading_signature = stripped.lower()
            if heading_signature in seen_heading_hashes:
                continue
            last_page = heading_last_page.get(heading_signature)
            if last_page is not None and page is not None and abs(page - last_page) <= 2:
                continue
            seen_heading_hashes.add(heading_signature)
            if page is not None:
                heading_last_page[heading_signature] = page
            current_label = label
        sections.setdefault(current_label, []).append(paragraph)

    rebuilt = OrderedDict(
        (label, "\n\n".join(paragraphs).strip())
        for label, paragraphs in sections.items()
        if paragraphs
    )

    if len(rebuilt) < min_sections:
        fallback_sections: "OrderedDict[str, str]" = OrderedDict()
        total_paragraphs = len(ordered_texts)
        if total_paragraphs:
            chunk = max(1, total_paragraphs // min_sections)
            labels = list(SECTION_KEYWORDS.keys())
            cursor = 0
            for idx in range(min_sections):
                start = cursor
                end = total_paragraphs if idx == min_sections - 1 else min(total_paragraphs, cursor + chunk)
                segment = [p for p in ordered_texts[start:end] if p.strip()]
                cursor = end
                if not segment:
                    continue
                label = labels[idx] if idx < len(labels) else f"section_{idx + 1}"
                fallback_sections[label] = "\n\n".join(segment).strip()
        if fallback_sections:
            rebuilt = fallback_sections
        elif ctx.mode != "always":
            return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="insufficient_salvage")
        else:
            rebuilt = OrderedDict({"discussion": "\n\n".join(ordered_texts).strip()})

    pruned_labels: List[str] = []
    for label, content in list(rebuilt.items()):
        if _should_drop_section(content):
            pruned_labels.append(label)
            rebuilt.pop(label)

    if not rebuilt and ordered_texts:
        rebuilt = OrderedDict({"discussion": "\n\n".join(ordered_texts).strip()})

    document.sections = dict(rebuilt)
    pipeline_info["section_salvage_applied"] = True
    if pruned_labels:
        pipeline_info["section_salvage_pruned"] = pruned_labels
    sectionizer_bucket = pipeline_info.setdefault("sectionizer", {})
    sectionizer_bucket["sections_rebuilt"] = len(rebuilt)
    sectionizer_bucket["sections_pruned"] = len(pruned_labels)
    pipeline_info["sections_rebuilt"] = len(rebuilt)
    pipeline_info["sections_pruned"] = len(pruned_labels)
    if subtype == "editorial_or_economics":
        sectionizer_bucket["mode"] = "editorial"
        pipeline_info["sectionizer_mode"] = "editorial"
        pipeline_info["imrad_required"] = False
    else:
        sectionizer_bucket.setdefault("mode", "research")
        pipeline_info.setdefault("sectionizer_mode", sectionizer_bucket.get("mode"))
    pipeline_info.setdefault("second_pass", {}).setdefault("patches_applied", [])
    document.pipeline_info = pipeline_info

    modifications = {"sections_rebuilt": len(rebuilt)}
    if pruned_labels:
        modifications["sections_pruned"] = len(pruned_labels)

    return SecondPassPatchResult(
        name=PATCH_NAME,
        applied=True,
        modifications=modifications,
        reasons=["section_salvage"],
    )
