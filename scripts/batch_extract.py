"""Convenience script to run Medparse batch extraction."""

from __future__ import annotations

from pathlib import Path

import typer

from typing import Literal

from medparse.batch.run import run_batch

app = typer.Typer(help="Medparse batch extraction utility.")

SupportedDocType = Literal["article", "ifu", "textbook"]


@app.command()
def main(
    doc_type: SupportedDocType = typer.Argument(..., help="Document type: article|ifu|textbook"),
    input_dir: Path = typer.Argument(..., exists=True, file_okay=False, resolve_path=True),
    output_dir: Path = typer.Argument(..., file_okay=False, resolve_path=True),
) -> None:
    """Run batch extraction for PDFs in ``input_dir``."""

    run_batch(input_dir, output_dir, doc_type=doc_type)


if __name__ == "__main__":
    app()
