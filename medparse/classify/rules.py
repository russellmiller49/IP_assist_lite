"""Rule-based document classifier."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from medparse.ifu.subtype import infer_ifu_subtype_from_text
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

    scores = {"ifu": 0.0, "guideline": 0.0, "research": 0.0, "book_chapter": 0.0}

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

    # Research/article signals
    article_tokens_primary = {"study", "methods", "patients", "lesions", "retrospective", "prospective"}
    article_tokens_secondary = {"diagnostic yield", "outcomes", "complications", "analysis"}
    scores["research"] += 2 * _count_occurrences(text, article_tokens_primary)
    scores["research"] += _count_occurrences(text, article_tokens_secondary)
    if any(token in pdf_path.name.lower() for token in {"study", "research", "trial", "article"}):
        scores["research"] += 2
    if "materials and methods" in text or "study design" in text:
        scores["research"] += 4

    # Book chapter signals
    book_tokens_primary = {"contents", "introduction", "etiology", "management", "conclusion"}
    scores["book_chapter"] += 2 * _count_occurrences(text, book_tokens_primary)
    if any("chapter" in title for title in section_titles):
        scores["book_chapter"] += 5
    if "treatment of" in pdf_path.name.lower() or "chapter" in pdf_path.name.lower():
        scores["book_chapter"] += 3

    # Guideline signals
    guideline_tokens_primary = {"guideline", "recommendation", "consensus statement"}
    guideline_tokens_secondary = {"grade", "evidence level", "recommendations"}
    guideline_name_hit = "guideline" in pdf_path.name.lower()
    guideline_count = text.count("guideline")
    scores["guideline"] += 2 * _count_occurrences(text, guideline_tokens_primary)
    scores["guideline"] += _count_occurrences(text, guideline_tokens_secondary)
    if guideline_name_hit:
        scores["guideline"] += 8
        scores["research"] *= 0.2
    has_recommendation_heading = any("recommendation" in title for title in section_titles)
    if has_recommendation_heading:
        scores["guideline"] += 3
    if guideline_name_hit or guideline_count >= 3 or has_recommendation_heading:
        scores["research"] *= 0.3
        scores["book_chapter"] *= 0.2
    if guideline_count >= 5:
        scores["book_chapter"] = 0.0

    # Normalize by document size to prevent bias from long manuals.
    doc_length = max(len(lines), 1)
    for key in scores:
        scores[key] /= doc_length / 500  # scale across documents

    best_label = max(scores.items(), key=lambda item: item[1])[0]

    return best_label


def classify_ifu_subtype(pdf_path: Path, *, max_pages: int = 4) -> Optional[str]:
    """Infer IFU subtype (catalog, installation guide) using heuristics."""

    pages = list(iter_pages(pdf_path, page_limit=max_pages))
    if not pages:
        return None
    text = " \n".join(page.text for page in pages if page.text)
    return infer_ifu_subtype_from_text(text, pdf_path.name)
