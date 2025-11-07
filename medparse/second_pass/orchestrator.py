"""Second-pass orchestrator that coordinates targeted patchers."""

from __future__ import annotations

import time
from typing import Dict, List

from medparse.schema.common import BaseDocument
from medparse.utils.log import get_logger

from .patchers import get_patchers_for
from .types import PatcherResult, SecondPassContext, SecondPassPatchResult, SecondPassReport

LOGGER = get_logger(__name__)


def _ensure_pipeline_bucket(document: BaseDocument) -> Dict[str, object]:
    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    if not isinstance(pipeline_info, dict):
        pipeline_info = {}
    second_pass_bucket = pipeline_info.setdefault("second_pass", {})
    if not isinstance(second_pass_bucket, dict):
        second_pass_bucket = {}
        pipeline_info["second_pass"] = second_pass_bucket
    applied_list = second_pass_bucket.setdefault("patches_applied", [])
    if not isinstance(applied_list, list):
        second_pass_bucket["patches_applied"] = []
    applied_alias = second_pass_bucket.setdefault("applied", [])
    if not isinstance(applied_alias, list):
        second_pass_bucket["applied"] = []
    document.pipeline_info = pipeline_info
    return second_pass_bucket


def _aggregate_modifications(results: List[SecondPassPatchResult]) -> Dict[str, int]:
    summary: Dict[str, int] = {}
    for result in results:
        for key, value in result.modifications.items():
            summary[key] = summary.get(key, 0) + int(value)
    return summary


def run_second_pass(document: BaseDocument, ctx: SecondPassContext) -> tuple[BaseDocument, SecondPassReport]:
    """Execute the ordered second-pass patchers for the given document."""

    patchers = get_patchers_for(getattr(document, "doc_type", ""))
    if not patchers or ctx.mode == "off":
        LOGGER.debug("Second pass disabled or no patchers registered for doc_type=%s", getattr(document, "doc_type", None))
        report = SecondPassReport(mode=ctx.mode, runtime_ms=0, skipped=True)
        return document, report

    start = time.perf_counter()
    second_pass_bucket = _ensure_pipeline_bucket(document)
    applied_sentinals = second_pass_bucket.setdefault("patches_applied", [])
    if not isinstance(applied_sentinals, list):
        applied_sentinals = second_pass_bucket["patches_applied"] = []

    patch_results: List[SecondPassPatchResult] = []
    patches_applied: List[str] = []

    max_runtime_ms = max(250, int(ctx.max_runtime_ms or 0))
    timed_out = False

    for patcher in patchers:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        if elapsed_ms >= max_runtime_ms:
            timed_out = True
            LOGGER.warning(
                "Second pass runtime exceeded (%d ms >= %d ms); skipping remaining patchers.",
                elapsed_ms,
                max_runtime_ms,
            )
            break

        snapshot = None
        patch_name = getattr(patcher, "__name__", getattr(patcher, "__qualname__", str(patcher)))
        if hasattr(document, "model_copy"):
            try:
                snapshot = document.model_copy(deep=True)  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover - defensive
                snapshot = None
        result_start = time.perf_counter()
        try:
            result = patcher(document, ctx)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.exception("Second pass patcher '%s' raised an error; reverting", patch_name)
            if snapshot is not None:
                document = snapshot
            result = SecondPassPatchResult.skipped_result(
                patch_name,
                reason=f"patch_reverted:{exc.__class__.__name__}",
            )
            second_pass_bucket.setdefault("patch_reverted", []).append(patch_name)
        result.runtime_ms = int((time.perf_counter() - result_start) * 1000)
        patch_results.append(result)
        if result.applied:
            patches_applied.append(result.name)
            LOGGER.info(
                "Second pass patcher '%s' applied modifications=%s reasons=%s",
                result.name,
                result.modifications or {},
                result.reasons or [],
            )
        else:
            LOGGER.debug(
                "Second pass patcher '%s' skipped (reasons=%s)",
                result.name,
                result.reasons or [],
            )

    runtime_ms = int((time.perf_counter() - start) * 1000)
    diff_summary = _aggregate_modifications(patch_results)

    aggregated_reasons: List[str] = []
    for result in patch_results:
        if result.reasons:
            for reason in result.reasons:
                if reason and reason not in aggregated_reasons:
                    aggregated_reasons.append(reason)

    aggregated_applied = list(dict.fromkeys(patches_applied))
    summary_modifications: Dict[str, int] = {}
    for key, value in diff_summary.items():
        try:
            summary_modifications[str(key)] = int(value)
        except (TypeError, ValueError):
            continue

    second_pass_bucket["runtime_ms"] = runtime_ms
    second_pass_bucket["diff_summary"] = diff_summary
    second_pass_bucket["patches_attempted"] = [result.name for result in patch_results]
    second_pass_bucket["mode"] = ctx.mode
    modifications_bucket = second_pass_bucket.setdefault("modifications", {})
    # Reset to maintain a stable snapshot while remaining idempotent across runs.
    modifications_bucket.clear()
    modifications_bucket.update(summary_modifications)
    if aggregated_applied:
        for name in aggregated_applied:
            if name not in applied_sentinals:
                applied_sentinals.append(name)
        applied_list = list(applied_sentinals)
        second_pass_bucket["patches_applied"] = applied_list
        second_pass_bucket["applied"] = list(aggregated_applied)
    else:
        second_pass_bucket.setdefault("applied", [])
    if timed_out:
        second_pass_bucket["timed_out"] = True
    if aggregated_reasons:
        second_pass_bucket["reasons"] = list(aggregated_reasons)
    else:
        second_pass_bucket.setdefault("reasons", [])

    document.pipeline_info = getattr(document, "pipeline_info", {}) or {}

    summary = PatcherResult(
        applied=list(aggregated_applied),
        reasons=list(aggregated_reasons),
        modifications=dict(summary_modifications),
    )

    report = SecondPassReport(
        mode=ctx.mode,
        runtime_ms=runtime_ms,
        patches_applied=patches_applied,
        patch_results=patch_results,
        diff_summary=diff_summary,
        notes=["timed_out"] if timed_out else [],
        skipped=False,
        summary=summary,
    )

    return document, report


__all__ = ["run_second_pass"]
