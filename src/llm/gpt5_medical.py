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
import logging
from dotenv import load_dotenv
from openai import OpenAI
import openai

# Configure logging
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
            logger.debug(f"✅ Found output_text attribute: {len(text)} chars")
            return text
            
        # 1b) Check for direct text attribute (GPT-5 specific)
        if text := getattr(resp, "text", None):
            logger.debug(f"✅ Found text attribute: {len(text)} chars")
            return text

        # 2) Robust parsing across possible shapes
        try:
            raw = resp.model_dump() if hasattr(resp, "model_dump") else resp.__dict__
            logger.debug(f"Response structure keys: {list(raw.keys()) if isinstance(raw, dict) else 'not a dict'}")
            
            # 2a) Check for text field at top level (GPT-5 responses)
            if isinstance(raw, dict) and "text" in raw and raw["text"]:
                text = raw["text"]
                logger.debug(f"✅ Found text field at top level: {len(text)} chars")
                return text

            # Newer Responses API: output is a list of items; message items have content blocks
            if isinstance(raw, dict) and isinstance(raw.get("output"), list):
                logger.debug(f"Found output list with {len(raw.get('output', []))} items")
                collected = []
                for i, item in enumerate(raw.get("output", [])):
                    itype = item.get("type")
                    logger.debug(f"  Item {i}: type={itype}")
                    
                    # Handle reasoning type (GPT-5 specific)
                    if itype == "reasoning":
                        # Check if there's text in the reasoning
                        reasoning_text = item.get("text", "")
                        if reasoning_text:
                            logger.debug(f"    Found reasoning text: {len(reasoning_text)} chars")
                            # For now, skip reasoning - we want the actual output
                        continue
                        
                    # Direct output_text item
                    if itype == "output_text" and isinstance(item.get("text"), str):
                        collected.append(item.get("text", ""))
                        continue
                    
                    # Direct text item
                    if itype == "text" and isinstance(item.get("text"), str):
                        collected.append(item.get("text", ""))
                        continue
                        
                    # Message with content blocks
                    if itype == "message":
                        content = item.get("content", []) or []
                        logger.debug(f"    Message has {len(content)} content blocks")
                        for block in content:
                            btype = block.get("type")
                            # Blocks may be 'output_text' or other types; prefer text payload
                            if btype in ("output_text", "text") and isinstance(block.get("text"), str):
                                collected.append(block.get("text", ""))
                if collected:
                    result = "\n".join([t for t in collected if t])
                    logger.debug(f"✅ Extracted {len(result)} chars from output items")
                    return result

            # Fallbacks: sometimes SDK may return a flat 'text' at top level
            if isinstance(raw, dict) and isinstance(raw.get("text"), str):
                text = raw.get("text")
                logger.debug(f"✅ Found text at top level: {len(text)} chars")
                return text
        except Exception as e:
            logger.error(f"❌ Error extracting text: {e}")

        logger.warning("❌ No text extracted from response")
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
                logger.info(f"🔵 Using Responses API for model: {self.model}")
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
                
                logger.debug(f"Request kwargs: {kwargs}")
                resp = self.client.responses.create(**kwargs)
                logger.debug(f"Response type: {type(resp)}")
                
                text = self._extract_text(resp)
                logger.info(f"📝 Extracted text length: {len(text) if text else 0} chars")
                
                tool_calls = _extract_tool_calls_from_responses(resp)
                from utils.serialization import to_jsonable
                self.last_used_model = getattr(resp, "model", self.model)

                # If Responses returned no text and no tool calls, try a Chat fallback (same model)
                if not (text and text.strip()) and not tool_calls:
                    logger.warning(f"⚠️ Responses API returned empty text. Trying Chat Completions fallback...")
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

                        logger.info(f"🔄 Trying Chat Completions with model: {self.model}")
                        chat_resp = self.client.chat.completions.create(**chat_kwargs)
                        msg = chat_resp.choices[0].message if chat_resp.choices else None
                        text = msg.content if msg else ""
                        
                        if text:
                            logger.info(f"✅ Chat Completions returned {len(text)} chars")
                        else:
                            logger.warning(f"❌ Chat Completions also returned empty")
                            
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
                    except Exception as e:
                        logger.error(f"❌ Chat fallback failed: {e}")
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
        except (openai.NotFoundError, openai.PermissionDeniedError) as e:
            logger.warning(f"⚠️ Model {self.model} not accessible: {e}")
            # Try fallback to GPT-4
            if ENABLE_GPT4_FALLBACK and self.model.startswith("gpt-5"):
                logger.info(f"🔄 Falling back to {FALLBACK_MODEL}")
                try:
                    fallback_kwargs = {
                        "model": FALLBACK_MODEL,
                        "messages": messages,
                        "max_tokens": self.max_out,
                    }
                    if temperature is not None:
                        fallback_kwargs["temperature"] = temperature
                    if tools:
                        fallback_kwargs["tools"] = tools
                        fallback_kwargs["tool_choice"] = tool_choice or "auto"
                        
                    fallback_resp = self.client.chat.completions.create(**fallback_kwargs)
                    msg = fallback_resp.choices[0].message if fallback_resp.choices else None
                    text = msg.content if msg else ""
                    
                    logger.info(f"✅ Fallback to {FALLBACK_MODEL} succeeded: {len(text)} chars")
                    
                    tool_calls = []
                    if msg and getattr(msg, "tool_calls", None):
                        for tc in msg.tool_calls:
                            tool_calls.append({
                                "name": getattr(tc.function, "name", "") if hasattr(tc, "function") else "",
                                "arguments": getattr(tc.function, "arguments", "") if hasattr(tc, "function") else "",
                            })
                    
                    from utils.serialization import to_jsonable
                    self.last_used_model = FALLBACK_MODEL
                    self.last_warning_banner = f"Using fallback model {FALLBACK_MODEL} (GPT-5 not accessible)"
                    
                    return {
                        "text": text,
                        "tool_calls": tool_calls or None,
                        "raw": to_jsonable(fallback_resp),
                        "used_model": self.last_used_model,
                    }
                except Exception as e2:
                    logger.error(f"❌ Fallback also failed: {e2}")
                    raise e
            else:
                raise e
        except openai.AuthenticationError as e:
            logger.error(f"❌ Authentication error: {e}")
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
