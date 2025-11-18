"""Evidence bank writer that deduplicates spans and anchors to paragraphs."""

from __future__ import annotations

from typing import Dict, List, MutableMapping, Optional

from medparse.normalize.evidence_bank import span_to_ref
from medparse.schema.common import EvidenceSpan, SizeGuards, TruncationNotice
from medparse.utils.log import get_logger

LOGGER = get_logger(__name__)


class EvidenceBank:
    """Manager for deduplicated evidence storage."""

    def __init__(
        self,
        size_guards: Optional[SizeGuards] = None,
        *,
        paragraph_store: Optional[MutableMapping[str, Dict[str, object]]] = None,
        inline_text: bool = False,
    ):
        """Initialize evidence bank with optional size limits."""

        self.bank: Dict[str, Dict[str, object]] = {}
        self.size_guards = size_guards or SizeGuards()
        self.paragraph_store = paragraph_store or {}
        self.inline_text = inline_text
        self.stats = {
            "total_added": 0,
            "deduplicated": 0,
            "truncated": 0,
        }

    @staticmethod
    def _compute_truncation_percent(original: int, kept: int) -> float:
        if original <= 0:
            return 0.0
        clipped = max(original - kept, 0)
        return round((clipped / float(original)) * 100.0, 2)

    def _apply_truncation_metadata(
        self,
        payload: Dict[str, object],
        *,
        original_length: int,
        kept_length: int,
        reason: str,
    ) -> None:
        if original_length <= 0:
            return
        payload["clip_chars_original"] = original_length
        payload["clip_chars_kept"] = kept_length
        payload["original_length"] = original_length
        payload["truncation_percent"] = self._compute_truncation_percent(original_length, kept_length)
        payload["truncation_reason"] = reason
        payload["truncated"] = True

    def _resolve_text(self, span: EvidenceSpan) -> Optional[str]:
        if span.text:
            return span.text
        paragraph_hash = span.paragraph_hash or span.hash
        if not paragraph_hash:
            return None
        entry = self.paragraph_store.get(paragraph_hash)
        if isinstance(entry, dict):
            text = str(entry.get("text") or "")
            if not text:
                return None
            start, end = span.paragraph_offset or (0, len(text))
            start = max(int(start or 0), 0)
            end = max(int(end or len(text)), start)
            try:
                return text[start:end]
            except Exception:  # pragma: no cover - defensive
                return text
        return None

    @staticmethod
    def _clip_sentence(snippet: str, limit: int) -> str:
        if limit <= 0 or len(snippet) <= limit:
            return snippet.strip()
        window = snippet[:limit]
        sentence_end = max(window.rfind(". "), window.rfind("? "), window.rfind("! "))
        if sentence_end >= max(40, int(limit * 0.5)):
            return window[: sentence_end + 1].strip()
        last_space = window.rfind(" ")
        if last_space > 0:
            return window[:last_space].strip()
        return window.strip()

    def add_evidence(self, evidence: Optional[EvidenceSpan]) -> Optional[str]:
        """Add evidence to bank and return hash ID."""

        if not isinstance(evidence, EvidenceSpan):
            return None

        self.stats["total_added"] += 1
        max_chars = self.size_guards.max_chars_per_evidence
        clip_info: Dict[str, object] = {}
        if self.inline_text and evidence.text and len(evidence.text) > max_chars:
            original_len = len(evidence.text)
            evidence.text = self._clip_sentence(evidence.text, max_chars)
            evidence.truncated = True
            self.stats["truncated"] += 1
            clip_info = {
                "original_length": original_len,
                "kept_length": len(evidence.text),
                "reason": "length_cap",
            }

        if not evidence.hash:
            evidence.hash = evidence.compute_hash(max_chars=max_chars)

        ref = span_to_ref(evidence, self.paragraph_store)
        if not ref:
            return None

        hash_id = str(ref.get("hash"))
        if hash_id in self.bank:
            self.stats["deduplicated"] += 1
            return hash_id

        payload = dict(ref)
        if self.inline_text:
            snippet = self._resolve_text(evidence)
            if snippet:
                if len(snippet) > max_chars:
                    original_len = len(snippet)
                    clipped = self._clip_sentence(snippet, max_chars)
                    payload["text"] = clipped
                    self._apply_truncation_metadata(
                        payload,
                        original_length=original_len,
                        kept_length=len(clipped),
                        reason="length_cap",
                    )
                    self.stats["truncated"] += 1
                else:
                    payload["text"] = snippet

        if clip_info:
            self._apply_truncation_metadata(
                payload,
                original_length=int(clip_info.get("original_length") or 0),
                kept_length=int(clip_info.get("kept_length") or 0),
                reason=str(clip_info.get("reason") or "length_cap"),
            )

        self.bank[hash_id] = payload
        return hash_id

    def add_evidence_list(
        self, evidence_list: Optional[List[EvidenceSpan]]
    ) -> List[str]:
        """Add multiple evidence spans and return list of hash IDs."""

        if not evidence_list:
            return []

        max_count = self.size_guards.max_evidence_per_item
        refs: List[str] = []

        for evidence in evidence_list[:max_count]:
            hash_id = self.add_evidence(evidence)
            if hash_id:
                refs.append(hash_id)

        if len(evidence_list) > max_count:
            LOGGER.debug(
                "Truncated evidence list from %d to %d items",
                len(evidence_list),
                max_count,
            )

        return refs

    def get_truncation_notice(self) -> Optional[TruncationNotice]:
        """Generate truncation notice from stats."""

        if self.stats["truncated"] == 0:
            return None

        return TruncationNotice(
            evidence_dropped=0,
            tables_dropped=0,
            sections_dropped=0,
            chars_truncated=self.stats["truncated"],
            reason="size_guards_evidence_truncation",
        )

    def get_bank(self) -> Dict[str, Dict[str, object]]:
        """Get the evidence bank dictionary (hash -> payload)."""
        return self.bank

    def get_text_bank(self) -> Dict[str, str]:
        """Get the evidence bank as text-only dictionary for JSON export."""

        return {
            hash_id: str(payload.get("text", ""))
            for hash_id, payload in self.bank.items()
            if isinstance(payload, dict) and "text" in payload
        }

    def get_stats(self) -> Dict[str, int]:
        """Get deduplication statistics."""

        return self.stats.copy()


__all__ = ["EvidenceBank"]
