import json
import time
from pathlib import Path

import pytest

from medparse.pipeline import run_ingest


def _write_metrics(out_path: Path, *, second_pass: bool) -> None:
    payload = {
        "_metrics": {
            "tables_original": 3,
            "tables_kept": 3,
            "tables_dropped": 0,
            "second_pass_applied": second_pass,
        }
    }
    out_path.write_text(json.dumps(payload))


def test_auto_backend_routes_text_and_scanned(monkeypatch, tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    files = [input_dir / name for name in ("ifu_text_a.pdf", "ifu_text_b.pdf", "ifu_scanned.pdf")]
    for path in files:
        path.write_bytes(b"PDF")

    def fake_probe(path: Path) -> bool:
        return "scanned" not in path.name.lower()

    monkeypatch.setattr(run_ingest, "fast_text_probe", fake_probe)

    medparse_calls: list[str] = []
    docling_calls: list[tuple[str, bool]] = []

    def fake_medparse(pdf_path: Path, doc_type: str, out_dir: Path) -> Path:
        medparse_calls.append(pdf_path.name)
        out_path = out_dir / f"{pdf_path.stem}.json"
        _write_metrics(out_path, second_pass=True)
        return out_path

    def fake_docling(*, pdf_path: Path, doc_type: str, out_dir: Path, use_ocr: bool, accel: str) -> Path:
        docling_calls.append((pdf_path.name, use_ocr))
        out_path = out_dir / f"{pdf_path.stem}.json"
        payload = {
            "safety_warnings": [
                {
                    "text": "WARNING",
                    "severity": "warning",
                }
            ],
            "_metrics": {
                "tables_original": 1,
                "tables_kept": 1,
                "tables_dropped": 0,
                "second_pass_applied": False,
            },
        }
        out_path.write_text(json.dumps(payload))
        return out_path

    monkeypatch.setattr(run_ingest, "_run_medparse_pipeline", fake_medparse)
    monkeypatch.setattr(run_ingest, "_run_docling_pipeline", fake_docling)

    output_dir = tmp_path / "out"
    start = time.perf_counter()
    run_ingest.ingest_path(
        input_path=input_dir,
        out_dir=output_dir,
        doc_type="ifu",
        backend="auto",
        accel="cpu",
        limit=None,
    )
    elapsed = time.perf_counter() - start

    assert elapsed < 5, "Auto backend should not stall on text PDFs"
    assert len(medparse_calls) == 2, "Text IFUs should use the Medparse path"
    assert len(docling_calls) == 1, "Scanned IFUs should use Docling"
    assert docling_calls[0][0] == "ifu_scanned.pdf"
    assert docling_calls[0][1] is True, "Scanned IFUs require OCR"

    outputs = list(output_dir.glob("*.json"))
    assert len(outputs) == 3
    for artifact in outputs:
        payload = json.loads(artifact.read_text())
        metrics = payload.get("_metrics", {})
        assert "tables_original" in metrics
        assert "tables_kept" in metrics
        assert "tables_dropped" in metrics
        assert "second_pass_applied" in metrics

    scanned_payload = json.loads((output_dir / "ifu_scanned.json").read_text())
    safety = scanned_payload.get("safety_warnings", [])
    assert safety and any(block.get("text") for block in safety)


def test_backend_override_respects_user_choice(monkeypatch, tmp_path):
    pdf_path = tmp_path / "single.pdf"
    pdf_path.write_bytes(b"PDF")

    monkeypatch.setattr(run_ingest, "fast_text_probe", lambda _: True)

    medparse_calls: list[str] = []
    docling_calls: list[str] = []

    def fake_medparse(pdf_path: Path, doc_type: str, out_dir: Path) -> Path:
        medparse_calls.append(pdf_path.name)
        out = out_dir / f"{pdf_path.stem}.json"
        _write_metrics(out, second_pass=True)
        return out

    def fake_docling(*, pdf_path: Path, doc_type: str, out_dir: Path, use_ocr: bool, accel: str) -> Path:
        docling_calls.append(pdf_path.name)
        out = out_dir / f"{pdf_path.stem}.json"
        _write_metrics(out, second_pass=False)
        return out

    monkeypatch.setattr(run_ingest, "_run_medparse_pipeline", fake_medparse)
    monkeypatch.setattr(run_ingest, "_run_docling_pipeline", fake_docling)

    out_dir = tmp_path / "out"
    run_ingest.ingest_path(
        input_path=pdf_path,
        out_dir=out_dir,
        doc_type="ifu",
        backend="medparse",
        accel="cpu",
        limit=None,
    )
    assert medparse_calls == ["single.pdf"]
    assert not docling_calls

    medparse_calls.clear()
    run_ingest.ingest_path(
        input_path=pdf_path,
        out_dir=out_dir,
        doc_type="ifu",
        backend="docling",
        accel="cpu",
        limit=None,
    )
    assert docling_calls == ["single.pdf"]
    assert not medparse_calls
