"""Protocol definitions for Medparse tool transports."""

from __future__ import annotations

from typing import Any, Dict, List, Protocol


class MedparseTool(Protocol):
    """Tool-shaped Medparse interface exposed to LangGraph flows."""

    def parse_document(self, url_or_path: str, options: Dict[str, Any]) -> Dict[str, Any]:
        """Parse a document and return an extraction envelope."""

    def enrich_stats(self, doc_id: str) -> List[Dict[str, Any]]:
        """Return enriched statistical results for ``doc_id``."""

    def extract_figures(self, doc_id: str) -> List[Dict[str, Any]]:
        """Return extracted figures for ``doc_id``."""

    def link_umls(self, doc_id: str) -> List[Dict[str, Any]]:
        """Return relation edges representing UMLS linking for ``doc_id``."""

    def compute_ats_yield(self, doc_id: str) -> Dict[str, Any]:
        """Compute ATS strict diagnostic yield for ``doc_id``."""
