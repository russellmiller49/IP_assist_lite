"""Command-line interface for Medparse."""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Dict, Iterable, Optional

# Suppress sklearn version warnings from spaCy models (loaded internally)
# These warnings occur because spaCy models contain sklearn components from 1.1.2
warnings.filterwarnings(
    "ignore",
    message=".*Trying to unpickle.*version.*",
    category=UserWarning,
)
warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    module="sklearn",
)

import os
import sys

import click
import typer

from medparse import __version__
from medparse.pipeline.run_extract import PipelineOutcome, run_extract, write_failure_artifact
from medparse.utils.slug import slugify
from medparse.validate.validators import validate_document
from medparse.config import ExtractionProfile

app = typer.Typer(help="Medparse - structured medical PDF extraction.")

CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs"


@app.callback()
def version_callback(
    version: bool = typer.Option(False, "--version", callback=lambda value: _show_version(value)),
) -> None:
    """Register --version flag."""

    if os.getenv("MEDPARSE_CLI_DEBUG_ARGS"):
        typer.echo(f"[medparse.cli] argv={sys.argv}")


def _show_version(value: bool) -> None:
    # Typer sometimes passes string "False" instead of boolean
    if value and str(value).lower() != "false":
        typer.echo(f"medparse {__version__}")
        raise typer.Exit()


@app.command("extract-articles")
def extract_articles(
    input_dir: Path = typer.Argument(..., exists=True, file_okay=False, resolve_path=True),
    out: Path = typer.Option(Path("out/articles"), "--out", "-o", resolve_path=True),
    no_cache: bool = typer.Option(False, "--no-cache", help="Skip pipeline cache.", is_flag=True),
    force_deep: bool = typer.Option(False, "--force-deep", help="Start with full extraction.", is_flag=True),
    max_pages: Optional[int] = typer.Option(None, "--max-pages", min=1, help="Limit preview pages."),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        help="Extraction profile (enriched|fast_raw).",
        click_type=click.Choice([p.value for p in ExtractionProfile], case_sensitive=False),
    ),
    summary_length: Optional[str] = typer.Option(
        None,
        "--summary-length",
        help="Override summary length.",
        click_type=click.Choice(["short", "medium", "long"], case_sensitive=False),
    ),
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        exists=True,
        resolve_path=True,
        help="Path to pipeline configuration YAML.",
    ),
    tables_mode: Optional[str] = typer.Option(
        None,
        "--tables-mode",
        help="Override tables emit mode (compact|verbatim).",
        click_type=click.Choice(["compact", "verbatim"], case_sensitive=False),
    ),
    evidence_policy: Optional[str] = typer.Option(
        None,
        "--evidence-policy",
        help="Override evidence policy (compact|verbatim).",
        click_type=click.Choice(["compact", "verbatim"], case_sensitive=False),
    ),
    zotero_json: Optional[Path] = typer.Option(
        None,
        "--zotero-json",
        help="Override Zotero CSL JSON export for front-matter enrichment.",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    emit_raw_pages: bool = typer.Option(False, "--emit-raw-pages", help="Emit raw page text to sidecar files (disabled by default)."),
) -> None:
    """Run the article extractor for every PDF in ``input_dir``."""

    pdfs = sorted(input_dir.glob("*.pdf"))
    _run_pipeline_for_pdfs(
        pdfs=pdfs,
        out_dir=out,
        prefix="article",
        config_name="run_article.yaml",
        use_cache=not no_cache,
        force_deep=force_deep,
        max_pages=max_pages,
        summary_length=summary_length,
        config_override=config,
        profile_override=profile,
        emit_raw_pages=emit_raw_pages,
        tables_mode=tables_mode,
        evidence_policy=evidence_policy,
        zotero_json=zotero_json,
    )


