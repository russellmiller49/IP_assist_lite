# src/index/chunker_v2.py
"""
Advanced chunking system with policy-driven behavior
Implements sentence-safe packing, table coalescing, and quality gates
"""
from __future__ import annotations
import re, json, hashlib, logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Callable

logger = logging.getLogger(__name__)

# ---------- Policy ----------
@dataclass
class ChunkPolicy:
    target_tokens: int = 300
    max_tokens: int = 500
    min_tokens: int = 80
    overlap_tokens: int = 45
    ensure_sentence_boundary: bool = True
    drop_if_short: int = 15
    keep_section_intact: bool = False
    pack_rows: int = 0
    bullet_join: bool = False
    drop_patterns: Tuple[re.Pattern, ...] = ()
    version: str = "2"

def load_policy(yaml_path: Path) -> Tuple[ChunkPolicy, Dict[str, ChunkPolicy]]:
    import yaml
    cfg = yaml.safe_load(Path(yaml_path).read_text())
    def compile_patterns(items): 
        return tuple(re.compile(p) for p in items or [])
    base = cfg.get("default", {})
    base_cp = ChunkPolicy(
        target_tokens=base.get("target_tokens", 300),
        max_tokens=base.get("max_tokens", 500),
        min_tokens=base.get("min_tokens", 80),
        overlap_tokens=base.get("overlap_tokens", 45),
        ensure_sentence_boundary=base.get("ensure_sentence_boundary", True),
        drop_if_short=base.get("drop_if_short", 15),
        drop_patterns=compile_patterns(base.get("drop_patterns")),
        version=str(cfg.get("version", "2"))
    )
    overrides = {}
    for sec, o in (cfg.get("section_overrides") or {}).items():
        tmp = ChunkPolicy(
            target_tokens=o.get("target_tokens", base_cp.target_tokens),
            max_tokens=o.get("max_tokens", base_cp.max_tokens),
            min_tokens=o.get("min_tokens", base_cp.min_tokens),
            overlap_tokens=o.get("overlap_tokens", base_cp.overlap_tokens),
            ensure_sentence_boundary=o.get("ensure_sentence_boundary", base_cp.ensure_sentence_boundary),
            drop_if_short=o.get("drop_if_short", base_cp.drop_if_short),
            keep_section_intact=o.get("keep_section_intact", False),
            pack_rows=o.get("pack_rows", 0),
            bullet_join=o.get("bullet_join", False),
            drop_patterns=base_cp.drop_patterns,  # inherit base
            version=base_cp.version
        )
        overrides[sec] = tmp
    return base_cp, overrides

