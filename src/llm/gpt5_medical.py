"""
GPT-5 medical answer generator for IP-Assist-Lite
Canonical wrapper supporting both Responses API and Chat Completions
- JSON-safe serialization via model_dump()
- Tool forcing support for both APIs
- Reasoning effort control
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Union
import os
from dotenv import load_dotenv
from openai import OpenAI
import openai

# Load environment variables from .env file
load_dotenv()

# Configuration from environment
USE_RESPONSES_API = os.getenv("USE_RESPONSES_API", "1").strip() not in {"0","false","False"}
REASONING_EFFORT = os.getenv("REASONING_EFFORT", "").strip() or None  # e.g., "medium"
# Allowed GPT‑5 model family
ALLOWED_GPT5_MODELS = {"gpt-5", "gpt-5-mini", "gpt-5-nano"}
ENABLE_GPT4_FALLBACK = os.getenv("ENABLE_GPT4_FALLBACK", "true").strip().lower() == "true"
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"

class GPT5Medical:
    def _compose_instructions(self, messages: List[Dict[str, str]]) -> str:
        """Compose a single instruction string from any system messages with a sensible default."""
        sys_parts = [m.get("content", "") for m in messages if m.get("role") == "system"]
        base = (
            "You are a careful, thorough interventional pulmonology assistant. "
            "Use only the provided context when present; cite succinctly. Be specific on doses, contraindications, and steps when applicable."
        )
        if sys_parts:
            return "\n".join(sys_parts + [base]).strip()
        return base
    def _extract_text(self, resp) -> Optional[str]:
        """SDK-agnostic text extractor for Responses API."""
        # 1) Preferred shortcut (SDK helper)
        if text := getattr(resp, "output_text", None):
            return text

        # 2) Robust parsing across possible shapes
        try:
            raw = resp.model_dump() if hasattr(resp, "model_dump") else resp.__dict__

            # Newer Responses API: output is a list of items; message items have content blocks
            if isinstance(raw, dict) and isinstance(raw.get("output"), list):
                collected = []
                for item in raw.get("output", []):
                    itype = item.get("type")
                    # Direct output_text item
                    if itype == "output_text" and isinstance(item.get("text"), str):
                        collected.append(item.get("text", ""))
                        continue
                    # Message with content blocks
                    if itype == "message":
                        for block in item.get("content", []) or []:
                            btype = block.get("type")
                            # Blocks may be 'output_text' or other types; prefer text payload
                            if btype in ("output_text", "text") and isinstance(block.get("text"), str):
                                collected.append(block.get("text", ""))
                if collected:
                    return "\n".join([t for t in collected if t])

            # Fallbacks: sometimes SDK may return a flat 'text' at top level
            if isinstance(raw, dict) and isinstance(raw.get("text"), str):
                return raw.get("text")
        except Exception:
            pass

        return None
    
    def __init__(self,
                 model: Optional[str] = None,
                 use_responses: Optional[bool] = None,
                 max_out: int = 800,
                 reasoning_effort: Optional[str] = None):  # "low"|"medium"|"high"
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        # Normalize to GPT‑5 family if an alias like "gpt-5-turbo" is provided
        raw_model = (model or os.getenv("IP_GPT5_MODEL") or os.getenv("GPT5_MODEL") or "gpt-5-mini").strip()
        self.model = self._coerce_gpt5_model(raw_model)
        self.use_responses = use_responses if use_responses is not None else USE_RESPONSES_API
        self.max_out = max_out
        self.reasoning_effort = reasoning_effort or REASONING_EFFORT
        # Trace fields for UI/telemetry
        self.last_used_model: Optional[str] = None
        self.last_warning_banner: Optional[str] = None

    def _coerce_gpt5_model(self, name: str) -> str:
        """Map arbitrary names into the supported GPT‑5 family.
        - Exact matches allowed: gpt-5, gpt-5-mini, gpt-5-nano
        - Unknown gpt‑5 variants (e.g., gpt-5-turbo) → gpt-5
        - Non gpt‑5 names left as-is (fallback logic will handle access errors)
        """
        if name in ALLOWED_GPT5_MODELS:
            return name
        if name.startswith("gpt-5"):
            # Coerce any unrecognized variant in the gpt‑5 family to the base model
            return "gpt-5"
        return name

    def _normalize_messages_for_responses(self, messages: List[Dict[str, str]]):
        """Map Chat-style messages -> Responses input format (role + string content).
        The Responses API accepts a list of {role, content} where content is a string.
        """
        return [{"role": msg.get("role", "user"), "content": msg.get("content", "")} for msg in messages]

    def complete(self,
                 messages: List[Dict[str, str]],
                 tools: Optional[List[Dict[str, Any]]] = None,
                 tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
                 temperature: Optional[float] = None) -> Dict[str, Any]:
        """Return a plain dict with `.text`, `.tool_calls`, `.raw` fields.
        - Uses Responses API by default; falls back to Chat Completions with correct params.
        - Always returns JSON-serializable structures.
        """
        # Reset trace fields
        self.last_used_model = None
        self.last_warning_banner = None

        # Helper: extract tool calls from Responses API output
        def _extract_tool_calls_from_responses(resp_obj):
            tool_calls = []
            for item in getattr(resp_obj, "output", []) or []:
                if getattr(item, "type", None) == "tool_call":
                    tool_calls.append({
                        "name": getattr(item, "tool_name", ""),
                        "arguments": getattr(item, "arguments", ""),
                    })
            return tool_calls

        # Primary call: Responses API or Chat Completions for the requested model
        try:
            if self.use_responses:
                kwargs = {
                    "model": self.model,
                    # Extract any system messages into instructions; provide default guidance too
                    "instructions": self._compose_instructions(messages),
                    "input": self._normalize_messages_for_responses([m for m in messages if m.get("role") != "system"]),
                    "max_output_tokens": self.max_out,
                }
                if self.reasoning_effort:
                    kwargs["reasoning"] = {"effort": self.reasoning_effort}
                # Avoid passing non-portable 'verbosity' param; SDKs may not support it yet
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = tool_choice or "auto"
                # Note: GPT-5 Responses API doesn't support temperature parameter
                # Temperature is controlled by the model's internal reasoning

                resp = self.client.responses.create(**kwargs)
                text = self._extract_text(resp)
                tool_calls = _extract_tool_calls_from_responses(resp)
                from utils.serialization import to_jsonable
                self.last_used_model = getattr(resp, "model", self.model)

                # If Responses returned no text and no tool calls, try a Chat fallback (same model)
                if not (text and text.strip()) and not tool_calls:
                    try:
                        chat_kwargs = {
                            "model": self.model,
                            "messages": messages,
                        }
                        if self.model and (self.model.startswith("gpt-5") or self.model in ALLOWED_GPT5_MODELS):
                            chat_kwargs["max_completion_tokens"] = self.max_out
                        else:
                            chat_kwargs["max_tokens"] = self.max_out
                        if tools:
                            chat_kwargs["tools"] = tools
                            chat_kwargs["tool_choice"] = tool_choice or "auto"
                        if temperature is not None:
                            chat_kwargs["temperature"] = temperature

                        chat_resp = self.client.chat.completions.create(**chat_kwargs)
                        msg = chat_resp.choices[0].message if chat_resp.choices else None
                        text = msg.content if msg else ""
                        tool_calls = []
                        if msg and getattr(msg, "tool_calls", None):
                            for tc in msg.tool_calls:
                                tool_calls.append({
                                    "name": getattr(tc.function, "name", "") if hasattr(tc, "function") else "",
                                    "arguments": getattr(tc.function, "arguments", "") if hasattr(tc, "function") else "",
                                })
                        self.last_used_model = getattr(chat_resp, "model", self.model)
                        self.last_warning_banner = "Fetched content via Chat after empty Responses output."
                        return {
                            "text": text,
                            "tool_calls": tool_calls or None,
                            "raw": to_jsonable(chat_resp),
                            "used_model": self.last_used_model,
                        }
                    except Exception:
                        # Fall back to returning the original Responses object (even if empty)
                        pass

                return {
                    "text": text,
                    "tool_calls": tool_calls or None,
                    "raw": to_jsonable(resp),
                    "used_model": self.last_used_model,
                }
            else:
                # Chat Completions path
                is_o1_model = self.model and self.model.startswith("o1")
                kwargs = {
                    "model": self.model,
                    "messages": messages,
                }
                # Use correct token cap per model family
                if self.model and (self.model.startswith("gpt-5") or self.model in ALLOWED_GPT5_MODELS):
                    kwargs["max_completion_tokens"] = self.max_out
                else:
                    kwargs["max_tokens"] = self.max_out
                if not is_o1_model:
                    if tools:
                        kwargs["tools"] = tools
                        kwargs["tool_choice"] = tool_choice or "auto"
                    if temperature is not None:
                        kwargs["temperature"] = temperature
                else:
                    filtered_messages = []
                    for msg in messages:
                        if msg.get("role") == "system":
                            filtered_messages.append({"role": "user", "content": f"[System]: {msg['content']}"})
                        else:
                            filtered_messages.append(msg)
                    kwargs["messages"] = filtered_messages

                resp = self.client.chat.completions.create(**kwargs)
                msg = resp.choices[0].message if resp.choices else None
                text = msg.content if msg else ""
                tool_calls = []
                if msg and getattr(msg, "tool_calls", None):
                    for tc in msg.tool_calls:
                        tool_calls.append({
                            "name": getattr(tc.function, "name", "") if hasattr(tc, "function") else "",
                            "arguments": getattr(tc.function, "arguments", "") if hasattr(tc, "function") else "",
                        })
                from utils.serialization import to_jsonable
                self.last_used_model = getattr(resp, "model", self.model)
                return {
                    "text": text,
                    "tool_calls": tool_calls or None,
                    "raw": to_jsonable(resp),
                    "used_model": self.last_used_model,
                }
        except (openai.NotFoundError, openai.PermissionDeniedError, openai.AuthenticationError) as e:
            # Hard failures: do not silently downgrade
            self.last_warning_banner = (
                f"Selected model '{self.model}' is unavailable for this API key/project. "
                "Verify model access in the OpenAI dashboard or choose a different model."
            )
            raise
        except (openai.RateLimitError, openai.APIConnectionError, openai.APIStatusError, TimeoutError) as e:
            # Transient errors: optionally fallback
            if ENABLE_GPT4_FALLBACK and FALLBACK_MODEL:
                try:
                    # Retry primary path with fallback model
                    if self.use_responses:
                        kwargs = {
                            "model": FALLBACK_MODEL,
                            "instructions": self._compose_instructions(messages),
                            "input": self._normalize_messages_for_responses([m for m in messages if m.get("role") != "system"]),
                            "max_output_tokens": self.max_out,
                        }
                        if self.reasoning_effort:
                            kwargs["reasoning"] = {"effort": self.reasoning_effort}
                        if tools:
                            kwargs["tools"] = tools
                            kwargs["tool_choice"] = tool_choice or "auto"
                        kwargs["temperature"] = 0.2 if temperature is None else temperature
                        resp = self.client.responses.create(**kwargs)
                        text = self._extract_text(resp)
                        tool_calls = _extract_tool_calls_from_responses(resp)
                        from utils.serialization import to_jsonable
                        self.last_used_model = getattr(resp, "model", FALLBACK_MODEL)
                        self.last_warning_banner = (
                            f"Fell back to {FALLBACK_MODEL} due to transient error calling '{self.model}': {e.__class__.__name__}."
                        )
                        return {
                            "text": text,
                            "tool_calls": tool_calls or None,
                            "raw": to_jsonable(resp),
                            "used_model": self.last_used_model,
                        }
                    else:
                        is_o1_model = FALLBACK_MODEL.startswith("o1")
                        kwargs = {
                            "model": FALLBACK_MODEL,
                            "messages": messages,
                        }
                        if FALLBACK_MODEL.startswith("gpt-5"):
                            kwargs["max_completion_tokens"] = self.max_out
                        else:
                            kwargs["max_tokens"] = self.max_out
                        if not is_o1_model:
                            if tools:
                                kwargs["tools"] = tools
                                kwargs["tool_choice"] = tool_choice or "auto"
                            if temperature is not None:
                                kwargs["temperature"] = temperature
                        resp = self.client.chat.completions.create(**kwargs)
                        msg = resp.choices[0].message if resp.choices else None
                        text = msg.content if msg else ""
                        tool_calls = []
                        if msg and getattr(msg, "tool_calls", None):
                            for tc in msg.tool_calls:
                                tool_calls.append({
                                    "name": getattr(tc.function, "name", "") if hasattr(tc, "function") else "",
                                    "arguments": getattr(tc.function, "arguments", "") if hasattr(tc, "function") else "",
                                })
                        from utils.serialization import to_jsonable
                        self.last_used_model = getattr(resp, "model", FALLBACK_MODEL)
                        self.last_warning_banner = (
                            f"Fell back to {FALLBACK_MODEL} due to transient error calling '{self.model}': {e.__class__.__name__}."
                        )
                        return {
                            "text": text,
                            "tool_calls": tool_calls or None,
                            "raw": to_jsonable(resp),
                            "used_model": self.last_used_model,
                        }
                except Exception:
                    # Fall through to generic error
                    pass
            # If fallback disabled or also failed, re-raise
            raise
        except Exception:
            # Unknown error, bubble up
            raise

    # Backward compatibility with old interface
    def generate(self,
                 system: str,
                 user: str,
                 tools: Optional[List[Dict]] = None,
                 tool_choice: Optional[Dict] = None) -> Dict:
        """Legacy interface for backward compatibility"""
        messages = [
            {"role": "system", "content": system.strip()},
            {"role": "user", "content": user.strip()}
        ]
        result = self.complete(messages, tools, tool_choice)
        # Map to old format
        return {
            "text": result["text"],
            "tool_calls": result["tool_calls"],
            "usage": result["raw"].get("usage", {})
        }
    
    def generate_response(self, prompt: str, messages: Optional[List[Dict]] = None) -> str:
        """Simple text generation for orchestrator use"""
        msgs = messages or []
        msgs.append({"role": "user", "content": prompt})
        result = self.complete(msgs)
        # Track used model for UI consumption
        self.last_used_model = result.get("used_model", self.model)
        return result["text"] or "Unable to generate response."

# Create alias for backward compatibility
GPT5MedicalGenerator = GPT5Medical

__all__ = [
    "GPT5Medical",
    "GPT5MedicalGenerator",  # Backward compatibility alias
]