@app.command("extract-guidelines")
def extract_guidelines(
    input_dir: Path = typer.Argument(..., exists=True, file_okay=False, resolve_path=True),
    out: Path = typer.Option(Path("out/guidelines"), "--out", "-o", resolve_path=True),
    no_cache: bool = typer.Option(False, "--no-cache", help="Skip pipeline cache.", is_flag=True),
    force_deep: bool = typer.Option(False, "--force-deep", help="Start with full extraction.", is_flag=True),
    max_pages: Optional[int] = typer.Option(None, "--max-pages", min=1, help="Limit preview pages."),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        help="Extraction profile (enriched|fast_raw).",
        click_type=click.Choice([p.value for p in ExtractionProfile], case_sensitive=False),
    ),
    summary_length: Optional[str] = typer.Option(
        None,
        "--summary-length",
        help="Override summary length.",
        click_type=click.Choice(["short", "medium", "long"], case_sensitive=False),
    ),
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        exists=True,
        resolve_path=True,
        help="Path to pipeline configuration YAML.",
    ),
    tables_mode: Optional[str] = typer.Option(
        None,
        "--tables-mode",
        help="Override tables emit mode (compact|verbatim).",
        click_type=click.Choice(["compact", "verbatim"], case_sensitive=False),
    ),
    evidence_policy: Optional[str] = typer.Option(
        None,
        "--evidence-policy",
        help="Override evidence policy (compact|verbatim).",
        click_type=click.Choice(["compact", "verbatim"], case_sensitive=False),
    ),
    zotero_json: Optional[Path] = typer.Option(
        None,
        "--zotero-json",
        help="Override Zotero CSL JSON export for front-matter enrichment.",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    emit_raw_pages: bool = typer.Option(False, "--emit-raw-pages", help="Emit raw page text to sidecar files (disabled by default)."),
) -> None:
    """Run the guideline extractor for every PDF in ``input_dir``."""

    pdfs = sorted(input_dir.glob("*.pdf"))
    _run_pipeline_for_pdfs(
        pdfs=pdfs,
        out_dir=out,
        prefix="guideline",
        config_name="run_guideline.yaml",
        use_cache=not no_cache,
        force_deep=force_deep,
        max_pages=max_pages,
        summary_length=summary_length,
        config_override=config,
        profile_override=profile,
        emit_raw_pages=emit_raw_pages,
        tables_mode=tables_mode,
        evidence_policy=evidence_policy,
        zotero_json=zotero_json,
    )


@app.command("extract-ifus")
def extract_ifus(
    input_dir: Path = typer.Argument(..., exists=True, file_okay=False, resolve_path=True),
    out: Path = typer.Option(Path("out/ifus"), "--out", "-o", resolve_path=True),
    no_cache: bool = typer.Option(False, "--no-cache", help="Skip pipeline cache.", is_flag=True),
    force_deep: bool = typer.Option(False, "--force-deep", help="Start with full extraction.", is_flag=True),
    max_pages: Optional[int] = typer.Option(None, "--max-pages", min=1, help="Limit preview pages."),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        help="Extraction profile (enriched|fast_raw).",
        click_type=click.Choice([p.value for p in ExtractionProfile], case_sensitive=False),
    ),
    summary_length: Optional[str] = typer.Option(
        None,
        "--summary-length",
        help="Override summary length.",
        click_type=click.Choice(["short", "medium", "long"], case_sensitive=False),
    ),
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        exists=True,
        resolve_path=True,
        help="Path to pipeline configuration YAML.",
    ),
    tables_mode: Optional[str] = typer.Option(
        None,
        "--tables-mode",
        help="Override tables emit mode (compact|verbatim).",
        click_type=click.Choice(["compact", "verbatim"], case_sensitive=False),
    ),
    evidence_policy: Optional[str] = typer.Option(
        None,
        "--evidence-policy",
        help="Override evidence policy (compact|verbatim).",
        click_type=click.Choice(["compact", "verbatim"], case_sensitive=False),
    ),
    zotero_json: Optional[Path] = typer.Option(
        None,
        "--zotero-json",
        help="Override Zotero CSL JSON export for front-matter enrichment.",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    emit_raw_pages: bool = typer.Option(False, "--emit-raw-pages", help="Emit raw page text to sidecar files (disabled by default)."),
) -> None:
    """Run the IFU/manual extractor."""

    pdfs = sorted(input_dir.glob("*.pdf"))
    _run_pipeline_for_pdfs(
        pdfs=pdfs,
        out_dir=out,
        prefix="ifu",
        config_name="run_ifu.yaml",
        use_cache=not no_cache,
        force_deep=force_deep,
        max_pages=max_pages,
        summary_length=summary_length,
        config_override=config,
        profile_override=profile,
        emit_raw_pages=emit_raw_pages,
        tables_mode=tables_mode,
        evidence_policy=evidence_policy,
        zotero_json=None,
    )


