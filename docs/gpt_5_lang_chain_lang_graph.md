# GPT‑5 + LangChain/LangGraph 1.0 Alpha – Integration Guide for `IP_assist_lite` (Revised)

**Purpose**: Exact, machine‑actionable conventions so agents can write/modify code in this repo without guesswork. This version fixes model ID inaccuracies (e.g., replaces the non‑existent `gpt-5-large` with valid IDs), aligns token‑cap params per endpoint, and adds new GPT‑5 controls (`verbosity`, `minimal` reasoning).

> **Repo anchors (assumed paths)**
>
> - Orchestrator (primary): `src/orchestration/langgraph_agent.py`
> - GPT‑5 wrapper: `src/llm/gpt5_medical.py`
> - Safety tool schema: `src/safety/contraindication_tool.py`
> - Retrieval: `src/retrieval/hybrid_retriever.py`
> - Indexing: `src/index/{chunk.py|chunker_v2.py, upsert_qdrant.py}`
> - UI: `src/ui/gradio_app.py`, `src/ui/gradio_app_gpt5.py`

---

## 0) Environment & Dependencies

- **Python SDK**: `openai>=1.100.0` (or newer). Ensures GPT‑5 features like `verbosity`, expanded reasoning controls, and updated token‑cap params are available.
- **Models**: Set via env `IP_GPT5_MODEL`. **Valid values**: `gpt-5`, `gpt-5-mini`, `gpt-5-nano`. (There is **no** `gpt-5-large`.)
- **Keys**: `OPENAI_API_KEY` present. For Azure variants, set `OPENAI_BASE_URL` + `OPENAI_API_VERSION` and use the Azure client.
- **Serialization**: Never `json.dumps()` SDK objects—use `.model_dump()` / `.model_dump_json()` (see §3).

---

## 1) Which API to use (and when)

We support **both** OpenAI API surfaces because GPT‑5 features differ by endpoint:

- **Primary**: **Responses API** (`client.responses.create`) – preferred for reasoning controls, rich tool behavior, and token caps via `max_output_tokens`.
- **Alternate**: **Chat Completions** (`client.chat.completions.create`) – also supported; for reasoning models, the token cap is `max_completion_tokens` (not `max_tokens`).

> **Rule**: If the call needs tool forcing + reasoning effort, use **Responses**. For plain text, either works; default to **Responses** for consistency.

---

## 2) Canonical wrapper (drop‑in) – `src/llm/gpt5_medical.py`

Create/confirm a single class providing a stable, testable interface used by the orchestrator and UIs.

```python
# src/llm/gpt5_medical.py
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple, Union
import os
from openai import OpenAI

class GPT5Medical:
    def __init__(self,
                 model: Optional[str] = None,
                 use_responses: bool = True,
                 max_out: int = 800,
                 reasoning_effort: Optional[str] = None):  # "minimal"|"low"|"medium"|"high"
        self.client = OpenAI()
        # ✅ default to a real API model id
        self.model = model or os.getenv("IP_GPT5_MODEL", "gpt-5")
        self.use_responses = use_responses
        self.max_out = max_out
        self.reasoning_effort = reasoning_effort

    def _normalize_messages_for_responses(self, messages: List[Dict[str, str]]):
        """Map Chat-style messages -> Responses input format (list of role/content objects)."""
        return messages

    def complete(self,
                 messages: List[Dict[str, str]],
                 tools: Optional[List[Dict[str, Any]]] = None,
                 tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
                 temperature: Optional[float] = None,
                 verbosity: Optional[str] = None) -> Dict[str, Any]:
        """Return a dict with `.text`, `.tool_calls`, `.raw`.
        Uses Responses API by default; falls back to Chat Completions with correct params.
        Always returns JSON-serializable structures (see §3).
        """
        if self.use_responses:
            # Responses API path
            kwargs = {
                "model": self.model,
                "input": self._normalize_messages_for_responses(messages),
                "max_output_tokens": self.max_out,
                "tools": tools,
                "tool_choice": tool_choice or "auto",
                "temperature": temperature,
            }
            if self.reasoning_effort:
                kwargs["reasoning"] = {"effort": self.reasoning_effort}
            if verbosity:
                kwargs["verbosity"] = verbosity

            resp = self.client.responses.create(**kwargs)
            text = getattr(resp, "output_text", None)

            tool_calls = []
            for item in getattr(resp, "output", []) or []:
                if getattr(item, "type", None) == "tool_call":
                    tool_calls.append({
                        "name": item.tool_name,
                        "arguments": item.arguments,
                    })

            return {"text": text, "tool_calls": tool_calls, "raw": resp.model_dump()}
        else:
            # Chat Completions path (reasoning models: use max_completion_tokens)
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_completion_tokens=self.max_out,
                tools=tools,
                tool_choice=tool_choice,
                temperature=temperature,
            )
            msg = resp.choices[0].message
            tool_calls = []
            if getattr(msg, "tool_calls", None):
                for tc in msg.tool_calls:
                    tool_calls.append({
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    })
            return {"text": msg.content, "tool_calls": tool_calls, "raw": resp.model_dump()}
```

