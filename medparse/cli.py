"""Command-line interface for Medparse."""

from pathlib import Path
from typing import Optional

import typer

from medparse import __version__
from medparse.extract.dispatcher import dispatch_document

app = typer.Typer(help="Medparse - structured medical PDF extraction.")


@app.callback()
def version_callback(
    _: bool = typer.Option(
        False,
        "--version",
        help="Show Medparse version and exit.",
        callback=lambda value: _show_version(value),
    )
) -> None:
    """Register a --version flag."""


def _show_version(value: bool) -> None:
    if value:
        typer.echo(f"medparse {__version__}")
        raise typer.Exit()


@app.command()
def extract(
    file: Path = typer.Argument(..., exists=True, readable=True, resolve_path=True),
    json: Optional[Path] = typer.Option(
        None, "--json", "-j", help="Write extraction JSON output to this path."
    ),
) -> None:
    """Extract structured data for a single PDF."""
    document = dispatch_document(file)
    payload = document.model_dump(mode="json")
    if json:
        json.parent.mkdir(parents=True, exist_ok=True)
        json.write_text(document.model_dump_json(indent=2))
        typer.echo(f"Wrote extraction to {json}")
    else:
        typer.echo(payload)


@app.command()
def batch(
    input: Path = typer.Argument(..., exists=True, readable=True, resolve_path=True, dir_okay=True),
    out: Path = typer.Option(Path("out"), "--out", "-o", help="Output directory for JSON payloads."),
    jobs: int = typer.Option(1, "--jobs", "-j", min=1, help="Parallel workers."),
) -> None:
    """Process an entire directory of PDFs."""
    from medparse.batch.run import run_batch

    run_batch(input, out, jobs=jobs)


def run() -> None:
    """Entrypoint to invoke the Typer application."""
    app()


if __name__ == "__main__":
    run()
