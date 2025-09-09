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

# Load environment variables from .env file
load_dotenv()

# Configuration from environment
USE_RESPONSES_API = os.getenv("USE_RESPONSES_API", "1").strip() not in {"0","false","False"}
REASONING_EFFORT = os.getenv("REASONING_EFFORT", "").strip() or None  # e.g., "medium"
# Allowed GPT‑5 model family
ALLOWED_GPT5_MODELS = {"gpt-5", "gpt-5-mini", "gpt-5-nano"}

class GPT5Medical:
    def _extract_text(self, resp) -> Optional[str]:
        """SDK-agnostic text extractor for Responses API."""
        # Try direct attribute first
        if text := getattr(resp, "output_text", None):
            return text
        
        # Try various response structures
        try:
            raw = resp.model_dump() if hasattr(resp, "model_dump") else resp.__dict__
            
            # Check for output array with different structures
            for item in raw.get("output", []):
                # Check for message type
                if item.get("type") == "message":
                    for block in item.get("content", []):
                        if block.get("type") == "text":
                            return block["text"]
                
                # Check for output_text type
                if item.get("type") == "output_text":
                    return item["text"]
                
                # Check for direct text content
                if isinstance(item, dict) and "text" in item:
                    return item["text"]
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
        """Map Chat-style messages -> Responses input format.
        Wrap each message as text content blocks for better compatibility.
        """
        output = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            # Responses API expects 'input_text' blocks for text input
            output.append({"role": role, "content": [{"type": "input_text", "text": content}]})
        return output

    def complete(self,
                 messages: List[Dict[str, str]],
                 tools: Optional[List[Dict[str, Any]]] = None,
                 tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
                 temperature: Optional[float] = None) -> Dict[str, Any]:
        """Return a plain dict with `.text`, `.tool_calls`, `.raw` fields.
        - Uses Responses API by default; falls back to Chat Completions with correct params.
        - Always returns JSON-serializable structures.
        """
        # Try model candidates for robustness (handles preview names / access errors)
        model_candidates = []
        seen = set()
        for m in [self.model, os.getenv("GPT5_MODEL", "gpt-5"), "gpt-4o-mini", "gpt-4o"]:
            if m and m not in seen:
                model_candidates.append(m)
                seen.add(m)

        last_error = None
        for candidate in model_candidates:
            self.model = candidate
            if self.use_responses:
                try:
                    # Build Responses API call
                    kwargs = {
                        "model": self.model,
                        "input": self._normalize_messages_for_responses(messages),
                        "max_output_tokens": self.max_out,
                    }
                    if self.reasoning_effort:
                        kwargs["reasoning"] = {"effort": self.reasoning_effort}
                    if tools:
                        kwargs["tools"] = tools
                        kwargs["tool_choice"] = tool_choice or "auto"
                    if temperature is not None:
                        kwargs["temperature"] = temperature
                    resp = self.client.responses.create(**kwargs)
                    # Extract text using robust extractor
                    text = self._extract_text(resp)
                    # Extract tool calls
                    tool_calls = []
                    for item in getattr(resp, "output", []) or []:
                        if getattr(item, "type", None) == "tool_call":
                            tool_calls.append({
                                "name": getattr(item, "tool_name", ""),
                                "arguments": getattr(item, "arguments", ""),
                            })
                    from utils.serialization import to_jsonable
                    return {
                        "text": text,
                        "tool_calls": tool_calls or None,
                        "raw": to_jsonable(resp),
                    }
                except Exception as e:
                    last_error = e
                    # If Responses API call fails for this model, try Chat for the same model
                    pass
        
        # Chat Completions path (reasoning models: use max_completion_tokens)
        # Check if using o1 models or GPT-5 models which have special requirements
        is_o1_model = self.model and self.model.startswith("o1")
        is_gpt5_model = self.model and (self.model.startswith("gpt-5") or self.model == "gpt-5")
        
        kwargs = {
            "model": self.model,
            "messages": messages,
        }
        
        # Chat Completions: use max_tokens universally for compatibility
        kwargs["max_tokens"] = self.max_out
            
        # o1 models don't support tools, temperature, or system messages
        if not is_o1_model:
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = tool_choice or "auto"
            if temperature is not None:
                kwargs["temperature"] = temperature
        else:
            # For o1 models, convert system messages to user messages
            filtered_messages = []
            for msg in messages:
                if msg.get("role") == "system":
                    filtered_messages.append({"role": "user", "content": f"[System]: {msg['content']}"})
                else:
                    filtered_messages.append(msg)
            kwargs["messages"] = filtered_messages
            
        try:
            resp = self.client.chat.completions.create(**kwargs)
        except Exception as e:
            # Try next model candidate via chat if available
            last_error = e
            for candidate in model_candidates:
                if candidate == self.model:
                    continue
                try:
                    kwargs["model"] = candidate
                    resp = self.client.chat.completions.create(**kwargs)
                    self.model = candidate
                    break
                except Exception as e2:
                    last_error = e2
            else:
                raise last_error
        
        msg = resp.choices[0].message if resp.choices else None
        text = msg.content if msg else ""
        
        # Extract tool calls
        tool_calls = []
        if msg and getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                tool_calls.append({
                    "name": tc.function.name if hasattr(tc, "function") else "",
                    "arguments": tc.function.arguments if hasattr(tc, "function") else "",
                })
        
        # Import serialization helper
        from utils.serialization import to_jsonable
        return {
            "text": text,
            "tool_calls": tool_calls if tool_calls else None,
            "raw": to_jsonable(resp),  # Always JSON-serializable
        }

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
        return result["text"] or "Unable to generate response."

# Create alias for backward compatibility
GPT5MedicalGenerator = GPT5Medical

__all__ = [
    "GPT5Medical",
    "GPT5MedicalGenerator",  # Backward compatibility alias
]