@app.command("extract-textbook")
def extract_textbook(
    textbooks_root: Path = typer.Argument(..., exists=True, file_okay=False, resolve_path=True),
    out: Path = typer.Option(Path("out/textbooks"), "--out", "-o", resolve_path=True),
    no_cache: bool = typer.Option(False, "--no-cache", help="Skip pipeline cache.", is_flag=True),
    force_deep: bool = typer.Option(False, "--force-deep", help="Start with full extraction.", is_flag=True),
    max_pages: Optional[int] = typer.Option(None, "--max-pages", min=1, help="Limit preview pages."),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        help="Extraction profile (enriched|fast_raw).",
        click_type=click.Choice([p.value for p in ExtractionProfile], case_sensitive=False),
    ),
    summary_length: Optional[str] = typer.Option(
        None,
        "--summary-length",
        help="Override summary length.",
        click_type=click.Choice(["short", "medium", "long"], case_sensitive=False),
    ),
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        exists=True,
        resolve_path=True,
        help="Path to pipeline configuration YAML.",
    ),
    tables_mode: Optional[str] = typer.Option(
        None,
        "--tables-mode",
        help="Override tables emit mode (compact|verbatim).",
        click_type=click.Choice(["compact", "verbatim"], case_sensitive=False),
    ),
    evidence_policy: Optional[str] = typer.Option(
        None,
        "--evidence-policy",
        help="Override evidence policy (compact|verbatim).",
        click_type=click.Choice(["compact", "verbatim"], case_sensitive=False),
    ),
    zotero_json: Optional[Path] = typer.Option(
        None,
        "--zotero-json",
        help="Override Zotero CSL JSON export for front-matter enrichment.",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    emit_raw_pages: bool = typer.Option(False, "--emit-raw-pages", help="Emit raw page text to sidecar files (disabled by default)."),
) -> None:
    """Run the textbook chapter extractor for each subfolder."""

    jobs: list[tuple[Path, Path]] = []
    for folder in sorted(path for path in textbooks_root.iterdir() if path.is_dir()):
        book_slug = slugify(folder.name)
        candidate_dirs = [folder]
        pdf_subdir = folder / "pdf"
        if pdf_subdir.exists():
            candidate_dirs.append(pdf_subdir)
        seen: set[Path] = set()
        for candidate in candidate_dirs:
            for pdf in sorted(candidate.glob("*.pdf")):
                if pdf in seen:
                    continue
                seen.add(pdf)
                chapter_slug = slugify(pdf.stem)
                jobs.append((pdf, out / f"textbook_{book_slug}_{chapter_slug}.json"))

    if not jobs:
        typer.echo("No textbook PDFs discovered.")
        raise typer.Exit(code=1)

    config_path = config if config else CONFIG_DIR / "run_textbook.yaml"
    normalized_summary = _normalize_summary(summary_length)
    out.mkdir(parents=True, exist_ok=True)
    emit_overrides: Dict[str, object] = {}
    if tables_mode:
        emit_overrides["tables_mode"] = tables_mode.lower()
    if evidence_policy:
        emit_overrides["evidence_policy"] = evidence_policy.lower()
    overrides_payload = emit_overrides or None
    metadata_overrides: Dict[str, object] = {}
    if zotero_json:
        metadata_overrides["zotero_json"] = str(zotero_json)
    metadata_payload = metadata_overrides or None
    failures: list[Path] = []
    successes = 0
    profile_label = profile or "auto"
    for pdf_path, out_path in jobs:
        try:
            outcome = run_extract(
                pdf_path=pdf_path,
                config_path=config_path,
                use_cache=not no_cache,
                force_deep=force_deep,
                max_pages=max_pages,
                summary_length=normalized_summary,
                profile_override=profile,
                emit_overrides=overrides_payload,
                metadata_overrides=metadata_payload,
            )
        except Exception as exc:  # pragma: no cover - defensive batch safeguard
            write_failure_artifact(
                out_path,
                exc,
                stage="extract",
                profile=profile_label,
                doc_path=pdf_path,
            )
            failures.append(out_path)
            continue
        outcome.metadata["emit_raw_pages"] = emit_raw_pages
        if _write_outcome(outcome, out_path):
            successes += 1
        else:
            failures.append(out_path)

    if failures:
        typer.echo(f"{len(failures)} textbook extraction(s) reported validation errors or failures.")
    if successes == 0:
        raise typer.Exit(code=2)


