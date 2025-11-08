"""Shared types for the second-pass orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Literal, Optional

from medparse.schema.common import BaseDocument
from medparse.validate.validators import ValidationIssue

SecondPassMode = Literal["off", "auto", "always"]


@dataclass(slots=True)
class SecondPassContext:
    """Execution context shared across all second-pass patchers."""

    validation_issues: List[ValidationIssue]
    paragraph_store: Dict[str, Dict[str, object]]
    evidence_bank: Dict[str, object]
    profile: Optional[str]
    engines_tried: List[str]
    emit_policies: Dict[str, object]
    config: Dict[str, object]
    mode: SecondPassMode
    doc_metrics: Dict[str, object]
    max_runtime_ms: int = 2500


@dataclass(slots=True)
class SecondPassPatchResult:
    """Outcome produced by an individual patcher invocation."""

    name: str
    applied: bool
    reasons: List[str] = field(default_factory=list)
    modifications: Dict[str, int] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    runtime_ms: int = 0
    skipped: bool = False

    @classmethod
    def skipped_result(cls, name: str, *, reason: Optional[str] = None) -> "SecondPassPatchResult":
        result = cls(name=name, applied=False, skipped=True)
        if reason:
            result.reasons.append(reason)
        return result


@dataclass(slots=True)
class PatcherResult:
    """Aggregated outcome across all executed second-pass patchers."""

    applied: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    modifications: Dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, object]:
        """Return a JSON-serializable view of the aggregated patch data."""

        return {
            "applied": list(self.applied),
            "reasons": list(self.reasons),
            "modifications": dict(self.modifications),
        }


@dataclass(slots=True)
class SecondPassReport:
    """Aggregated report returned by the orchestrator."""

    mode: SecondPassMode
    runtime_ms: int
    patches_applied: List[str] = field(default_factory=list)
    patch_results: List[SecondPassPatchResult] = field(default_factory=list)
    diff_summary: Dict[str, int] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    skipped: bool = False
    summary: PatcherResult = field(default_factory=PatcherResult)
    requires_revalidation: bool = False

    def as_metadata(self) -> Dict[str, object]:
        """Convert report into pipeline metadata payload."""

        return {
            "mode": self.mode,
            "runtime_ms": self.runtime_ms,
            "patches_applied": list(self.patches_applied),
            "diff_summary": dict(self.diff_summary),
            "notes": list(self.notes),
            "applied": list(self.summary.applied),
            "reasons": list(self.summary.reasons),
            "modifications": dict(self.summary.modifications),
            "requires_revalidation": self.requires_revalidation,
        }


SecondPassPatcher = Callable[[BaseDocument, SecondPassContext], SecondPassPatchResult]

__all__ = [
    "SecondPassContext",
    "SecondPassPatchResult",
    "PatcherResult",
    "SecondPassReport",
    "SecondPassPatcher",
    "SecondPassMode",
]
