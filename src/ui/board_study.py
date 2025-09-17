"""Utilities for the board study module in the Gradio UI."""
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Any

OPTION_RE = re.compile(r"^([A-H])\.\s*(.+)$")
QUESTION_RE = re.compile(r"^Q(\d+)$", re.IGNORECASE)


@dataclass
class BoardQuestion:
    qid: str
    category: str
    prompt: str
    options: Dict[str, str]
    answer: str
    explanation: str


def _normalise_lines(path: Path) -> List[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return [line.strip() for line in text.splitlines()]


def load_board_bank(path: Path | None = None) -> List[BoardQuestion]:
    path = path or Path("data/knowledge_base/complete board review data set.txt")
    if not path.exists():
        return []

    lines = _normalise_lines(path)
    questions: List[BoardQuestion] = []
    category = "General"
    i = 0
    total = len(lines)

    while i < total:
        line = lines[i]
        if not line:
            i += 1
            continue
        # Skip high-level header
        if line.lower().startswith("interventional pulmonology"):
            i += 1
            continue

        if QUESTION_RE.match(line):
            qid = line.upper()
            i += 1
            stem_parts: List[str] = []
            while i < total:
                current = lines[i]
                if not current:
                    stem_parts.append("")
                    i += 1
                    continue
                if OPTION_RE.match(current) or QUESTION_RE.match(current) or current.lower().startswith("correct answer"):
                    break
                if current.lower().startswith("explanation"):
                    break
                if not stem_parts and current.lower().startswith("category:"):
                    category = current.split(":", 1)[1].strip() or category
                    i += 1
                    continue
                stem_parts.append(current)
                i += 1
            options: Dict[str, str] = {}
            while i < total:
                current = lines[i]
                if not current:
                    i += 1
                    continue
                opt_match = OPTION_RE.match(current)
                if not opt_match:
                    break
                letter, text = opt_match.groups()
                options[letter.upper()] = text.strip()
                i += 1

            answer = ""
            if i < total and lines[i].lower().startswith("correct answer"):
                answer = lines[i].split(":", 1)[1].strip().split()[0].upper()
                i += 1

            explanation_parts: List[str] = []
            if i < total and lines[i].lower().startswith("explanation"):
                explanation = lines[i].split(":", 1)[1].strip()
                explanation_parts.append(explanation)
                i += 1
                while i < total:
                    current = lines[i]
                    if not current:
                        i += 1
                        if explanation_parts and explanation_parts[-1]:
                            explanation_parts.append("")
                        continue
                    if QUESTION_RE.match(current):
                        break
                    if OPTION_RE.match(current):
                        break
                    if current.lower().startswith("correct answer"):
                        break
                    # Stop if we hit a new category header (heuristic: no punctuation and title case)
                    if not explanation_parts or explanation_parts[-1] == "":
                        maybe_header = current.replace("&", "").replace("-", "").strip()
                        if maybe_header and maybe_header == maybe_header.title() and len(maybe_header.split()) <= 6:
                            break
                    explanation_parts.append(current)
                    i += 1

            prompt = "\n".join(part for part in stem_parts if part is not None).strip()
            explanation_text = "\n".join(part for part in explanation_parts if part is not None).strip()
            questions.append(
                BoardQuestion(
                    qid=qid,
                    category=category,
                    prompt=prompt,
                    options=options,
                    answer=answer,
                    explanation=explanation_text,
                )
            )
            continue

        # Treat as category header
        category = line
        i += 1

    return questions


BOARD_QUESTIONS: List[BoardQuestion] = load_board_bank()
BOARD_CATEGORIES: List[str] = sorted({q.category for q in BOARD_QUESTIONS})


def pick_question(category: Optional[str] = None) -> Optional[BoardQuestion]:
    if not BOARD_QUESTIONS:
        return None
    if category and category != "All Topics":
        pool = [q for q in BOARD_QUESTIONS if q.category == category]
        if not pool:
            return None
    else:
        pool = BOARD_QUESTIONS
    return random.choice(pool)


def question_to_markdown(question: BoardQuestion) -> str:
    header = f"**{question.qid}**"
    if question.category:
        header += f" · {question.category}"
    body = question.prompt.strip()
    return f"{header}\n\n{body}" if body else header


def feedback_markdown(question: BoardQuestion, selected: str, correct: bool) -> str:
    correct_text = question.options.get(question.answer, "")
    selected_text = question.options.get(selected, "")
    lines = []
    if correct:
        lines.append(f"✅ Correct! **{question.answer}. {correct_text}**")
    else:
        lines.append(f"❌ {selected}. {selected_text} is not correct.")
        lines.append(f"\n**Correct Answer:** {question.answer}. {correct_text}")
    if question.explanation:
        lines.append("\n---\n")
        lines.append(question.explanation)
    return "\n".join(lines).strip()


def initialise_state(state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    state = state or {}
    stats = state.get("stats") or {"attempts": 0, "correct": 0}
    state["stats"] = {"attempts": int(stats.get("attempts", 0)), "correct": int(stats.get("correct", 0))}
    if "current" not in state:
        state["current"] = None
    return state


def stats_summary(state: Optional[Dict[str, Any]] = None) -> str:
    state = initialise_state(state)
    attempts = state["stats"].get("attempts", 0)
    correct = state["stats"].get("correct", 0)
    pct = (correct / attempts * 100) if attempts else 0.0
    return f"Score: {correct} / {attempts} ({pct:.0f}%)"


def prepare_next_question(category: Optional[str], state: Optional[Dict[str, Any]] = None) -> Tuple[Optional[BoardQuestion], Optional[str], Dict[str, Any]]:
    state = initialise_state(state)
    if not BOARD_QUESTIONS:
        return None, (
            "No board study questions found. Add `data/knowledge_base/complete board review data set.txt` "
            "and rerun the knowledge base prep pipeline."
        ), state

    request_category = category if category and category != "All Topics" else None
    question = pick_question(request_category)
    if not question:
        return None, "No questions are available for the selected topic.", state

    state["current"] = {
        "qid": question.qid,
        "category": question.category,
        "prompt": question.prompt,
        "answer": question.answer,
        "explanation": question.explanation,
        "options": dict(question.options),
        "answered": False,
    }
    return question, None, state


def evaluate_answer(selection: Optional[str], state: Optional[Dict[str, Any]] = None) -> Tuple[Optional[BoardQuestion], str, Dict[str, Any], Optional[str]]:
    state = initialise_state(state)
    current = state.get("current")
    if not current:
        return None, "Select 'Next Question' to begin.", state, None

    if not selection:
        return None, "Please choose an answer before checking.", state, None

    selected_letter = selection.split(".", 1)[0].strip().upper()
    correct_letter = (current.get("answer") or "").strip().upper()

    question = BoardQuestion(
        qid=current.get("qid", "Q"),
        category=current.get("category", ""),
        prompt=current.get("prompt", ""),
        options=current.get("options", {}),
        answer=correct_letter,
        explanation=current.get("explanation", ""),
    )

    if selected_letter not in question.options:
        return None, "Invalid selection. Please choose one of the listed answers.", state, None

    is_correct = selected_letter == correct_letter

    if not current.get("answered"):
        stats = state["stats"]
        stats["attempts"] += 1
        if is_correct:
            stats["correct"] += 1
        current["answered"] = True
    current["selected"] = selected_letter

    feedback = feedback_markdown(question, selected_letter, is_correct)
    return question, feedback, state, selected_letter


def generate_detailed_rationale(
    question: BoardQuestion,
    selected_letter: str,
    retriever: Any,
    generator: Callable[..., str],
    *,
    top_k: int = 8,
    temperature: float = 0.2,
    max_output_tokens: int = 900,
) -> str:
    if not hasattr(retriever, "retrieve"):
        return ""

    query_lines = [question.prompt.strip()]
    for letter, text in question.options.items():
        query_lines.append(f"{letter}. {text}")
    query = "\n".join(query_lines)

    passages: List[str] = []
    try:
        results = retriever.retrieve(
            query=query,
            top_k=top_k,
            use_reranker=True,
        )
        for res in results[:top_k]:
            meta = (
                f"Source: {getattr(res, 'doc_id', '')} · {getattr(res, 'section_title', '')} "
                f"· {getattr(res, 'authority_tier', '?')}/{getattr(res, 'evidence_level', '?')} "
                f"({getattr(res, 'year', 'n/a')})"
            )
            passages.append(f"{getattr(res, 'text', '')}\n{meta}")
    except Exception:
        return ""

    if not passages:
        return ""

    options_block = "\n".join(f"{letter}. {text}" for letter, text in question.options.items())
    prompt = (
        "You are an interventional pulmonology board review tutor. "
        "Using the cited passages, explain why the correct option is right and why each other option is wrong. "
        "Lead with the correct answer, then discuss the remaining choices individually. "
        "Keep the focus on clinical reasoning and cite supporting passages as [#]."
    )

    analysis_question = (
        f"Board question stem:\n{question.prompt}\n\nOptions:\n{options_block}\n\n"
        f"Correct answer key: {question.answer}. Selected answer: {selected_letter}."
    )

    try:
        return generator(
            question=f"{prompt}\n\n{analysis_question}",
            passages=passages,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
    except Exception:
        return ""


__all__ = [
    "BOARD_CATEGORIES",
    "BOARD_QUESTIONS",
    "BoardQuestion",
    "feedback_markdown",
    "pick_question",
    "question_to_markdown",
    "initialise_state",
    "stats_summary",
    "prepare_next_question",
    "evaluate_answer",
    "generate_detailed_rationale",
]