def _run_pipeline_for_pdfs(
    *,
    pdfs: Iterable[Path],
    out_dir: Path,
    prefix: str,
    config_name: str,
    use_cache: bool,
    force_deep: bool,
    max_pages: Optional[int],
    summary_length: Optional[str],
    config_override: Optional[Path],
    profile_override: Optional[str],
    emit_raw_pages: bool,
    tables_mode: Optional[str],
    evidence_policy: Optional[str],
    zotero_json: Optional[Path],
) -> None:
    pdfs = list(pdfs)
    if not pdfs:
        typer.echo("No PDFs found for extraction.")
        raise typer.Exit(code=1)

    config_path = config_override if config_override else CONFIG_DIR / config_name
    normalized_summary = _normalize_summary(summary_length)
    out_dir.mkdir(parents=True, exist_ok=True)
    emit_overrides: Dict[str, object] = {}
    if tables_mode:
        emit_overrides["tables_mode"] = tables_mode.lower()
    if evidence_policy:
        emit_overrides["evidence_policy"] = evidence_policy.lower()
    overrides_payload = emit_overrides or None
    metadata_overrides: Dict[str, object] = {}
    if zotero_json:
        metadata_overrides["zotero_json"] = str(zotero_json)
    metadata_payload = metadata_overrides or None
    failures: list[Path] = []
    successes = 0
    profile_label = profile_override or "auto"
    for pdf_path in pdfs:
        out_path = out_dir / f"{prefix}_{slugify(pdf_path.stem)}.json"
        try:
            outcome = run_extract(
                pdf_path=pdf_path,
                config_path=config_path,
                use_cache=use_cache,
                force_deep=force_deep,
                max_pages=max_pages,
                summary_length=normalized_summary,
                profile_override=profile_override,
                emit_overrides=overrides_payload,
                metadata_overrides=metadata_payload,
            )
        except Exception as exc:  # pragma: no cover - defensive batch safeguard
            write_failure_artifact(
                out_path,
                exc,
                stage="extract",
                profile=profile_label,
                doc_path=pdf_path,
            )
            failures.append(out_path)
            continue

        outcome.metadata["emit_raw_pages"] = emit_raw_pages
        if _write_outcome(outcome, out_path):
            successes += 1
        else:
            failures.append(out_path)

    if failures:
        typer.echo(f"{len(failures)} extraction(s) reported validation errors or failures.")
    if successes == 0:
        raise typer.Exit(code=2)


def _collect_failure_metrics(outcome: PipelineOutcome) -> Dict[str, object]:
    """Assemble uniform failure metrics payload."""

    base_metrics = dict(outcome.metrics or {})
    document = outcome.document

    page_count = base_metrics.get("page_count")
    coverage_ratio = base_metrics.get("coverage_ratio")
    extracted_chars = base_metrics.get("extracted_chars")
    duration = base_metrics.get("duration_s")

    sections_count = base_metrics.get("sections_count")
    recommendations_count = base_metrics.get("recommendations_count")
    tables_kept = base_metrics.get("tables_kept")
    umls_entities = base_metrics.get("umls_entities")
    diagnostic_present = base_metrics.get("diagnostic_yield_present")

    if document is not None:
        if sections_count is None and hasattr(document, "sections"):
            sections = getattr(document, "sections")
            if isinstance(sections, dict):
                sections_count = len(sections)
        if recommendations_count is None and hasattr(document, "recommendations"):
            recommendations = getattr(document, "recommendations")
            if isinstance(recommendations, list):
                recommendations_count = len(recommendations)
        if tables_kept is None and hasattr(document, "tables"):
            tables = getattr(document, "tables")
            if isinstance(tables, list):
                tables_kept = len(tables)
        if umls_entities is None and hasattr(document, "umls_entities"):
            entities = getattr(document, "umls_entities")
            if isinstance(entities, list):
                umls_entities = len(entities)
        if diagnostic_present is None and hasattr(document, "diagnostic_yield"):
            diagnostic_present = bool(getattr(document, "diagnostic_yield"))

    engines_raw = outcome.metadata.get("engines_requested", [])
    if isinstance(engines_raw, list):
        engines_tried = engines_raw
    elif engines_raw:
        engines_tried = [engines_raw]
    else:
        engines_tried = []
    profile = None
    if outcome.config:
        profile = outcome.config.profile.value

    failure_metrics: Dict[str, object] = {
        "page_count": page_count,
        "coverage_ratio": coverage_ratio,
        "extracted_chars": extracted_chars,
        "sections_count": sections_count,
        "recommendations_count": recommendations_count,
        "umls_entities": umls_entities,
        "diagnostic_yield_present": diagnostic_present,
        "tables_kept": tables_kept,
        "duration_s": duration,
        "engines_tried": engines_tried,
        "profile": profile,
        "cache_used": outcome.cache_used,
    }
    return failure_metrics


