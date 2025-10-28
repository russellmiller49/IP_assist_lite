"""Evidence deduplication utilities for size reduction."""

from __future__ import annotations

from typing import Dict, List, Optional

from medparse.schema.common import EvidenceSpan, SizeGuards, TruncationNotice
from medparse.utils.log import get_logger

LOGGER = get_logger(__name__)


class EvidenceBank:
    """Manager for deduplicated evidence storage."""

    def __init__(self, size_guards: Optional[SizeGuards] = None):
        """Initialize evidence bank with optional size limits.

        Args:
            size_guards: Configuration for size limits
        """
        self.bank: Dict[str, EvidenceSpan] = {}
        self.size_guards = size_guards or SizeGuards()
        self.stats = {
            "total_added": 0,
            "deduplicated": 0,
            "truncated": 0,
        }

    def add_evidence(
        self, evidence: Optional[EvidenceSpan], max_count: Optional[int] = None
    ) -> Optional[str]:
        """Add evidence to bank and return hash ID.

        Args:
            evidence: Evidence span to add
            max_count: Maximum number of evidence items to keep (for per-item limits)

        Returns:
            Hash ID of evidence, or None if evidence was None
        """
        if not evidence or not evidence.text:
            return None

        self.stats["total_added"] += 1

        # Truncate text if needed
        max_chars = self.size_guards.max_chars_per_evidence
        if len(evidence.text) > max_chars:
            evidence.text = evidence.text[:max_chars]
            evidence.truncated = True
            self.stats["truncated"] += 1

        # Compute hash
        hash_id = evidence.compute_hash(max_chars=max_chars)

        # Check if already exists
        if hash_id in self.bank:
            self.stats["deduplicated"] += 1
            return hash_id

        # Add to bank
        self.bank[hash_id] = evidence
        return hash_id

    def add_evidence_list(
        self, evidence_list: Optional[List[EvidenceSpan]]
    ) -> List[str]:
        """Add multiple evidence spans and return list of hash IDs.

        Args:
            evidence_list: List of evidence spans

        Returns:
            List of hash IDs
        """
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
        """Generate truncation notice from stats.

        Returns:
            TruncationNotice if any truncation occurred, else None
        """
        if self.stats["truncated"] == 0:
            return None

        return TruncationNotice(
            evidence_dropped=0,  # Will be set by caller
            tables_dropped=0,
            sections_dropped=0,
            chars_truncated=self.stats["truncated"],
            reason="size_guards_evidence_truncation",
        )

    def get_bank(self) -> Dict[str, EvidenceSpan]:
        """Get the evidence bank dictionary.

        Returns:
            Dictionary of hash_id -> EvidenceSpan
        """
        return self.bank

    def get_stats(self) -> Dict[str, int]:
        """Get deduplication statistics.

        Returns:
            Dictionary with total_added, deduplicated, truncated counts
        """
        return self.stats.copy()


__all__ = ["EvidenceBank"]
