import json
from pathlib import Path

from typer.testing import CliRunner

from medparse.batch.run import run_batch
from medparse.cli import app

ARTICLES_DIR = Path("tests/data/articles")
IFU_DIR = Path("tests/data/ifu")


def test_run_batch_articles(tmp_path) -> None:
    out_dir = tmp_path / "articles"
    run_batch(ARTICLES_DIR, out_dir, doc_type="article")

    produced = {path.name for path in out_dir.glob("article_*.json")}
    assert produced == {"article_robotic-cryobiopsy-2022.json"}
    report = json.loads((out_dir / "extraction_report.json").read_text())
    assert report["failed_count"] == 0


def test_cli_extract_ifus(tmp_path) -> None:
    runner = CliRunner()
    out_dir = tmp_path / "cli-ifus"
    result = runner.invoke(app, [
        "extract-ifus",
        str(IFU_DIR),
        "--out",
        str(out_dir),
    ])
    assert result.exit_code == 0
    payload = json.loads(next(out_dir.glob("ifu_*.json")).read_text())
    assert payload["doc_type"] == "ifu"


def test_cli_version_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "medparse" in result.stdout.lower()
