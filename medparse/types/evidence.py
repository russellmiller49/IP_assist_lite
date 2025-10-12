"""Containers for evidence span collections."""

from typing import List

from pydantic import BaseModel

from .base import EvidenceSpan


class EvidenceList(BaseModel):
    """Holds one or more evidence spans for a single field."""

    items: List[EvidenceSpan]


__all__ = ["EvidenceList"]
