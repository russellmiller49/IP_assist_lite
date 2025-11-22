"""Runtime backend chooser for ingestion workloads."""

from __future__ import annotations

import json
import logging
import os
import shutil
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, List, Literal, Optional

from docling.backend.docling_parse_v4_backend import DoclingParseV4DocumentBackend
from docling.datamodel.accelerator_options import AcceleratorOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import RapidOcrOptions, ThreadedPdfPipelineOptions
from docling.document_converter import DocumentConverter, FormatOption
from docling.pipeline.threaded_standard_pdf_pipeline import ThreadedStandardPdfPipeline
import typer

from medparse.pipeline.fast_text_probe import fast_text_probe
from medparse.pipeline.run_extract import run_extract, write_failure_artifact, build_language_payloads
from medparse.post import postprocess_docling
from medparse.second_pass.patchers.ifu_metadata_validator import IFUMetadataValidator
from medparse.utils.slug import slugify
from medparse.validate.verifier import ValidationFailure, Verifier


BackendChoice = Literal["auto", "medparse", "docling"]
DocTypeChoice = Literal["ifu", "article", "textbook"]

class BackendEnum(str, Enum):
    auto = "auto"
    medparse = "medparse"
    docling = "docling"

class DocTypeEnum(str, Enum):
    ifu = "ifu"
    article = "article"
    textbook = "textbook"


LOGGER = logging.getLogger(__name__)
if not LOGGER.handlers:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

app = typer.Typer(add_completion=False)

CONFIG_ROOT = Path(__file__).resolve().parents[2] / "configs"
CONFIG_MAP: Dict[DocTypeChoice, Path] = {
    "ifu": CONFIG_ROOT / "run_ifu.yaml",
    "article": CONFIG_ROOT / "run_article.yaml",
    "textbook": CONFIG_ROOT / "run_textbook.yaml",
}

DEFAULT_OUTPUT = Path("/output")
INGEST_BUILD_SHA = os.getenv("INGEST_BUILD_SHA") or os.getenv("GIT_SHA", "dev")
VERIFIER = Verifier()
DOC_CONVERTER_CACHE: Dict[tuple[bool, str], DocumentConverter] = {}


@app.command()
def main(  # pragma: no cover - exercised via typer app
    file_path: Optional[Path] = typer.Argument(
        None,
        help="PDF file or directory to process.",
    ),
    out: Path = typer.Option(
        DEFAULT_OUTPUT,
        "--output-dir",
        "--out",
        help="Directory where JSON artifacts will be written.",
    ),
    doc_type: DocTypeEnum = typer.Option(
        DocTypeEnum.ifu,
        "--doc-type",
        "-t",
        help="{ifu,article,textbook}",
    ),
    backend: BackendEnum = typer.Option(
        BackendEnum.auto,
        "--backend",
        "-b",
        help="{auto,medparse,docling}",
    ),
    disable_ocr_for_text: bool = typer.Option(
        True,
        "--disable-ocr-for-text/--no-disable-ocr-for-text",
        help="Skip OCR when a text layer is present.",
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        min=1,
        help="Process at most N PDFs (useful for smoke tests).",
    ),
    version: bool = typer.Option(
        False,
        "--version",
        help="Print build/runtime information and exit.",
        is_flag=True,
    ),
) -> None:
    """Command-line entry point."""

    prefer_gpu = _prefer_gpu()
    accel = "cuda" if prefer_gpu else "cpu"
    if version:
        typer.echo(f"INGEST_BUILD_SHA={INGEST_BUILD_SHA} BACKEND={backend.value} ACCEL={accel}")
        raise typer.Exit()

    if file_path is None:
        raise typer.BadParameter("FILE_PATH is required unless --version is passed")

    LOGGER.info("INGEST_BUILD_SHA=%s", INGEST_BUILD_SHA)
    LOGGER.info("CUDA available: %s", prefer_gpu)
    try:
        ingest_path(
            input_path=file_path,
            out_dir=out,
            doc_type=doc_type.value,  # type: ignore[arg-type]
            backend=backend.value,    # type: ignore[arg-type]
            limit=limit,
            accel=accel,
            disable_ocr_for_text=disable_ocr_for_text,
        )
    except RuntimeError as exc:  # pragma: no cover - surfaced as CLI exit code
        raise typer.Exit(code=1) from exc


