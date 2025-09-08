# GPT-5 + LangChain/LangGraph 1.0 Alpha – Integration Guide for IP_assist_lite

**Purpose**: This file defines exact, machine-actionable conventions so Claude (or any agent) can write/modify code in this repo without guesswork. It specifies which OpenAI API surface to use for GPT-5 (Responses vs Chat Completions), how to pass reasoning and tool params, how to serialize results safely, and the canonical LangGraph 1.0 alpha wiring that matches this codebase.

## Repo Anchors (Assumed Paths)
- **Orchestrator (primary)**: `src/orchestration/langgraph_agent.py`
- **GPT-5 wrapper**: `src/llm/gpt5_medical.py`
- **Safety tool schema**: `src/safety/contraindication_tool.py`
- **Retrieval**: `src/retrieval/hybrid_retriever.py`
- **Indexing**: `src/index/{chunk.py|chunker_v2.py, upsert_qdrant.py}`
- **UI**: `src/ui/gradio_app.py`, `src/ui/gradio_app_gpt5.py`

If any path differs locally, adapt the import strings below, but keep the interfaces intact.

---

## 0) Environment & Dependencies
- **Python SDK**: `openai>=1.40.0` (or current) to ensure full Responses API + reasoning model support.
- **Models**: Set via env: `IP_GPT5_MODEL` (e.g., `gpt-5-large` or equivalent)
- **Keys**: `OPENAI_API_KEY` present; for Azure variants, also set the corresponding `OPENAI_BASE_URL` + `OPENAI_API_VERSION` and use the Azure client.
- **Serialization**: We must not `json.dumps()` SDK model objects directly—use `.model_dump()`/`.model_dump_json()` (see §3).

---

## 1) Which API to Use (and When)

We support both OpenAI API surfaces because GPT-5 features differ by endpoint:

- **Primary**: **Responses API** (`client.responses.create`) – preferred when you need reasoning controls, rich tool behavior, and token caps as `max_output_tokens`.
- **Alternate**: **Chat Completions** (`client.chat.completions.create`) – still supported; for reasoning models here the token cap is `max_completion_tokens` (not `max_tokens`).

**Rule**: If the call needs tool forcing + reasoning effort, use Responses. If it's plain text generation, either works; default to Responses for consistency.

---

## 2) Canonical Wrapper (Drop-In) – `src/llm/gpt5_medical.py`

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
                 reasoning_effort: Optional[str] = None):  # "low"|"medium"|"high"
        self.client = OpenAI()
        self.model = model or os.getenv("IP_GPT5_MODEL", "gpt-5-large")
        self.use_responses = use_responses
        self.max_out = max_out
        self.reasoning_effort = reasoning_effort

    def _normalize_messages_for_responses(self, messages: List[Dict[str, str]]):
        """Map Chat-style messages -> Responses input format.
        Pass through as a list of role/content parts; Responses accepts that directly.
        """
        return messages

    def complete(self,
                 messages: List[Dict[str, str]],
                 tools: Optional[List[Dict[str, Any]]] = None,
                 tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
                 temperature: Optional[float] = None) -> Dict[str, Any]:
        """Return a plain dict with `.text`, `.tool_calls`, `.raw` fields.
        - Uses Responses API by default; falls back to Chat Completions with correct params.
        - Always returns JSON-serializable structures (see §3).
        """
        if self.use_responses:
            resp = self.client.responses.create(
                model=self.model,
                input=self._normalize_messages_for_responses(messages),
                max_output_tokens=self.max_out,
                reasoning={"effort": self.reasoning_effort} if self.reasoning_effort else None,
                tools=tools,
                tool_choice=tool_choice or "auto",
                temperature=temperature,
            )
            text = getattr(resp, "output_text", None)
            # Responses tool calls surface in structured outputs; extract minimal:
            tool_calls = []
            for item in getattr(resp, "output", []) or []:
                if getattr(item, "type", None) == "tool_call":
                    tool_calls.append({
                        "name": item.tool_name,
                        "arguments": item.arguments,  # already JSON text or dict depending on SDK
                    })
            return {
                "text": text,
                "tool_calls": tool_calls,
                "raw": resp.model_dump(),  # JSON-serializable
            }
        else:
            # Chat Completions path (reasoning models: use max_completion_tokens)
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_completion_tokens=self.max_out,
                tools=tools,
                tool_choice=tool_choice,  # e.g., {"type":"function","function":{"name":"emit_decision"}}
                temperature=temperature,
            )
            msg = resp.choices[0].message
            # Chat tools: function_call(s) live on the message/tools field depending on SDK version
            tool_calls = []
            if getattr(msg, "tool_calls", None):
                for tc in msg.tool_calls:
                    tool_calls.append({
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    })
            return {
                "text": msg.content,
                "tool_calls": tool_calls,
                "raw": resp.model_dump(),  # JSON-serializable
            }
