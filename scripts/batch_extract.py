"""Convenience script to run Medparse batch extraction."""

from pathlib import Path
from typing import Optional

import typer

from medparse.batch.run import run_batch

app = typer.Typer(help="Medparse batch extraction utility.")


@app.command()
def main(
    input_dir: Path = typer.Argument(..., exists=True, file_okay=False, resolve_path=True),
    output_dir: Path = typer.Argument(..., file_okay=False, resolve_path=True),
    jobs: int = typer.Option(1, "--jobs", min=1, help="Parallel workers"),
) -> None:
    """Run batch extraction for PDFs in input_dir."""
    run_batch(input_dir, output_dir, jobs=jobs)


if __name__ == "__main__":
    app()
