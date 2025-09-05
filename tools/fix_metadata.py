#!/usr/bin/env python3
"""
Fix metadata issues in processed JSONs:
- Ensure top-level doc_id/year/h_level
- authority_tier from book/filename mapping
- doc_type correction: guideline / rct / book_chapter
- Repair headings; rebuild content if empty
- Dry-run mode with human-readable report
"""

from __future__ import annotations
import argparse, json, re, shutil, sys
from pathlib import Path
from typing import Dict, Any, List

import yaml

GUIDE = None
HEAD_FIX = None

GUIDELINE_TITLE = re.compile(r"(guideline|consensus|expert panel|position statement|practice guideline|evidence[- ]informed|recommendation)", re.I)
GUIDELINE_BODY = re.compile(r"(multidisciplinary panel|evidence grade|consensus[- ]based|best practice statement|GRADE)", re.I)
RCT_HINTS = re.compile(r"(randomi[sz]ed|randomized controlled|double[- ]blind|placebo[- ]controlled|trial\b)", re.I)

def load_yaml(p: Path) -> dict:
    return yaml.safe_load(p.read_text(encoding="utf-8"))

def normalize_headings(text: str) -> str:
    if not text: return ""
    lines = []
    for line in text.splitlines():
        if line.startswith("## "):
            h = line[3:]
            # exact map first
            for bad, good in HEAD_FIX["fixes"].items():
                if h.strip().startswith(bad):
                    line = "## " + good
                    break
            # ensure initial capitalization
            h2 = line[3:]
            if h2 and not h2[0].isupper():
                line = "## " + h2[0].upper() + h2[1:]
        lines.append(line)
    return "\n".join(lines)

def ensure_content(data: Dict[str, Any]) -> str:
    content = data.get("content")
    if isinstance(content, str) and len(content) >= 400:
        return content
    parts: List[str] = []
    for sec in data.get("sections") or []:
        if isinstance(sec, dict):
            t = sec.get("title")
            c = sec.get("content") or sec.get("text")
            if t: parts.append(f"## {t}")
            if c: parts.append(c)
    return "\n\n".join(parts)

def guess_authority_tier(fname: str, book: str, rules: dict) -> str:
    f = fname.lower()
    b = (book or "").lower()
    for tier, cfg in rules["authority_map"].items():
        if any(s in b for s in cfg.get("book_substrings", [])): return tier
        if any(f.startswith(pfx) for pfx in cfg.get("filename_prefixes", [])): return tier
    return "A4"

