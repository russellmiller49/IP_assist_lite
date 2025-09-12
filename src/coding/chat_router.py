"""Routes general chat messages to/from coding module."""

import re
from typing import Dict, Tuple
from .kb import CodingKB
from .extractors import extract_case
from .rules import code_case
from .formatter import to_markdown
from .qa import build_context, answer as answer_q

TRIGGERS = [
    "code this", "coding for", "cpt code", "bill this",
    "procedure code", "what codes", "generate codes", "procedure report"
]
CODE_RE = re.compile(r"\+?\b\d{5}\b")

def maybe_route_to_coding(user_input: str) -> bool:
    u = user_input.lower()
    return any(t in u for t in TRIGGERS) or len(user_input) > 800  # heuristics: long pasted reports

def handle_first_pass(user_input: str, state: Dict) -> Tuple[str, Dict]:
    """Analyze a report, save context, and return markdown result."""
    kb = CodingKB()
    case = extract_case(user_input, kb, llm=None)
    bundle = code_case(case, kb)
    ctx = build_context(case, bundle, kb=kb)
    state = dict(state or {})
    state["coding_ctx"] = ctx
    md = to_markdown(bundle) + f"\n\n_KB: {kb.version_info()}_"
    return md, state

def maybe_answer_followup(user_input: str, state: Dict) -> Tuple[bool, str, Dict]:
    """If we have prior coding_ctx and the user asks why/OPPS/PCS/etc, answer from context."""
    state = dict(state or {})
    ctx = state.get("coding_ctx")
    if not ctx:
        return False, "", state
    q = user_input.lower()
    looks_like_followup = bool(CODE_RE.search(user_input)) or any(
        kw in q for kw in ["why", "opps", "pcs", "packag", "documentation", "ncci", "modifier", "-59"]
    )
    if not looks_like_followup:
        return False, "", state
    ans = answer_q(user_input, ctx)
    return True, ans, state

def clear_coding_context(state: Dict) -> Dict:
    """Clear coding context when switching topics."""
    state = dict(state or {})
    if "coding_ctx" in state:
        del state["coding_ctx"]
    return state