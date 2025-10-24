"""Rule-based document classifier."""

from __future__ import annotations

from pathlib import Path

from medparse.ingest.pdf_reader import iter_pages


def _count_occurrences(text: str, tokens: set[str]) -> int:
    return sum(text.count(token) for token in tokens)


def classify_with_rules(pdf_path: Path) -> str:
    """Return a doc_type label using heuristics."""
    pages = list(iter_pages(pdf_path))
    if not pages:
        return "article"

    text = " \n".join(page.text.lower() for page in pages)
    lines = [line.lower() for page in pages for line in page.lines]
    section_titles = [
        heading.title.lower() for page in pages for heading in page.headings if heading.kind == "section"
    ]

    scores = {"ifu": 0.0, "article": 0.0, "textbook_chapter": 0.0}

    # IFU signals
    ifu_tokens_primary = {
        "instructions for use",
        "user manual",
        "indications for use",
        "ifu",
    }
    ifu_tokens_secondary = {"warning", "caution", "note", "intuitive", "sterile"}
    scores["ifu"] += 3 * _count_occurrences(text, ifu_tokens_primary)
    scores["ifu"] += 0.5 * _count_occurrences(text, ifu_tokens_secondary)
    if text.count("warning") > 20:
        scores["ifu"] += 5
    if any("model" in line and "system" in line for line in lines):
        scores["ifu"] += 2

    # Article signals
    article_tokens_primary = {"study", "methods", "patients", "lesions", "retrospective", "prospective"}
    article_tokens_secondary = {"diagnostic yield", "outcomes", "complications", "analysis"}
    scores["article"] += 2 * _count_occurrences(text, article_tokens_primary)
    scores["article"] += _count_occurrences(text, article_tokens_secondary)
    if any(token in pdf_path.name.lower() for token in {"study", "research", "trial", "article"}):
        scores["article"] += 2
    if "materials and methods" in text or "study design" in text:
        scores["article"] += 4

    # Book chapter signals
    book_tokens_primary = {"contents", "introduction", "etiology", "management", "conclusion"}
    scores["textbook_chapter"] += 2 * _count_occurrences(text, book_tokens_primary)
    if any("chapter" in title for title in section_titles):
        scores["textbook_chapter"] += 5
    if "treatment of" in pdf_path.name.lower() or "chapter" in pdf_path.name.lower():
        scores["textbook_chapter"] += 3

    # Normalize by document size to prevent bias from long manuals.
    doc_length = max(len(lines), 1)
    for key in scores:
        scores[key] /= doc_length / 500  # scale across documents

    best_label = max(scores.items(), key=lambda item: item[1])[0]

    return best_label
