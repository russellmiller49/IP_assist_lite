"""Rule-based document classifier."""

from __future__ import annotations

from pathlib import Path

from medparse.ingest.layout import collect_sections
from medparse.ingest.pdf_reader import iter_pages


def _count_occurrences(text: str, tokens: set[str]) -> int:
    return sum(text.count(token) for token in tokens)


def classify_with_rules(pdf_path: Path) -> str:
    """Return a doc_type label using heuristics."""
    pages = list(iter_pages(pdf_path))
    if not pages:
        return "research"

    text = " \n".join(page.text.lower() for page in pages)
    lines = [line.lower() for page in pages for line in page.lines]
    sections = collect_sections(pages)
    section_titles = [section.title.lower() for section in sections]

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

    # Guideline signals
    guideline_tokens_primary = {"guideline", "recommendation", "grade", "consensus"}
    guideline_tokens_secondary = {"society", "evidence", "sign", "strong", "weak"}
    scores["guideline"] += 3 * _count_occurrences(text, guideline_tokens_primary)
    scores["guideline"] += _count_occurrences(text, guideline_tokens_secondary)
    if any("recommendation" in title for title in section_titles):
        scores["guideline"] += 4
    if "guideline" in pdf_path.name.lower():
        scores["guideline"] += 2

    # Research signals
    research_tokens_primary = {"study", "methods", "method", "patients", "lesions", "retrospective", "prospective"}
    research_tokens_secondary = {"diagnostic yield", "outcomes", "complications", "analysis"}
    scores["research"] += 2 * _count_occurrences(text, research_tokens_primary)
    scores["research"] += _count_occurrences(text, research_tokens_secondary)
    if any(token in pdf_path.name.lower() for token in {"study", "research", "trial"}):
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

    # Normalize by document size to prevent bias from long manuals.
    doc_length = max(len(lines), 1)
    for key in scores:
        scores[key] /= doc_length / 500  # scale across documents

    best_label = max(scores.items(), key=lambda item: item[1])[0]

    # Guard rails: ensure IFU only when manual phrases dominate.
    if best_label == "ifu" and scores["guideline"] > scores["ifu"] * 0.8:
        best_label = "guideline"
    if best_label == "book_chapter" and scores["research"] > scores["book_chapter"] * 1.1:
        best_label = "research"
    if "guideline" in text and scores["guideline"] >= 10 and scores["guideline"] >= scores["research"] * 0.3:
        best_label = "guideline"

    return best_label