**Contract**: Consumers (LangGraph nodes, Gradio, FastAPI) call `GPT5Medical.complete(messages, tools, tool_choice, temperature, verbosity)` and get: `text: str|None`, `tool_calls: List[...]`, `raw: dict`.

---

## 3) JSON safety (fixes UI crashes)

Never `json.dumps()` the raw SDK objects. Use the SDK’s Pydantic helpers:

- `resp.model_dump()` → plain Python `dict`
- `resp.model_dump_json()` → JSON string

If you keep custom dicts that may nest SDK objects, normalize recursively:

```python
def to_jsonable(o):
    if hasattr(o, "model_dump"): return o.model_dump()
    if isinstance(o, dict): return {k: to_jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [to_jsonable(x) for x in o]
    return o
```

Apply this at **UI boundaries** (`gradio_app*.py`, FastAPI handlers) before returning/logging responses.

---

## 4) Tool schemas (function tools)

Keep tool schemas as JSONSchema‑ish **functions**. Example (medical contraindication checker):

```python
# src/safety/contraindication_tool.py

def contraindication_tool_schema():
    return {
        "type": "function",
        "function": {
            "name": "emit_contraindication_decision",
            "description": "Return contraindication status and rationale for a proposed intervention.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {"type": "string"},
                    "intervention": {"type": "string"},
                    "decision": {"type": "string", "enum": ["contraindicated", "use_with_caution", "proceed"]},
                    "rationale": {"type": "string"}
                },
                "required": ["patient_id", "intervention", "decision", "rationale"]
            },
        },
    }
```

- **Responses API**: pass `tools=[...]`, `tool_choice="auto"` or force with the dict: `{"type":"function","function":{"name":"emit_contraindication_decision"}}`.
- **Chat Completions**: same `tools` list; force with the dict form (do **not** rely on deprecated shortcuts).

**Handling tool calls** (both APIs):
1. Inspect `result["tool_calls"]` (from wrapper).
2. Execute server‑side tool(s) with validated args.
3. Append results to the conversation as `role="tool"` messages with `tool_name` and JSON `content`, then call `complete(...)` again for the final answer.

---

## 5) LangGraph 1.0 alpha – canonical wiring

Flow: **START → classify → retrieve → synthesize → safety_check → END**

```python
# src/orchestration/langgraph_agent.py (skeleton)
from __future__ import annotations
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, START, END

class AgentState(TypedDict):
    user_id: str
    messages: List[Dict[str, str]]
    query: str
    retrieved: List[Dict[str, Any]]
    draft: str
    safety: Dict[str, Any]

def node_classify(state: AgentState) -> AgentState:
    return state

def node_retrieve(state: AgentState) -> AgentState:
    from src.retrieval.hybrid_retriever import HybridRetriever
    retriever = HybridRetriever(...)
    hits = retriever.search(state["query"], k=8)  # returns (chunk_id, score)
    state["retrieved"] = hits
    return state

def node_synthesize(state: AgentState) -> AgentState:
    from src.llm.gpt5_medical import GPT5Medical
    llm = GPT5Medical(use_responses=True, max_out=800, reasoning_effort="medium")
    sys_prompt = {"role": "system", "content": "You are an interventional pulmonology assistant. Cite retrieved evidence when possible."}
    user_msg = {"role": "user", "content": state["query"]}
    out = llm.complete([sys_prompt, *state.get("messages", []), user_msg], tools=[])
    state["draft"] = out["text"] or ""
    state.setdefault("_llm_raw", out["raw"])  # traceable, JSON‑serializable
    return state

def node_safety_check(state: AgentState) -> AgentState:
    from src.llm.gpt5_medical import GPT5Medical
    from src.safety.contraindication_tool import contraindication_tool_schema
    llm = GPT5Medical(use_responses=True, max_out=200)
    msgs = [
        {"role": "system", "content": "You are a safety controller that must call the contraindication tool if needed."},
        {"role": "user", "content": state["draft"]},
    ]
    out = llm.complete(msgs, tools=[contraindication_tool_schema()], tool_choice="auto")
    state["safety"] = {"tool_calls": out["tool_calls"]}
    return state

def build_graph():
    g = StateGraph(AgentState)
    g.add_node("classify", node_classify)
    g.add_node("retrieve", node_retrieve)
    g.add_node("synthesize", node_synthesize)
    g.add_node("safety_check", node_safety_check)

    g.add_edge(START, "classify")
    g.add_edge("classify", "retrieve")
    g.add_edge("retrieve", "synthesize")
    g.add_edge("synthesize", "safety_check")
    g.add_edge("safety_check", END)

    return g.compile()
```

