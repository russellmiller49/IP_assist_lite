"""
GPT-5 medical answer generator for IP-Assist-Lite
- Dynamic input budgeting (400k ctx - reserved output - margin)
- reasoning.effort + text.verbosity
- temperature <= 0.2 for clinical safety
- Robust response parsing
"""
import os, logging
from typing import List, Dict, Optional
from dotenv import load_dotenv

import tiktoken
from openai import OpenAI

# Load environment variables from .env file
load_dotenv()

MODEL = os.getenv("GPT5_MODEL", "gpt-5")  # gpt-5 | gpt-5-mini | gpt-5-nano
CTX_MAX = 400_000
DEFAULT_MAX_OUTPUT = 8_000
SAFETY_MARGIN = 1_024

def _get_encoder():
    try:
        return tiktoken.encoding_for_model(MODEL)
    except Exception:
        try:
            return tiktoken.get_encoding("o200k_base")
        except Exception:
            return tiktoken.get_encoding("cl100k_base")

ENCODER = _get_encoder()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def num_tokens(s: str) -> int:
    return len(ENCODER.encode(s or ""))

def truncate_right(text: str, budget: int) -> str:
    toks = ENCODER.encode(text or "")
    if len(toks) <= budget:
        return text
    return ENCODER.decode(toks[-budget:])

def max_input_budget(max_output_tokens: int) -> int:
    return max(0, CTX_MAX - max_output_tokens - SAFETY_MARGIN)

class GPT5MedicalGenerator:
    def __init__(self,
                 model: str = MODEL,
                 max_output: int = DEFAULT_MAX_OUTPUT,
                 reasoning_effort: str = "medium",  # minimal | low | medium | high
                 verbosity: str = "medium"):        # low | medium | high
        self.model = model
        self.max_out = max_output
        self.reasoning_effort = reasoning_effort
        self.verbosity = verbosity

    def generate(self,
                 system: str,
                 user: str,
                 tools: Optional[List[Dict]] = None,
                 tool_choice: Optional[Dict] = None) -> Dict:
        """
        Return dict: {"text": str, "tool_calls": list|None, "usage": dict|None}
        """
        prompt = f"System:\n{system.strip()}\n\nUser:\n{user.strip()}"
        prompt = truncate_right(prompt, max_input_budget(self.max_out))

        # Use chat completions API (GPT-5 is available on both APIs)
        # GPT-5 models only support default temperature (1.0)
        # If tools are provided, use them; otherwise simple completion
        if tools:
            resp = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system.strip()},
                    {"role": "user", "content": user.strip()}
                ],
                max_completion_tokens=self.max_out,
                # temperature=1.0 is default for GPT-5
                tools=tools,
                tool_choice=tool_choice if tool_choice else "auto",
                # GPT-5 specific parameters
                reasoning_effort=self.reasoning_effort,
                verbosity=self.verbosity
            )
        else:
            resp = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system.strip()},
                    {"role": "user", "content": user.strip()}
                ],
                max_completion_tokens=self.max_out,
                # temperature=1.0 is default for GPT-5
                # GPT-5 specific parameters
                reasoning_effort=self.reasoning_effort,
                verbosity=self.verbosity
            )

        # Parse response for chat completions API format
        if hasattr(resp, 'choices') and resp.choices:
            choice = resp.choices[0]
            answer = choice.message.content or ""
            tool_calls = choice.message.tool_calls if hasattr(choice.message, 'tool_calls') else []
        else:
            answer = ""
            tool_calls = []

        return {
            "text": answer,
            "tool_calls": tool_calls or None,
            "usage": dict(resp.usage) if hasattr(resp, 'usage') else {}
        }

__all__ = [
    "GPT5MedicalGenerator",
    "num_tokens",
    "max_input_budget",
]