def ingest_path(
    *,
    input_path: Path,
    out_dir: Path,
    doc_type: DocTypeChoice,
    backend: BackendChoice,
    accel: str,
    limit: Optional[int] = None,
    disable_ocr_for_text: bool = True,
) -> None:
    pdfs = list(_collect_pdfs(input_path))
    if not pdfs:
        raise RuntimeError(f"No PDFs were found under {input_path}")
    if limit is not None:
        pdfs = pdfs[:limit]

    out_dir.mkdir(parents=True, exist_ok=True)
    failures: List[Path] = []
    for pdf_path in pdfs:
        try:
            _process_single_pdf(
                pdf_path=pdf_path,
                out_dir=out_dir,
                doc_type=doc_type,
                requested_backend=backend,
                accel=accel,
                disable_ocr_for_text=disable_ocr_for_text,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.exception("Ingestion failed for %s: %s", pdf_path.name, exc)
            failures.append(pdf_path)

    if failures:
        names = ", ".join(path.name for path in failures)
        raise RuntimeError(f"Failed to ingest {len(failures)} file(s): {names}")


def _collect_pdfs(base_path: Path) -> Iterable[Path]:
    if not base_path.exists():
        raise RuntimeError(f"Input path does not exist: {base_path}")
    if base_path.is_file():
        return [base_path]
    return sorted(path for path in base_path.glob("*.pdf") if path.is_file())


def _process_single_pdf(
    *,
    pdf_path: Path,
    out_dir: Path,
    doc_type: DocTypeChoice,
    requested_backend: BackendChoice,
    accel: str,
    disable_ocr_for_text: bool,
) -> Path:
    text_present = _probe_text_layer(pdf_path, requested_backend)
    resolved_backend = _select_backend(requested_backend, text_present)
    ocr_enabled = _should_enable_ocr(resolved_backend, text_present, disable_ocr_for_text)
    LOGGER.info(
        "[ingest] sha=%s file=%s doc_type=%s backend=%s text_pdf=%s accel=%s ocr=%s",
        INGEST_BUILD_SHA,
        pdf_path.name,
        doc_type,
        resolved_backend,
        text_present,
        accel,
        ocr_enabled,
    )

    if resolved_backend == "medparse":
        return _run_medparse_pipeline(pdf_path, doc_type, out_dir)

    return _run_docling_pipeline(
        pdf_path=pdf_path,
        doc_type=doc_type,
        out_dir=out_dir,
        use_ocr=ocr_enabled,
        accel=accel,
    )


def _probe_text_layer(pdf_path: Path, backend: BackendChoice) -> bool:
    if backend == "medparse":
        return True
    return fast_text_probe(pdf_path)


def _select_backend(requested: BackendChoice, text_present: bool) -> BackendChoice:
    if requested != "auto":
        return requested
    return "medparse" if text_present else "docling"


def _should_enable_ocr(
    resolved_backend: BackendChoice,
    text_present: bool,
    disable_ocr_for_text: bool,
) -> bool:
    if resolved_backend != "docling":
        return False
    if text_present and _resolve_disable_ocr_flag(disable_ocr_for_text):
        return False
    return True


def _is_truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _prefer_gpu() -> bool:
    return shutil.which("nvidia-smi") is not None or bool(os.environ.get("CUDA_VISIBLE_DEVICES"))


def _resolve_disable_ocr_flag(cli_flag: bool) -> bool:
    env_flag = os.getenv("DOCLING_DISABLE_OCR_FOR_TEXT")
    if env_flag is None:
        return cli_flag
    return _is_truthy(env_flag)


def _run_medparse_pipeline(pdf_path: Path, doc_type: DocTypeChoice, out_dir: Path) -> Path:
    config_path = CONFIG_MAP[doc_type]
    outcome = run_extract(
        pdf_path=pdf_path,
        config_path=config_path,
        use_cache=True,
        force_deep=False,
        max_pages=None,
        summary_length=None,
        profile_override=None,
        emit_overrides=None,
        metadata_overrides=None,
        ifu_overrides=None,
        second_pass_mode="auto",
        chunking_mode="smart",
    )
    output_name = f"{slugify(pdf_path.stem)}.json"
    out_path = out_dir / output_name
    if not outcome.success:
        write_failure_artifact(
            out_path,
            RuntimeError(outcome.failure_reason or "extraction_failed"),
            stage="extract",
            profile=outcome.config.profile.value if outcome.config else doc_type,
            doc_path=pdf_path,
        )
        raise RuntimeError(outcome.failure_reason or f"Medparse pipeline failed for {pdf_path}")

    payload = outcome.to_payload()
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    pipeline_meta = payload.get("_pipeline_metadata", {}) if isinstance(payload, dict) else {}
    split_languages = bool(pipeline_meta.get("split_languages"))
    if split_languages:
        lang_payloads = build_language_payloads(payload)
        for lang, lang_payload in lang_payloads.items():
            lang_out_path = out_dir / f"{slugify(pdf_path.stem)}.{lang}.json"
            lang_out_path.write_text(json.dumps(lang_payload, ensure_ascii=False, indent=2))
    return out_path


def _run_docling_pipeline(
    *,
    pdf_path: Path,
    doc_type: DocTypeChoice,
    out_dir: Path,
    use_ocr: bool,
    accel: str,
) -> Path:
    converter = _get_docling_converter(use_ocr=use_ocr, accel=accel)
    conversion = converter.convert(pdf_path)
    result = postprocess_docling(
        conversion,
        doc_type=doc_type,
        doc_id=pdf_path.name,
        source_pdf=pdf_path,
    )

    if doc_type == "ifu":
        validator = IFUMetadataValidator()
        result = validator.run(result)

    try:
        VERIFIER.verify(result)
    except ValidationFailure as exc:  # pragma: no cover - informational
        LOGGER.warning("Validation failed for %s: %s", pdf_path.name, exc)

    out_path = out_dir / f"{slugify(pdf_path.stem)}.json"
    out_path.write_text(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
    return out_path


def _get_docling_converter(*, use_ocr: bool, accel: str) -> DocumentConverter:
    key = (use_ocr, accel)
    cached = DOC_CONVERTER_CACHE.get(key)
    if cached:
        return cached

    pipeline_options = ThreadedPdfPipelineOptions()
    pipeline_options.do_ocr = use_ocr
    ocr_options = RapidOcrOptions()
    ocr_options.backend = "torch" if accel == "cuda" else "onnxruntime"
    pipeline_options.ocr_options = ocr_options
    pipeline_options.accelerator_options = AcceleratorOptions(device=accel)

    format_options = {
        InputFormat.PDF: FormatOption(
            pipeline_cls=ThreadedStandardPdfPipeline,
            pipeline_options=pipeline_options,
            backend=DoclingParseV4DocumentBackend,
        )
    }
    converter = DocumentConverter(format_options=format_options)
    DOC_CONVERTER_CACHE[key] = converter
    return converter


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    app()
