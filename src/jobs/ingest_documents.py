"""Ingest documents via Medparse and produce normalized graph payloads."""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Iterable, List, Sequence

from ..adapters.medparse_transport import ExtractRequest, MedparseTransport, get_medparse_transport
from ..config import AppConfig
from ..normalize.merge_enrichments import extract_to_graph_payload
from ..normalize.types import GraphPayload


def ingest_pdf(
    pdf_path: Path,
    *,
    doc_id: str | None = None,
    transport: MedparseTransport | None = None,
    raw_output_dir: Path | None = None,
) -> GraphPayload:
    """Ingest a single PDF document through Medparse."""

    cfg = AppConfig()
    client = transport or get_medparse_transport(cfg)

    request = _build_extract_request(pdf_path, doc_id=doc_id)
    response = client.extract(request)

    if raw_output_dir:
        raw_output_dir.mkdir(parents=True, exist_ok=True)
        raw_file = raw_output_dir / f"{request['doc_id']}.json"
        raw_file.write_text(json.dumps(response, indent=2, ensure_ascii=False), encoding="utf-8")

    return extract_to_graph_payload(response)


def ingest_documents(
    documents: Sequence[Path],
    *,
    transport: MedparseTransport | None = None,
    raw_output_dir: Path | None = None,
) -> List[GraphPayload]:
    """Ingest multiple documents and return their normalized payloads."""

    results: List[GraphPayload] = []
    cfg = AppConfig()
    client = transport or get_medparse_transport(cfg)

    for path in documents:
        request = _build_extract_request(path)
        payload = client.extract(request)
        if raw_output_dir:
            raw_output_dir.mkdir(parents=True, exist_ok=True)
            raw_file = raw_output_dir / f"{request['doc_id']}.json"
            raw_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        results.append(extract_to_graph_payload(payload))
    return results


def _build_extract_request(pdf_path: Path, *, doc_id: str | None = None) -> ExtractRequest:
    if not pdf_path.exists():
        raise FileNotFoundError(f"Document not found: {pdf_path}")
    document_id = doc_id or pdf_path.stem
    encoded = base64.b64encode(pdf_path.read_bytes()).decode("utf-8")
    return ExtractRequest(doc_id=document_id, bytes_b64=encoded)


__all__ = ["ingest_pdf", "ingest_documents"]
