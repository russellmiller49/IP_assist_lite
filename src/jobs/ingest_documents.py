"""Ingest documents via Medparse, persist graph/vector data, and emit summaries."""
from __future__ import annotations

import argparse
import base64
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

from adapters.medparse_transport import (
    ExtractRequest,
    MedparseTransport,
    get_medparse_transport,
)
from config import AppConfig
from normalize.merge_enrichments import extract_to_graph_payload
from normalize.types import GraphPayload
from graph.sinks.neo4j_sink import Neo4jSink
from graph.sinks.qdrant_sink import QdrantSink


@dataclass(slots=True)
class IngestSummary:
    doc_id: str
    counts: dict[str, int]
    edges: dict[str, int]

    def as_json(self) -> str:
        return json.dumps(
            {
                "doc_id": self.doc_id,
                "counts": self.counts,
                "edges": self.edges,
            }
        )


def ingest_pdf(
    pdf_path: Path,
    *,
    doc_id: str | None = None,
    doc_type: str | None = None,
    transport: MedparseTransport | None = None,
    sinks: Sequence[object] | None = None,
    raw_output_dir: Path | None = None,
) -> tuple[GraphPayload, IngestSummary]:
    """Ingest a single PDF document through Medparse and persist to sinks."""

    cfg = AppConfig()
    client = transport or get_medparse_transport(cfg)
    created_sinks = False
    actual_sinks = sinks
    if actual_sinks is None:
        actual_sinks = _build_sinks(cfg)
        created_sinks = True
    try:
        request = _build_extract_request(pdf_path, doc_id=doc_id, doc_type=doc_type)
        response = client.extract(request)
        graph, summary = _persist_response(response, cfg, actual_sinks, raw_output_dir)
        return graph, summary
    finally:
        if created_sinks:
            _close_sinks(actual_sinks)


def ingest_payload(
    payload: dict,
    *,
    cfg: AppConfig | None = None,
    sinks: Sequence[object] | None = None,
    raw_output_dir: Path | None = None,
) -> tuple[GraphPayload, IngestSummary]:
    """Ingest a pre-extracted Medparse JSON payload into sinks."""

    config = cfg or AppConfig()
    created_sinks = False
    actual_sinks = sinks
    if actual_sinks is None:
        actual_sinks = _build_sinks(config)
        created_sinks = True
    try:
        return _persist_response(payload, config, actual_sinks, raw_output_dir)
    finally:
        if created_sinks:
            _close_sinks(actual_sinks)


def ingest_documents(
    documents: Sequence[Path],
    *,
    doc_type: str | None = None,
    transport: MedparseTransport | None = None,
    raw_output_dir: Path | None = None,
) -> List[IngestSummary]:
    """Ingest multiple PDF documents."""

    cfg = AppConfig()
    client = transport or get_medparse_transport(cfg)
    sinks = _build_sinks(cfg)

    summaries: List[IngestSummary] = []
    try:
        for path in documents:
            request = _build_extract_request(path, doc_type=doc_type)
            response = client.extract(request)
            _, summary = _persist_response(response, cfg, sinks, raw_output_dir)
            summaries.append(summary)
        return summaries
    finally:
        _close_sinks(sinks)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _persist_response(
    payload: dict,
    cfg: AppConfig,
    sinks: Sequence[object],
    raw_output_dir: Path | None,
) -> tuple[GraphPayload, IngestSummary]:
    graph_payload = extract_to_graph_payload(payload)

    if raw_output_dir:
        raw_output_dir.mkdir(parents=True, exist_ok=True)
        out_file = raw_output_dir / f"{graph_payload['doc_id']}.json"
        out_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    for sink in sinks:
        sink.upsert(graph_payload)

    return graph_payload, _summarise_graph_payload(graph_payload)


