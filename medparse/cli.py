"""Command-line interface for Medparse."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional

import click
import typer

from medparse import __version__
from medparse.pipeline.run_extract import PipelineOutcome, run_extract
from medparse.utils.slug import slugify
from medparse.validate.validators import validate_document

app = typer.Typer(help="Medparse - structured medical PDF extraction.")

CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs"


@app.callback()
def version_callback(
    version: bool = typer.Option(False, "--version", callback=lambda value: _show_version(value)),
) -> None:
    """Register --version flag."""


def _show_version(value: bool) -> None:
    if value:
        typer.echo(f"medparse {__version__}")
        raise typer.Exit()


@app.command("extract-articles")
def extract_articles(
    input_dir: Path = typer.Argument(..., exists=True, file_okay=False, resolve_path=True),
    out: Path = typer.Option(Path("out/articles"), "--out", "-o", resolve_path=True),
    no_cache: bool = typer.Option(False, "--no-cache", help="Skip pipeline cache.", is_flag=True),
    force_deep: bool = typer.Option(False, "--force-deep", help="Start with full extraction.", is_flag=True),
    max_pages: Optional[int] = typer.Option(None, "--max-pages", min=1, help="Limit preview pages."),
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
    )


@app.command("extract-ifus")
def extract_ifus(
    input_dir: Path = typer.Argument(..., exists=True, file_okay=False, resolve_path=True),
    out: Path = typer.Option(Path("out/ifus"), "--out", "-o", resolve_path=True),
    no_cache: bool = typer.Option(False, "--no-cache", help="Skip pipeline cache.", is_flag=True),
    force_deep: bool = typer.Option(False, "--force-deep", help="Start with full extraction.", is_flag=True),
    max_pages: Optional[int] = typer.Option(None, "--max-pages", min=1, help="Limit preview pages."),
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
    )


@app.command("extract-textbook")
def extract_textbook(
    textbooks_root: Path = typer.Argument(..., exists=True, file_okay=False, resolve_path=True),
    out: Path = typer.Option(Path("out/textbooks"), "--out", "-o", resolve_path=True),
    no_cache: bool = typer.Option(False, "--no-cache", help="Skip pipeline cache.", is_flag=True),
    force_deep: bool = typer.Option(False, "--force-deep", help="Start with full extraction.", is_flag=True),
    max_pages: Optional[int] = typer.Option(None, "--max-pages", min=1, help="Limit preview pages."),
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
    for pdf_path, out_path in jobs:
        outcome = run_extract(
            pdf_path=pdf_path,
            config_path=config_path,
            use_cache=not no_cache,
            force_deep=force_deep,
            max_pages=max_pages,
            summary_length=normalized_summary,
        )
        _write_outcome(outcome, out_path)


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
) -> None:
    pdfs = list(pdfs)
    if not pdfs:
        typer.echo("No PDFs found for extraction.")
        raise typer.Exit(code=1)

    config_path = config_override if config_override else CONFIG_DIR / config_name
    normalized_summary = _normalize_summary(summary_length)
    out_dir.mkdir(parents=True, exist_ok=True)
    for pdf_path in pdfs:
        out_path = out_dir / f"{prefix}_{slugify(pdf_path.stem)}.json"
        outcome = run_extract(
            pdf_path=pdf_path,
            config_path=config_path,
            use_cache=use_cache,
            force_deep=force_deep,
            max_pages=max_pages,
            summary_length=normalized_summary,
        )
        _write_outcome(outcome, out_path)


def _write_outcome(outcome: PipelineOutcome, out_path: Path) -> None:
    """Write pipeline outcome to JSON with metadata and validation."""
    import hashlib

    payload = outcome.to_payload()

    # Add pipeline metadata for traceability
    payload["_pipeline_metadata"] = {
        "generator": "medparse",
        "pipeline_version": __version__,
        "engine": outcome.engine,
        "mode": outcome.mode,
        "cache_used": outcome.cache_used,
    }

    # Add config hash for reproducibility
    if outcome.config:
        config_str = f"{outcome.config.doc_type}:{outcome.config.layout_engine_primary}"
        config_hash = hashlib.md5(config_str.encode()).hexdigest()[:8]
        payload["_pipeline_metadata"]["config_hash"] = config_hash

    # Add first-3-pages hash for content verification
    if outcome.pdf_path and outcome.pdf_path.exists():
        try:
            pdf_bytes = outcome.pdf_path.read_bytes()[:50000]  # first ~50KB
            content_hash = hashlib.md5(pdf_bytes).hexdigest()[:12]
            payload["_pipeline_metadata"]["content_hash"] = content_hash
        except Exception:
            pass

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    typer.echo(f"Wrote {out_path}")

    if outcome.success and outcome.document is not None:
        issues = validate_document(outcome.document)
        has_errors = False
        for issue in issues:
            typer.echo(f"{issue.severity.upper()}: {issue.message}")
            if issue.severity == "error":
                has_errors = True

        # Exit with code 2 if there are hard errors
        if has_errors:
            typer.echo("VALIDATION FAILED: Hard errors detected in extraction output.")
            raise typer.Exit(code=2)
    else:
        typer.echo(f"EXTRACTION FAILED: {outcome.failure_reason}")
        raise typer.Exit(code=2)


def _normalize_summary(value: Optional[str]) -> Optional[str]:
    return value.lower() if value else None


def run() -> None:
    """Entrypoint to invoke the Typer application."""

    app()


if __name__ == "__main__":
    run()
