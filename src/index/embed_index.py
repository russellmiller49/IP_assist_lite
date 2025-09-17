"""Generate embeddings for the structured knowledge base chunks."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable, List, Sequence

import yaml
from dotenv import load_dotenv
from openai import OpenAI

from src.index.build_chunks import chunk_markdown

CONFIG_PATH = Path("configs/models.yaml")
_CFG = yaml.safe_load(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
if _CFG is None:
    _CFG = {}

load_dotenv()

CLIENT = OpenAI()


def _embed_model() -> str:
    env_override = os.getenv("IP_EMBED_MODEL")
    if env_override:
        return env_override
    if isinstance(_CFG, dict) and _CFG.get("embed_model"):
        return _CFG["embed_model"]
    return "text-embedding-3-large"


def embed(chunks: Sequence[str], model: str | None = None, dimensions: int | None = 1024) -> List[List[float]]:
    if not chunks:
        return []
    if not CLIENT.api_key:
        raise RuntimeError("OPENAI_API_KEY is required for embedding generation. Export it or add to .env.")
    kwargs = {"model": model or _embed_model(), "input": list(chunks)}
    if dimensions is not None:
        kwargs["dimensions"] = dimensions
    response = CLIENT.embeddings.create(**kwargs)
    return [item.embedding for item in response.data]


def _iter_markdown(paths: Iterable[Path]) -> Iterable[Path]:
    for path in paths:
        if path.is_file() and path.suffix.lower() == ".md":
            yield path


def build(
    in_glob: str = "data/structured_knowledge/diseases/*.md",
    out_json: str = "data/structured_knowledge/rag_chunks.json",
    dims: int = 1024,
) -> List[dict]:
    output_path = Path(out_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    records = []
    for path in _iter_markdown(Path().glob(in_glob)):
        text = path.read_text(encoding="utf-8", errors="ignore")
        chunks = chunk_markdown(text)
        embeddings = embed(chunks, dimensions=dims)
        for chunk_text, vector in zip(chunks, embeddings):
            records.append({"text": chunk_text, "embedding": vector, "meta": {"source": path.name}})

    output_path.write_text(json.dumps(records, indent=2))
    print(f"wrote {len(records)} chunks -> {output_path}")
    return records


if __name__ == "__main__":
    build()