def _summarise_graph_payload(graph_payload: GraphPayload) -> IngestSummary:
    nodes = graph_payload.get("nodes", {})
    counts = {
        "sections": len(graph_payload.get("sections", [])),
        "recommendations": len(nodes.get("Recommendation", [])) if isinstance(nodes, dict) else 0,
        "stats": len(nodes.get("Stat", [])) if isinstance(nodes, dict) else 0,
        "figures": len(nodes.get("Figure", [])) if isinstance(nodes, dict) else 0,
        "tables": len(nodes.get("Table", [])) if isinstance(nodes, dict) else 0,
    }

    edge_counts: dict[str, int] = {}
    for edge in graph_payload.get("edges", []):
        edge_type = str(edge.get("type", "RELATED_TO"))
        edge_counts[edge_type] = edge_counts.get(edge_type, 0) + 1

    return IngestSummary(doc_id=graph_payload["doc_id"], counts=counts, edges=edge_counts)


def _build_sinks(cfg: AppConfig) -> List[object]:
    sinks: List[object] = []
    if cfg.APP_USE_NEO4J:
        try:
            sinks.append(Neo4jSink.from_config(cfg))
        except RuntimeError as exc:  # pragma: no cover - environment misconfigured
            sys.stderr.write(f"[warn] Neo4j sink unavailable: {exc}\n")
    if cfg.APP_USE_QDRANT:
        try:
            sinks.append(QdrantSink.from_config(cfg))
        except RuntimeError as exc:  # pragma: no cover - environment misconfigured
            sys.stderr.write(f"[warn] Qdrant sink unavailable: {exc}\n")
    return sinks


def _build_extract_request(
    pdf_path: Path,
    *,
    doc_id: str | None = None,
    doc_type: str | None = None,
) -> ExtractRequest:
    if not pdf_path.exists():
        raise FileNotFoundError(f"Document not found: {pdf_path}")
    document_id = doc_id or pdf_path.stem
    encoded = base64.b64encode(pdf_path.read_bytes()).decode("utf-8")
    request = ExtractRequest(doc_id=document_id, bytes_b64=encoded)
    if doc_type:
        request["doc_type"] = doc_type
    return request


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest documents via Medparse and persist to graph stores.")
    parser.add_argument("--path", nargs="*", help="Paths or glob patterns to PDF documents.")
    parser.add_argument("--json", nargs="*", help="Paths or glob patterns to Medparse JSON payloads.")
    parser.add_argument("--doc-type", default=None, help="Optional Medparse document type.")
    parser.add_argument("--raw-dir", default=None, help="Directory to store raw extraction JSON.")
    args = parser.parse_args(argv)

    cfg = AppConfig()
    transport = get_medparse_transport(cfg)
    sinks = _build_sinks(cfg)
    raw_dir = Path(args.raw_dir) if args.raw_dir else None

    summaries: List[IngestSummary] = []

    if args.path:
        pdf_paths = _resolve_paths(args.path)
        for path in pdf_paths:
            request = _build_extract_request(path, doc_type=args.doc_type)
            response = transport.extract(request)
            _, summary = _persist_response(response, cfg, sinks, raw_dir)
            summaries.append(summary)

    if args.json:
        json_paths = _resolve_paths(args.json)
        for path in json_paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            _, summary = ingest_payload(payload, cfg=cfg, sinks=sinks, raw_output_dir=raw_dir)
            summaries.append(summary)

    try:
        for summary in summaries:
            sys.stdout.write(summary.as_json() + "\n")
        return 0
    finally:
        _close_sinks(sinks)


def _resolve_paths(patterns: Iterable[str]) -> List[Path]:
    paths: List[Path] = []
    for pattern in patterns:
        expanded = list(Path().glob(pattern))
        if expanded:
            paths.extend(expanded)
        else:
            candidate = Path(pattern)
            if candidate.exists():
                paths.append(candidate)
    return paths


def _close_sinks(sinks: Sequence[object]) -> None:
    for sink in sinks:
        close = getattr(sink, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # pragma: no cover - defensive cleanup
                pass


def main() -> None:
    raise SystemExit(_cli())


__all__ = [
    "IngestSummary",
    "ingest_pdf",
    "ingest_payload",
    "ingest_documents",
    "main",
]