def _write_outcome(outcome: PipelineOutcome, out_path: Path) -> bool:
    """Write pipeline outcome to JSON with metadata and validation."""
    import hashlib

    payload = outcome.to_payload()

    metadata = payload.setdefault("_pipeline_metadata", {})
    metadata.setdefault("generator", "medparse")
    metadata.setdefault("pipeline_version", __version__)
    metadata.setdefault("engine", outcome.engine)
    metadata.setdefault("mode", outcome.mode)
    metadata.setdefault("cache_used", outcome.cache_used)
    metadata.setdefault("warnings", [])

    # Add config hash for reproducibility
    if outcome.config:
        engine_tag = ",".join(outcome.config.engines)
        config_str = f"{outcome.config.doc_type}:{engine_tag}:{outcome.config.profile.value}"
        config_hash = hashlib.md5(config_str.encode()).hexdigest()[:8]
        metadata["config_hash"] = config_hash

    # Add first-3-pages hash for content verification
    if outcome.pdf_path and outcome.pdf_path.exists():
        try:
            pdf_bytes = outcome.pdf_path.read_bytes()[:50000]  # first ~50KB
            content_hash = hashlib.md5(pdf_bytes).hexdigest()[:12]
            metadata["content_hash"] = content_hash
        except Exception:
            pass

    emit_settings = metadata.get("emit", {}) or {}

    validator_issues = []
    if outcome.success and outcome.document is not None:
        validator_issues = validate_document(outcome.document)
        metadata["validators"] = {
            "passed": not any(issue.severity == "error" for issue in validator_issues),
            "warnings": [issue.message for issue in validator_issues if issue.severity == "warning"],
            "errors": [issue.message for issue in validator_issues if issue.severity == "error"],
        }
    else:
        metadata.setdefault(
            "validators",
            {
                "passed": False,
                "warnings": [],
                "errors": [outcome.failure_reason or "extraction_failed"],
            },
        )

    payload_json = json.dumps(payload, indent=2, ensure_ascii=False)
    max_json_bytes = emit_settings.get("max_json_bytes") if isinstance(emit_settings, dict) else None
    if isinstance(max_json_bytes, int) and max_json_bytes > 0:
        json_size = len(payload_json.encode("utf-8"))
        if json_size > max_json_bytes:
            metadata.setdefault("warnings", []).append(
                f"json_size_exceeded:{json_size}>{max_json_bytes}"
            )
            payload_json = json.dumps(payload, indent=2, ensure_ascii=False)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(payload_json)
    typer.echo(f"Wrote {out_path}")

    if outcome.success and outcome.document is not None:
        has_errors = False
        for issue in validator_issues:
            typer.echo(f"{issue.severity.upper()}: {issue.message}")
            if issue.severity == "error":
                has_errors = True

        if has_errors:
            failure_path = out_path.with_suffix(".failure.json")
            failure_payload = {
                "source_file": str(outcome.pdf_path),
                "failure_reason": "validation_failed",
                "issues": [issue.message for issue in validator_issues if issue.severity == "error"],
                "metrics": _collect_failure_metrics(outcome),
            }
            failure_path.write_text(json.dumps(failure_payload, indent=2, ensure_ascii=False))
            typer.echo("VALIDATION FAILED: Hard errors detected in extraction output.")
            return False
        return True

    failure_path = out_path.with_suffix(".failure.json")
    failure_payload = {
        "source_file": str(outcome.pdf_path),
        "failure_reason": outcome.failure_reason or "extraction_failed",
        "issues": outcome.warnings,
        "metrics": _collect_failure_metrics(outcome),
    }
    failure_path.write_text(json.dumps(failure_payload, indent=2, ensure_ascii=False))
    typer.echo(f"EXTRACTION FAILED: {outcome.failure_reason}")
    return False


def _normalize_summary(value: Optional[str]) -> Optional[str]:
    return value.lower() if value else None


def run() -> None:
    """Entrypoint to invoke the Typer application."""

    app()


if __name__ == "__main__":
    run()