```

**Contract**: Consumers (LangGraph nodes, Gradio, FastAPI) call `GPT5Medical.complete(messages, tools, tool_choice, temperature)` and get a dict with keys: `text: str|None`, `tool_calls: List[...]`, `raw: dict`.

---

## 3) JSON Safety (Fixes the Gradio Crash)

Never `json.dumps()` the raw SDK objects. Use the SDK's Pydantic helpers:
- `resp.model_dump()` → plain Python dict
- `resp.model_dump_json()` → JSON string

If you keep custom dicts that may nest SDK objects, normalize recursively:

```python
def to_jsonable(o):
    if hasattr(o, "model_dump"): return o.model_dump()
    if isinstance(o, dict): return {k: to_jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [to_jsonable(x) for x in o]
    return o
```

Apply this at UI boundaries (`gradio_app*.py`, FastAPI handlers) before returning/logging responses.

---

## 4) Tool Schemas (Claude Safe)

Keep tool schemas as JSONSchema-ish functions. Example for the medical contraindication checker:

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

- **Responses API**: pass `tools=[contraindication_tool_schema()]`, `tool_choice="auto"` or `{"type":"function","function":{"name":"emit_contraindication_decision"}}` to force.
- **Chat Completions**: use the same tools list; tool forcing must be the dict form shown above (not the "required" shortcut).

**Tool call handling** (both APIs):
1. Inspect `result["tool_calls"]` (from wrapper).
2. Execute server-side tool function(s) with validated args.
3. Append tool results to the conversation as `role="tool"` messages with `tool_name` and `content` (JSON string), then call `complete(...)` again to let the model synthesize a final answer.

---

## 5) LangGraph 1.0 Alpha – Canonical Wiring

We model the flow as: `START → classify → retrieve → synthesize → safety_check → END`

```python
# src/orchestration/langgraph_agent.py (skeleton)
from __future__ import annotations
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, START, END
#from langgraph.prebuilt import ToolNode  # optional if you wire tools manually

class AgentState(TypedDict):
    user_id: str
    messages: List[Dict[str, str]]  # chat history
    query: str
    retrieved: List[Dict[str, Any]]
    draft: str
    safety: Dict[str, Any]

# --- Node fns ---

def node_classify(state: AgentState) -> AgentState:
    # inspect state["query"] or last user msg; set routing hints if you have branches
    return state

def node_retrieve(state: AgentState) -> AgentState:
    from src.retrieval.hybrid_retriever import HybridRetriever
    retriever = HybridRetriever(...)
    hits = retriever.search(state["query"], k=8)  # ensure it returns (chunk_id, score), using payload["id"]
    state["retrieved"] = hits
    return state

def node_synthesize(state: AgentState) -> AgentState:
    from src.llm.gpt5_medical import GPT5Medical
    llm = GPT5Medical(use_responses=True, max_out=800, reasoning_effort="medium")
    sys_prompt = {
        "role": "system",
        "content": "You are an interventional pulmonology assistant. Cite retrieved evidence when possible."
    }
    user_msg = {"role": "user", "content": state["query"]}
    tool_schema = []  # optionally add functions used during synthesis
    out = llm.complete([sys_prompt, *state.get("messages", []), user_msg], tools=tool_schema)
    state["draft"] = out["text"] or ""
    state.setdefault("_llm_raw", out["raw"])  # traceable, JSON-serializable
    return state

def node_safety_check(state: AgentState) -> AgentState:
    # Option A: call model with tool forcing
    from src.llm.gpt5_medical import GPT5Medical
    from src.safety.contraindication_tool import contraindication_tool_schema
    llm = GPT5Medical(use_responses=True, max_out=200)
    msgs = [
        {"role": "system", "content": "You are a safety controller that must call the contraindication tool if needed."},
        {"role": "user", "content": state["draft"]},
    ]
    out = llm.complete(
        msgs,
        tools=[contraindication_tool_schema()],
        tool_choice="auto",
    )
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

**Contracts for nodes**:
- Nodes accept and return the full `AgentState` (a TypedDict).
- Put only JSON-serializable values on the state; if you need to attach model responses, keep `model_dump()` results or strings.
- If you import `ToolNode`, use it only when delegating tool execution to LangGraph; otherwise, handle tools explicitly per §4.

---

## 6) Retrieval Contract (Qdrant Alignment)

Ensure semantic search returns chunk IDs that exist in `chunk_map`:

```python
# src/retrieval/hybrid_retriever.py (search)
# ...client.search(..., with_payload=True)
results = [(hit.payload["id"], float(hit.score)) for hit in hits]  # id comes from your chunk metadata
```

This avoids dropping semantic hits due to numeric/UUID point IDs not matching string `chunk_ids`. If you later migrate the index, you may set `PointStruct.id` to a UUID derived from `chunk_id`.

---

## 7) UI Boundaries (Gradio/FastAPI) – Safe Returns

- Never return raw SDK objects to Gradio/FastAPI; always return strings and plain dicts (`model_dump()` as needed).
- If your orchestrator returns `(html, status, meta)`, unpack these in the CLI/UI rather than passing the tuple to Markdown directly.

---

## 8) Minimal Examples Claude Can Reuse

### 8.1 Plain Completion (Responses API)
```python
from src.llm.gpt5_medical import GPT5Medical
llm = GPT5Medical(use_responses=True, max_out=600, reasoning_effort="medium")
res = llm.complete([
    {"role": "system", "content": "Be concise and clinical."},
    {"role": "user", "content": "Summarize bronchoscopic lung volume reduction indications."}
])
print(res["text"])  # final text
```

### 8.2 Tool Forcing Example (Chat Completions)
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

### 8.3 LangGraph Invoke
```python
from src.orchestration.langgraph_agent import build_graph
app = build_graph()
state = {
    "user_id": "test",
    "messages": [],
    "query": "What are post-EBUS bleeding management steps?",
    "retrieved": [],
    "draft": "",
    "safety": {}
}
result = app.invoke(state)
# result is JSON-serializable AgentState
```

---

## 9) Tests to Keep Claude Honest

- **Wrapper conformance**: `test_gpt5.py` asserts that `complete()` returns dict with `text|tool_calls|raw` and that `raw` is dict (serializable).
- **Tool call round trip**: mock a tool response and ensure the second model call incorporates the tool `role` message and produces a final answer.
- **Retriever ID join**: assert semantic hits resolve through `chunk_map`.
- **Graph integrity**: build/compile graph succeeds; invoke updates `draft` and `safety` keys.

---

## 10) Quick Checklist for Contributors (Claude Readable)

- ✅ Use Responses API by default; fall back to Chat Completions when needed.
- ✅ Token cap names: `max_output_tokens` (Responses) vs `max_completion_tokens` (Chat).
- ✅ Tools: pass the same function schemas to either API; force via `tool_choice` dict.
- ✅ Never `json.dumps()` SDK objects; use `.model_dump()` / `.model_dump_json()`.
- ✅ Keep LangGraph state JSON-serializable.
- ✅ Retrieval must return chunk IDs present in `chunk_map` (use `with_payload=True` + `payload["id"]`).
- ✅ UI returns only strings & dicts; unpack tuples in CLI.

This guide is designed to be dropped into the repo (e.g., `docs/gpt5_langgraph_integration.md`) and kept in sync with the wrapper and orchestrator signatures above.