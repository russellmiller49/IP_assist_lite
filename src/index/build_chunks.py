"""Table-aware markdown chunker used for the structured knowledge base."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, List, Sequence
import re

MD_TABLE_RE = re.compile(r"^\|.+\|\s*$\n^\|(?:\s*:?-+:?\s*\|)+\s*$", re.MULTILINE)


def chunk_markdown(md: str, max_chars: int = 4000, overlap: int = 400) -> List[str]:
    """Split markdown text into chunks while keeping tables intact."""
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    chunks: List[str] = []
    buffer = ""
    lines = md.splitlines(keepends=True)
    i = 0

    while i < len(lines):
        line = lines[i]
        block = line
        if i + 1 < len(lines) and MD_TABLE_RE.match(line + lines[i + 1]):
            block += lines[i + 1]
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                block += lines[i]
                i += 1
        else:
            i += 1

        if len(buffer) + len(block) > max_chars and buffer:
            chunks.append(buffer)
            overlap_text = buffer[-overlap:] if overlap > 0 else ""
            buffer = overlap_text + block
        else:
            buffer += block

    if buffer:
        chunks.append(buffer)

    return chunks


def _emit_counts(paths: Iterable[Path]) -> None:
    emitted = False
    for path in paths:
        if not path.is_file():
            continue
        emitted = True
        chunks = chunk_markdown(path.read_text(encoding="utf-8", errors="ignore"))
        print(f"{path}: {len(chunks)} chunks")
    if not emitted:
        print("no markdown files found")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Chunk markdown files with table preservation.")
    parser.add_argument("paths", nargs="*", help="Markdown files to chunk. Defaults to structured KB output.")
    parser.add_argument("--glob", dest="glob", default="data/structured_knowledge/diseases/*.md", help="Glob pattern when no explicit paths are provided.")
    args = parser.parse_args(argv)

    if args.paths:
        _emit_counts(Path(p) for p in args.paths)
    else:
        _emit_counts(Path().glob(args.glob))


if __name__ == "__main__":
    main()
