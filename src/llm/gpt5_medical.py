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

class GPT5Medical:
    def __init__(self,
                 model: Optional[str] = None,
                 use_responses: Optional[bool] = None,
                 max_out: int = 800,
                 reasoning_effort: Optional[str] = None):  # "low"|"medium"|"high"
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        # Use correct GPT-5 model names (gpt-5, gpt-5-mini, gpt-5-nano)
        self.model = model or os.getenv("IP_GPT5_MODEL", "gpt-5")
        self.use_responses = use_responses if use_responses is not None else USE_RESPONSES_API
        self.max_out = max_out
        self.reasoning_effort = reasoning_effort or REASONING_EFFORT

    def _normalize_messages_for_responses(self, messages: List[Dict[str, str]]):
        """Map Chat-style messages -> Responses input format.
        Wrap each message as text content blocks for better compatibility.
        """
        output = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            output.append({"role": role, "content": [{"type": "text", "text": content}]})
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
                
                # Extract text from response
                text = getattr(resp, "output_text", None)
                if not text and hasattr(resp, "output") and resp.output:
                    # Try to extract from structured output
                    if isinstance(resp.output, list) and len(resp.output) > 0:
                        first_output = resp.output[0]
                        if hasattr(first_output, "content") and isinstance(first_output.content, list):
                            for content_item in first_output.content:
                                if hasattr(content_item, "text"):
                                    text = content_item.text
                                    break
                
                # Extract tool calls
                tool_calls = []
                for item in getattr(resp, "output", []) or []:
                    if getattr(item, "type", None) == "tool_call":
                        tool_calls.append({
                            "name": getattr(item, "tool_name", ""),
                            "arguments": getattr(item, "arguments", ""),
                        })
                
                # Import serialization helper
                from utils.serialization import to_jsonable
                return {
                    "text": text,
                    "tool_calls": tool_calls,
                    "raw": to_jsonable(resp),  # Always JSON-serializable
                }
            except Exception as e:
                # If Responses API not available, fall back to Chat Completions
                print(f"Responses API failed, falling back to Chat Completions: {e}")
                self.use_responses = False
        
        # Chat Completions path (reasoning models: use max_completion_tokens)
        # Check if using o1 models or GPT-5 models which have special requirements
        is_o1_model = self.model and self.model.startswith("o1")
        is_gpt5_model = self.model and (self.model.startswith("gpt-5") or self.model == "gpt-5")
        
        kwargs = {
            "model": self.model,
            "messages": messages,
        }
        
        # GPT-5, o1 models, and gpt-4o use max_completion_tokens, others use max_tokens
        if is_gpt5_model or is_o1_model or self.model.startswith("gpt-4o"):
            kwargs["max_completion_tokens"] = self.max_out
        else:
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
            
        resp = self.client.chat.completions.create(**kwargs)
        
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