# ---------- Token length ----------
def make_token_len_fn(model_name: Optional[str] = None) -> Callable[[str], int]:
    tok = None
    if model_name:
        try:
            from transformers import AutoTokenizer
            tok = AutoTokenizer.from_pretrained(model_name, use_fast=True)
        except Exception:
            tok = None
    if tok:
        return lambda s: len(tok.encode(s, add_special_tokens=False))
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return lambda s: len(enc.encode(s))
    except Exception:
        return lambda s: max(1, len(s) // 4)

# ---------- Sentence segmentation ----------
def make_sentence_splitter() -> Callable[[str], List[str]]:
    try:
        import spacy
        nlp = spacy.blank("en")
        nlp.add_pipe("sentencizer")
        # Increase max_length to handle large documents
        nlp.max_length = 2000000  # 2M characters
        return lambda t: [s.text.strip() for s in nlp(t).sents if s.text.strip()]
    except Exception:
        pass
    
    try:
        import nltk
        nltk.download("punkt", quiet=True)
        from nltk.tokenize import sent_tokenize
        return lambda t: [s.strip() for s in sent_tokenize(t) if s.strip()]
    except Exception:
        pass
    
    # Fallback: simple regex-based splitter
    def simple_sent_split(text):
        # Basic sentence splitting on punctuation + space + capital
        # This is a simplified pattern that avoids complex lookbehinds
        sentences = []
        current = []
        
        # Split by periods, exclamations, questions
        parts = re.split(r'([.!?]+)', text)
        
        for i in range(0, len(parts)-1, 2):
            if i+1 < len(parts):
                sent = parts[i] + parts[i+1]
                sent = sent.strip()
                if sent:
                    sentences.append(sent)
        
        # Handle last part if it exists
        if len(parts) % 2 == 1 and parts[-1].strip():
            sentences.append(parts[-1].strip())
            
        return [s for s in sentences if s]
    
    return simple_sent_split

# ---------- Cleaning ----------
def preclean(text: str, patterns: Tuple[re.Pattern, ...]) -> str:
    lines = []
    for ln in text.splitlines():
        if any(p.search(ln) for p in patterns):
            continue
        lines.append(ln)
    out = "\n".join(lines)
    out = re.sub(r"(\w)-\n(\w)", r"\1\2", out)  # dehyphen
    out = re.sub(r"[ \t]+", " ", out)
    out = re.sub(r"\s+\n", "\n", out)
    out = out.replace("\u00a0", " ")
    return out.strip()

def is_garble(s: str) -> bool:
    return bool(re.fullmatch(r"(?:/C\d{2,3}){6,}", s.strip()))

def normalize_for_hash(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip().lower()
    # Replace smart quotes with regular quotes
    s = s.replace('"', '"').replace('"', '"').replace(''', "'").replace(''', "'")
    return s

# ---------- Chunking core ----------
@dataclass
class Chunk:
    text: str
    start: int
    end: int
    token_count: int
    index: int
    issues: List[str]

def pack_sentences(sentences: List[Tuple[str,int,int]],
                   policy: ChunkPolicy, tlen: Callable[[str], int]) -> List[Chunk]:
    chunks: List[Chunk] = []
    i = 0
    idx = 0
    while i < len(sentences):
        buf, start_char, end_char, toks, issues = [], sentences[i][1], sentences[i][2], 0, []
        j = i
        while j < len(sentences):
            s, s0, s1 = sentences[j]
            stoks = tlen(s)
            if toks + stoks > policy.max_tokens and buf:
                break
            buf.append(s)
            toks += stoks
            end_char = s1
            if toks >= policy.target_tokens:
                break
            j += 1
        
        # Calculate overlap for next chunk
        if buf and policy.overlap_tokens > 0 and j < len(sentences) - 1:
            ov, k = 0, len(buf) - 1
            while k >= 0 and ov < policy.overlap_tokens:
                ov += tlen(buf[k])
                k -= 1
            next_i = max(i + 1, i + (k + 1))
        else:
            next_i = j + 1
        
        txt = " ".join(buf).strip()
        if not txt:
            i = next_i
            continue
            
        # Check for issues
        if not re.search(r'[.!?]"?\s*$', txt) and policy.ensure_sentence_boundary:
            issues.append("mid_sentence_end")
        if is_garble(txt): 
            issues.append("garbled_pdf")
        if tlen(txt) < policy.min_tokens and len(buf) == 1:
            issues.append("very_short")
            
        chunks.append(Chunk(text=txt, start=start_char, end=end_char,
                            token_count=toks, index=idx, issues=issues))
        idx += 1
        i = next_i
    return chunks

def coalesce_table_rows(rows: List[str], policy: ChunkPolicy,
                        tlen: Callable[[str], int]) -> List[str]:
    if policy.pack_rows <= 1:
        return rows
    out, cur = [], []
    for r in rows:
        cur.append(r.strip())
        if len(cur) >= policy.pack_rows:
            out.append("; ".join(cur))
            cur = []
    if cur:
        out.append("; ".join(cur))
    return out

# ---------- Public API ----------
def chunk_document(doc: Dict, policy_base: ChunkPolicy,
                   overrides: Dict[str, ChunkPolicy],
                   tlen: Callable[[str], int]) -> List[Dict]:
    sec_type = doc.get("section_type", "general")
    policy = overrides.get(sec_type, policy_base)

    raw_text = doc.get("text", "")
    text = preclean(raw_text, policy.drop_patterns)
    if not text:
        return []

    # Handle table rows specially
    if sec_type == "table_row":
        rows = [ln for ln in text.splitlines() if ln.strip()]
        rows = coalesce_table_rows(rows, policy, tlen)
        text = "\n".join(rows)

    # Split into sentences
    splitter = make_sentence_splitter()
    sentences, pos = [], 0
    for sent in splitter(text):
        start = text.find(sent, pos)
        if start == -1:
            start = pos
        end = start + len(sent)
        sentences.append((sent, start, end))
        pos = end

    # Pack sentences into chunks
    chunks = pack_sentences(sentences, policy, tlen)

    # Deduplicate
    seen = set()
    out = []
    for ch in chunks:
        norm = normalize_for_hash(ch.text)
        h = hashlib.md5(norm.encode()).hexdigest()
        if h in seen:
            ch.issues.append("duplicate")
            continue
        seen.add(h)
        
        chunk_dict = {
            "doc_id": doc.get("doc_id", ""),
            "section_type": sec_type,
            "chunk_id": f"{doc.get('doc_id', '')}:{ch.index}",
            "index_in_doc": ch.index,
            "text": ch.text,
            "token_count": ch.token_count,
            "start_char": ch.start,
            "end_char": ch.end,
            "policy_version": policy.version,
            "issues": ch.issues,
        }
        
        # Add metadata from document
        meta = doc.get("meta", {})
        if meta:
            chunk_dict.update(meta)
            
        out.append(chunk_dict)
    return out

def chunk_stream(docs: Iterable[Dict], policy_path: Path,
                 tokenizer_model: Optional[str] = None,
                 out_path: Optional[Path] = None) -> List[Dict]:
    base, overrides = load_policy(policy_path)
    tlen = make_token_len_fn(tokenizer_model)
    all_chunks, qa_rows = [], []
    
    for doc in docs:
        chunks = chunk_document(doc, base, overrides, tlen)
        for c in chunks:
            qa_rows.append({
                "doc_id": c["doc_id"],
                "section_type": c["section_type"],
                "index_in_doc": c["index_in_doc"],
                "token_count": c["token_count"],
                "ends_with_punct": not ("mid_sentence_end" in c["issues"]),
                "issues": "|".join(c["issues"]),
                "text_preview": (c["text"][:200] + "…") if len(c["text"]) > 200 else c["text"]
            })
        all_chunks.extend(chunks)

    if out_path:
        # Write chunks
        with out_path.open("w", encoding="utf-8") as f:
            for c in all_chunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        
        # Write QA CSV
        if qa_rows:
            import csv
            qa_path = out_path.with_suffix(".qa.csv")
            with qa_path.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(qa_rows[0].keys()))
                w.writeheader()
                w.writerows(qa_rows)
            logger.info("Wrote %s and %s", out_path, qa_path)
    
    return all_chunks

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--in_jsonl", type=Path, required=True)
    p.add_argument("--out_jsonl", type=Path, required=True)
    p.add_argument("--policy", type=Path, default=Path("configs/chunking.yaml"))
    p.add_argument("--tokenizer", type=str, default=None,
                   help="HF model name or leave empty for heuristic/tiktoken")
    args = p.parse_args()
    
    # Load documents
    docs = []
    with args.in_jsonl.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                docs.append(json.loads(line))
    
    # Process chunks
    chunk_stream(docs, args.policy, tokenizer_model=args.tokenizer, out_path=args.out_jsonl)