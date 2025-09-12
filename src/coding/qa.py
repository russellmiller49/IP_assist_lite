"""Q&A module for code rationale questions."""

import re
from typing import Dict, Any, List, Tuple, Optional
from .schema import Case, CodeBundle

CODE_RE = re.compile(r"\+?\b\d{5}\b")  # matches 31652, +31627, 99152, etc.

def build_context(case: Case, bundle: CodeBundle, kb=None) -> Dict[str, Any]:
    """Create a lightweight, serializable context for follow-up Q&A."""
    idx = {cl.code: cl for cl in (bundle.professional + bundle.facility)}
    return {
        "codes": list(idx.keys()),
        "by_code": {k: {
            "rationale": v.rationale,
            "mods": v.modifiers,
            "qty": v.quantity,
            "desc": v.description or "",
        } for k, v in idx.items()},
        "opps": bundle.opps_notes,
        "doc_gaps": bundle.documentation_gaps,
        "warnings": bundle.warnings,
        "pcs": bundle.icd10_pcs_suggestions,
        "raw_report": case.report_text,
        "kb_version": (kb.version_info() if kb else ""),
    }

def _explain_code(code: str, ctx: Dict[str, Any]) -> Optional[str]:
    b = ctx["by_code"].get(code)
    if not b: return None
    bits = [f"**{code}**"]
    if b["desc"]: bits.append(b["desc"])
    if b["rationale"]: bits.append(f"Why: {b['rationale']}")
    if b["mods"]: bits.append(f"Modifiers: {', '.join(b['mods'])}")
    if b["qty"] and b["qty"] != 1: bits.append(f"Quantity: {b['qty']}")
    return " — ".join(bits)

def _best_topics(question: str) -> List[str]:
    q = question.lower()
    out = []
    if "opps" in q or "facility" in q or "packag" in q: out.append("opps")
    if "pcs" in q or "icd-10" in q or "icd10" in q: out.append("pcs")
    if "document" in q or "start" in q or "stop" in q or "observer" in q: out.append("doc_gaps")
    if "ncci" in q or "bundle" in q or "modifier" in q or "-59" in q or "distinct" in q: out.append("warnings")
    return out

def answer(question: str, ctx: Dict[str, Any]) -> str:
    """Answer 'why this code', OPPS/PCS/doc/warning questions using structured context."""
    found = CODE_RE.findall(question)
    parts = []
    # Code-specific explanations
    if found:
        for c in found:
            exp = _explain_code(c, ctx)
            if exp: parts.append(exp)
        if not parts:
            parts.append("I didn't find those codes in the current analysis.")
    # Topic summaries
    for t in _best_topics(question):
        if t == "opps" and ctx["opps"]:
            parts.append("**OPPS notes:** " + " ".join(ctx["opps"]))
        if t == "pcs" and ctx["pcs"]:
            parts.append("**ICD‑10‑PCS suggestions:** " + ", ".join(ctx["pcs"]))
        if t == "doc_gaps" and ctx["doc_gaps"]:
            parts.append("**Documentation checks:** " + "; ".join(ctx["doc_gaps"]))
        if t == "warnings" and ctx["warnings"]:
            parts.append("**NCCI/Compliance warnings:** " + " | ".join(ctx["warnings"]))
    # Fallback: if no codes nor topics matched, give a helpful summary
    if not parts:
        parts.append("You can ask about a specific code (e.g., 'Why 31653?') or topics like OPPS packaging, PCS, documentation, or NCCI/modifiers.")
        parts.append("Here are the codes in context: " + ", ".join(ctx["codes"]))
    if ctx.get("kb_version"):
        parts.append(f"_KB version: {ctx['kb_version']}_")
    return "\n\n".join(parts)