**Node contracts**
- Nodes accept/return the full `AgentState`.
- Keep state **JSON‑serializable** only.
- If you use `ToolNode`, prefer explicit tool handling unless you want LangGraph to manage tool execution.

---

## 6) Retrieval contract (Qdrant alignment)

Semantic search must return chunk IDs that exist in `chunk_map`:

```python
# src/retrieval/hybrid_retriever.py
# ...client.search(..., with_payload=True)
results = [(hit.payload["id"], float(hit.score)) for hit in hits]
```

This avoids dropping semantic hits due to numeric/UUID point IDs not matching your string `chunk_id`s.

---

## 7) UI boundaries (Gradio/FastAPI)

- Return only strings & plain dicts to clients; never raw SDK objects.
- If your orchestrator returns a tuple `(html, status, meta)`, unpack it before passing to Markdown / JSON responses.

---

## 8) Minimal examples

### 8.1 Plain completion (Responses API)
```python
from src.llm.gpt5_medical import GPT5Medical
llm = GPT5Medical(use_responses=True, max_out=600, reasoning_effort="medium")
res = llm.complete([
    {"role": "system", "content": "Be concise and clinical."},
    {"role": "user", "content": "Summarize bronchoscopic lung volume reduction indications."}
], verbosity="low")
print(res["text"])  # final text
```

### 8.2 Tool forcing example (Chat Completions)
```python
from src.llm.gpt5_medical import GPT5Medical
from src.safety.contraindication_tool import contraindication_tool_schema

llm = GPT5Medical(use_responses=False, max_out=200)
msgs = [
    {"role": "system", "content": "Use the tool to decide safety."},
    {"role": "user", "content": "Evaluate pneumothorax risk for valve placement in severe emphysema."}
]
res = llm.complete(
    msgs,
    tools=[contraindication_tool_schema()],
    tool_choice={"type":"function","function":{"name":"emit_contraindication_decision"}}
)
print(res["tool_calls"])  # list of {name, arguments}
```

### 8.3 LangGraph invoke
```python
from src.orchestration.langgraph_agent import build_graph
app = build_graph()
state = {
  "user_id": "test",
  "messages": [],
  "query": "What are post‑EBUS bleeding management steps?",
  "retrieved": [],
  "draft": "",
  "safety": {}
}
result = app.invoke(state)  # JSON‑serializable AgentState
```

---

## 9) Tests

- **Wrapper conformance**: `test_gpt5.py` asserts that `complete()` returns dict with `text|tool_calls|raw` and that `raw` is a `dict`.
- **Tool round‑trip**: mock a tool response and ensure the second model call consumes the tool message and produces a final answer.
- **Retriever join**: assert semantic hits resolve through `chunk_map`.
- **Graph integrity**: build/compile graph succeeds; `invoke` updates `draft` and `safety` keys.

---

## 10) Quick checklist

- ✅ Default to **Responses API**; Chat is fine when needed.
- ✅ Token caps: `max_output_tokens` (Responses) vs `max_completion_tokens` (Chat).
- ✅ Tools: same function schemas for both APIs; force via `tool_choice` dict.
- ✅ **Never** `json.dumps()` SDK objects; use `.model_dump()` / `.model_dump_json()`.
- ✅ Keep LangGraph state JSON‑serializable.
- ✅ Retrieval must return chunk IDs present in `chunk_map`.
- ✅ UI returns only strings & dicts.

---

### Notes on GPT‑5 controls you can surface
- **`reasoning_effort`** supports `"minimal"` (plus `low|medium|high`) to speed up routine answers.
- **`verbosity`** can be `low|medium|high` to control brevity vs. expansiveness.

(See the citations in my message for the latest docs.)

