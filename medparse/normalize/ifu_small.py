"""Policies for harmonising small IFU leaflets."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Sequence

from medparse.ingest.models import PageData
from medparse.normalize.ifu_sections import clean_section_text


def _coerce_text(value: Any) -> Optional[str]:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            stripped = text.strip()
            return stripped or None
    return None


FALLBACK_SENTENCE_PATTERNS = (
    "indicated for",
    "indicated to",
    "intended for",
    "intended to",
    "designed for",
    "designed to",
    "for use in",
    "for use with",
    "used for",
)


def _extract_intended_use_from_pages(pages: Sequence[PageData]) -> Optional[str]:
    intent_pattern = re.compile(
        r"(INDICATIONS?|CLINICAL\s+INDICATIONS?|INTENDED\s+(?:USE|PURPOSE)|APPLICATIONS?)",
        re.IGNORECASE,
    )
    stop_pattern = re.compile(r"\n\s*(?:\d+\s+[A-Z]|[A-Z]{2,})")
    for page in pages[:3]:
        page_lines = page.lines or []
        if not page_lines:
            continue
        page_text = "\n".join(page_lines)
        match = intent_pattern.search(page_text)
        if not match:
            continue
        segment = page_text[match.end():]
        segment = segment.lstrip(" :\n")
        stop = stop_pattern.search(segment)
        if stop:
            segment = segment[: stop.start()]
        lines = [line.strip() for line in segment.splitlines() if line.strip()]
        while lines and re.match(r"^\d+\.", lines[0]):
            lines.pop(0)
        while lines and lines[0] and lines[0][0].islower():
            lines.pop(0)
        collected: list[str] = []
        for line in lines:
            if re.match(r"^[\*•\-]\s*\d*", line):
                continue
            if re.match(r"^\d+(\.|[\s])", line):
                break
            if re.match(r"^[A-Z]{3,}(?:\s+[A-Z]{2,})*$", line):
                break
            collected.append(line)
        if not collected:
            continue
        joined = " ".join(collected).strip()
        joined = re.sub(r"\s*\*+\d+\b", "", joined)
        sentences = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", joined) if segment.strip()]
        extracted = None
        for idx, sentence in enumerate(sentences):
            lowered = sentence.lower()
            if any(keyword in lowered for keyword in ("intended", "indication", "designed")):
                extracted = sentence
                if idx + 1 < len(sentences):
                    follow = sentences[idx + 1]
                    if "do not use" in follow.lower():
                        extracted = f"{sentence} {follow}"
                break
        target = extracted or joined
        use_text = clean_section_text(target)
        if use_text:
            return use_text
    # Fallback: look for sentences containing indicative phrases
    for page in pages[:3]:
        page_text = "\n".join(page.lines or [])
        if not page_text:
            continue
        sentences = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", page_text) if segment.strip()]
        collected_sentences: List[str] = []
        for sentence in sentences:
            lowered = sentence.lower()
            if any(token in lowered for token in FALLBACK_SENTENCE_PATTERNS):
                normalized = clean_section_text(sentence)
                if normalized:
                    collected_sentences.append(normalized)
            if len(collected_sentences) >= 2:
                break
        if collected_sentences:
            return " ".join(collected_sentences)
    return None


def apply_small_leaflet_policy(
    ifu_payload: Dict[str, Any],
    *,
    policy: Optional[str],
    page_count: int,
    pages: Optional[Sequence[PageData]] = None,
) -> bool:
    policy_key = (policy or "").strip().lower()
    if policy_key != "map_intended_use_to_indications":
        return False
    if page_count > 4:
        return False

    existing_indications = _coerce_text(ifu_payload.get("indications_for_use"))
    if existing_indications:
        lowered_existing = existing_indications.lower()
        if len(existing_indications) < 300 and any(
            keyword in lowered_existing for keyword in ("intended", "indication", "indicated")
        ):
            return False

    intended_text = _coerce_text(ifu_payload.get("intended_use"))
    allow_replace_intended = False
    if intended_text:
        if len(intended_text) > 300:
            allow_replace_intended = True
        else:
            lowered_intended = intended_text.lower()
            if not any(token in lowered_intended for token in ("intended", "designed", "purpose")):
                allow_replace_intended = True
    else:
        allow_replace_intended = True

    if pages and allow_replace_intended:
        extracted = _extract_intended_use_from_pages(pages)
        if extracted:
            intended_text = extracted
            if allow_replace_intended or not _coerce_text(ifu_payload.get("intended_use")):
                ifu_payload["intended_use"] = extracted
    if not intended_text:
        return False

    ifu_payload["indications_for_use"] = {
        "text": intended_text,
        "derived_from": "intended_use",
        "provenance": "small_leaflet_mapper",
    }
    return True


__all__ = ["apply_small_leaflet_policy"]
