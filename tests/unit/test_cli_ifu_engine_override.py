from __future__ import annotations

from pathlib import Path

import pytest

from medparse import cli


@pytest.mark.usefixtures("tmp_path")
def test_extract_ifus_engine_override_forwarded(tmp_path, monkeypatch):
    captured = {}

    def fake_run_pipeline_for_pdfs(*, ifu_engine_override=None, **kwargs):
        captured["ifu_engine_override"] = ifu_engine_override
        captured["kwargs"] = kwargs

    monkeypatch.setattr(cli, "_run_pipeline_for_pdfs", fake_run_pipeline_for_pdfs)

    input_dir = Path(tmp_path)
    cli.extract_ifus(
        input_dir=input_dir,
        out=input_dir,
        ifu_engine_override="pymupdf",
        no_cache=True,
        force_deep=False,
    )

    assert captured.get("ifu_engine_override") == "pymupdf"
