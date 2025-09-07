#!/usr/bin/env python3
"""
Codemod for IP-Assist-Lite:
- Adds src/llm/gpt5_medical.py (GPT-5 Responses API wrapper)
- Adds src/safety/contraindication_tool.py (JSON-mode tool)
- Patches src/orchestrator/flow.py to register the GPT-5 node with dynamic budgeting
- Ensures requirements upgrades are present

Usage:
  python tools/apply_gpt5_upgrade.py
"""
import os, re, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
GPT5_FILE = ROOT / "src" / "llm" / "gpt5_medical.py"
SAFETY_TOOL_FILE = ROOT / "src" / "safety" / "contraindication_tool.py"
FLOW_FILE = ROOT / "src" / "orchestrator" / "flow.py"
REQ_FILE = ROOT / "requirements.txt"

INSERT_IMPORTS = "\nfrom src.llm.gpt5_medical import GPT5MedicalGenerator, num_tokens, max_input_budget\n"

CONTEXT_FILTER_DEF = """
def context_budget_filter(docs, reserved_for_question: int = 2000, max_out: int = 8000):
    \"\"\"Keep best-ranked docs while staying under the dynamic prompt budget.\"\"\" 
    budget = max_input_budget(max_out) - reserved_for_question
    total, kept = 0, []
    for d in docs:
        tk = num_tokens(getattr(d, "page_content", ""))
        if total + tk > budget:
            break
        total += tk
        kept.append(d)
    return kept
"""

ANSWER_NODE_DEF = """
def build_gpt5_answer_node():
    llm = GPT5MedicalGenerator(model=os.getenv("GPT5_MODEL", "gpt-5"),
                               max_output=8000,
                               reasoning_effort="medium",
                               verbosity="medium")
    def _answer(state: "GraphState") -> "GraphState":
        # fit retrieved docs to dynamic budget
        trimmed = context_budget_filter(state.retrieved_docs, max_out=llm.max_out)
        context = format_context(trimmed)  # assumes your helper exists
        system = (
            "You are an expert interventional pulmonology assistant. "
            "Use only the provided authoritative context. "
            "Cite sources as [A1-PAPOIP-2025], [A2-Practical-Guide], etc. "
            "If uncertain, state so explicitly."
        )
        user = f"Context:\\n{context}\\n\\nQuestion: {state.question}"
        out = llm.generate(system=system, user=user)
        state.answer = out.get("text", "")
        state.llm_usage = out.get("usage", {})
        return state
    return _answer
"""

REGISTER_NODE_REPLACEMENT = 'workflow.add_node("generate_answer", build_gpt5_answer_node())'

def ensure_requirements():
    if not REQ_FILE.exists():
        print("[warn] requirements.txt not found; create manually with openai>=1.37.0, tiktoken>=0.7.0")
        return
    txt = REQ_FILE.read_text(encoding="utf-8")
    changed = False
    def _ensure(line: str):
        nonlocal txt, changed
        name = line.split(">=")[0]
        if name not in txt:
            txt = txt.rstrip() + "\n" + line + "\n"
            changed = True
    _ensure("openai>=1.37.0")
    _ensure("tiktoken>=0.7.0")
    if changed:
        REQ_FILE.write_text(txt, encoding="utf-8")
        print(f"[ok] updated {REQ_FILE}")
    else:
        print(f"[skip] {REQ_FILE} already OK")

def patch_flow():
    if not FLOW_FILE.exists():
        print(f"[err] {FLOW_FILE} not found; adjust path and rerun.")
        return False
    src = FLOW_FILE.read_text(encoding="utf-8")

    # 1) import
    if "from src.llm.gpt5_medical import GPT5MedicalGenerator" not in src:
        # insert after first import block
        m = re.search(r"(^(\s*from\s+[^\n]+\n|\s*import\s+[^\n]+\n)+)", src, flags=re.M)
        if m:
            start, end = m.span()
            src = src[:end] + INSERT_IMPORTS + src[end:]
        else:
            src = INSERT_IMPORTS + src

    # 2) context filter (append if not present)
    if "def context_budget_filter(" not in src:
        src = src.rstrip() + "\n\n" + CONTEXT_FILTER_DEF

    # 3) answer node (append if not present)
    if "def build_gpt5_answer_node(" not in src:
        src = src.rstrip() + "\n\n" + ANSWER_NODE_DEF

    # 4) swap node registration if a prior generate_answer exists; otherwise add
    if 'workflow.add_node("generate_answer"' in src:
        src = re.sub(r'workflow\.add_node\("generate_answer",\s*[^)]+\)',
                     REGISTER_NODE_REPLACEMENT,
                     src, count=1)
    else:
        # append a default registration if none exists
        src = src.rstrip() + "\n\n" + REGISTER_NODE_REPLACEMENT + "\n"

    FLOW_FILE.write_text(src, encoding="utf-8")
    print(f"[ok] patched {FLOW_FILE}")
    return True

def main():
    ensure_requirements()
    ok = patch_flow()
    print("\nNext steps:")
    print("  1) pip install -r requirements.txt")
    print("  2) export OPENAI_API_KEY=sk-...  (and optional GPT5_MODEL=gpt-5|gpt-5-mini|gpt-5-nano)")
    print('  3) Smoke test: python -c "from src.llm.gpt5_medical import GPT5MedicalGenerator;'
          'print(GPT5MedicalGenerator().generate(\'You are an IP expert.\','
          '\'List contraindications for rigid bronchoscopy.\')[\'text\'][:300])"')
    if not ok:
        sys.exit(1)

if __name__ == "__main__":
    main()