def detect_doc_type(title: str, abstract: str, content: str, current: str, expected_authority: str) -> tuple:
    """
    Detect document type with proper precedence.
    Returns (doc_type, forced_h_level) where forced_h_level can be None
    """
    # CRITICAL: Use title+abstract ONLY for classification (not body to avoid false positives)
    title_abs = f"{title}\n{abstract or ''}".lower()
    body = (content or "").lower()[:2000]  # limit body peeking for fallbacks only
    
    # 1) Guideline/consensus (highest priority)
    if re.search(r"\b(guideline|consensus|expert panel|position statement|practice guideline|recommendation)\b", title_abs):
        return "guideline", "H1"
    # Organization guidelines (only when paired with guideline words)
    if re.search(r"\b(fleischner|bts|ers|esge|ests|aabip|accp|chest)\s+(guideline|statement|recommendation|consensus)", title_abs):
        return "guideline", "H1"
    
    # 2) Systematic review / meta-analysis / state of the art
    if re.search(r"\b(systematic review|meta[- ]analysis|state[- ]of[- ]the[- ]art)\b", title_abs):
        return "systematic_review", "H1"
    
    # 3) Review articles (generic reviews, not systematic)
    if re.search(r"\breview\b", title_abs) and not re.search(r"\brandomi[sz]ed\b|\btrial\b", title_abs):
        return "narrative_review", "H3"
    
    # 4) RCT/trial — ONLY in title/abstract, not body
    if re.search(r"\brandomi[sz]ed\b|\brct\b|\brandomi[sz]ed controlled trial\b", title_abs):
        return "rct", None  # keep existing H-level if set; infer later if missing
    
    # 5) Books → chapters by authority tier
    if expected_authority in ("A1","A2","A3"):
        return "book_chapter", "H3"
    
    # 6) Light body hints for observational/reporting (fallback only)
    if re.search(r"\b(cohort|prospective|retrospective|multicenter|multicentre)\b", body):
        return "cohort", "H2"  # H2 for prospective cohorts
    if re.search(r"\bcase series\b", body):
        return "case_series", "H4"
    if re.search(r"\breview\b", body):
        return "narrative_review", "H3"
    
    return current or "journal_article", None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--output", required=False, type=Path, help="If omitted, overwrite input")
    ap.add_argument("--rules", default=Path("configs/doc_type_rules.yaml"), type=Path)
    ap.add_argument("--headings", default=Path("configs/heading_fixes.yaml"), type=Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", default="fix_report.csv", type=str)
    args = ap.parse_args()

    global GUIDE, HEAD_FIX
    GUIDE = load_yaml(args.rules)
    HEAD_FIX = load_yaml(args.headings)

    in_dir = args.input
    out_dir = args.output or in_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    report_rows = []
    files = sorted(in_dir.glob("*.json"))
    for fp in files:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as e:
            report_rows.append([fp.name, "load_error", str(e)])
            continue

        changes = []
        meta = data.get("metadata") or {}
        title = data.get("title") or meta.get("title") or ""
        abstract = data.get("abstract") or meta.get("abstract") or ""
        book  = meta.get("book") or data.get("book") or ""

        # doc_id
        if "doc_id" not in data:
            did = meta.get("document_id") or data.get("id") or fp.stem
            data["doc_id"] = did
            changes.append("set:doc_id")

        # year - improved extraction
        if not isinstance(data.get("year"), int):
            y = meta.get("year") or data.get("year")
            if isinstance(y, str):
                # Extract 4-digit year from string
                if y[:4].isdigit():
                    data["year"] = int(y[:4])
                    changes.append("extract:year")
                elif re.search(r'\b(19\d{2}|20\d{2})\b', y):
                    match = re.search(r'\b(19\d{2}|20\d{2})\b', y)
                    data["year"] = int(match.group(1))
                    changes.append("extract:year")
            elif isinstance(y, (int, float)):
                data["year"] = int(y)
                changes.append("promote:year")

        # h_level
        h = data.get("h_level") or meta.get("evidence_level")
        if h not in ("H1","H2","H3","H4"):
            # infer weakly: guideline→H1; RCT→H1/H2; book chapter→H3
            content_sample = (data.get("content") or "")[:4000]
            if GUIDELINE_TITLE.search(title) or GUIDELINE_BODY.search(content_sample):
                data["h_level"] = "H1"
                changes.append("infer:h_level=H1(guideline)")
            elif RCT_HINTS.search(f"{title}\n{content_sample}"):
                data["h_level"] = "H1"  # generous; you can downgrade to H2 if single center nonblinded
                changes.append("infer:h_level=H1(rct)")
            else:
                data["h_level"] = "H3"
                changes.append("infer:h_level=H3(default)")
        else:
            data["h_level"] = h

        # authority_tier
        at_expected = guess_authority_tier(fp.name, book, GUIDE)
        at_current = meta.get("authority_tier") or data.get("authority_tier")
        if at_current != at_expected:
            meta["authority_tier"] = at_expected
            data["authority_tier"] = at_expected  # redundant but harmless
            changes.append(f"set:authority_tier->{at_expected}")

        # doc_type with improved precedence
        doc_type_cur = (meta.get("doc_type") or data.get("doc_type") or "").lower()
        content_all = data.get("content") or ""
        doc_type_new, forced_h = detect_doc_type(title, abstract, content_all, doc_type_cur, at_expected)
        
        if doc_type_new != doc_type_cur:
            meta["doc_type"] = doc_type_new
            changes.append(f"set:doc_type->{doc_type_new}")
        
        # Apply forced H level if specified
        if forced_h:
            if data.get("h_level") != forced_h:
                data["h_level"] = forced_h
                changes.append(f"force:h_level={forced_h}({doc_type_new})")
        # ALWAYS ensure guidelines and systematic reviews are H1
        elif doc_type_new in ("guideline", "systematic_review"):
            if data.get("h_level") != "H1":
                data["h_level"] = "H1"
                changes.append(f"force:h_level=H1({doc_type_new})")
        # Set default H-levels for other types if missing
        elif data.get("h_level") not in ("H1", "H2", "H3", "H4"):
            if doc_type_new == "rct":
                data["h_level"] = "H2"
                changes.append(f"set:h_level=H2({doc_type_new})")
            elif doc_type_new == "cohort":
                data["h_level"] = "H2"
                changes.append(f"set:h_level=H2({doc_type_new})")
            elif doc_type_new in ("narrative_review", "book_chapter"):
                data["h_level"] = "H3"
                changes.append(f"set:h_level=H3({doc_type_new})")
            elif doc_type_new == "case_series":
                data["h_level"] = "H4"
                changes.append(f"set:h_level=H4({doc_type_new})")

        # content
        fixed_content = ensure_content(data)
        fixed_content = normalize_headings(fixed_content)
        if fixed_content and fixed_content != data.get("content"):
            data["content"] = fixed_content
            changes.append("rebuild:content")

        # persist meta
        data["metadata"] = meta

        # write / report
        if args.dry_run:
            report_rows.append([fp.name, "|".join(changes) if changes else "noop", meta.get("doc_type",""), data.get("h_level",""), meta.get("authority_tier",""), data.get("year","")])
        else:
            out_file = out_dir / fp.name if out_dir else fp
            out_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            report_rows.append([fp.name, "|".join(changes) if changes else "noop", meta.get("doc_type",""), data.get("h_level",""), meta.get("authority_tier",""), data.get("year","")])

    # write report
    header = "filename,changes,doc_type,h_level,authority_tier,year\n"
    out_report = out_dir / args.report
    out_report.write_text(header + "\n".join(",".join(map(lambda x: str(x) if x is not None else "", r)) for r in report_rows), encoding="utf-8")
    print(f"Wrote report: {out_report}")
    print("Done.")

if __name__ == "__main__":
    main()