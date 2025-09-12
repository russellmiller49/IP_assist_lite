# SPDX-License-Identifier: MIT
from __future__ import annotations
import json
import os
import logging
from typing import Any, Dict
from pydantic import ValidationError
from .schema import ExtractedCase
from .prompt import build_prompt

logger = logging.getLogger(__name__)

# This client is intentionally minimal and vendor-agnostic.
# Replace `call_gpt_5_mini` with your actual API call (OpenAI SDK, etc.).

def call_gpt_5_mini(prompt: str) -> str:
    """
    Implement your provider call here (e.g., OpenAI Responses API).
    Must return a raw string that is a JSON object matching ExtractedCase.
    """
    # Example skeleton (pseudo-code):
    #
    # from openai import OpenAI
    # client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    # resp = client.responses.create(
    #     model="gpt-5-mini",
    #     input=[{"role":"user", "content": prompt}],
    #     temperature=0
    # )
    # return resp.output_text  # ensure it's pure JSON
    
    # Check if GPT-5 wrapper is available
    try:
        from src.models.gpt5_wrapper import GPT5Wrapper
        wrapper = GPT5Wrapper()
        
        # Use the wrapper's inference method
        response = wrapper.inference(
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=2000
        )
        
        # Extract the text response
        if isinstance(response, dict) and "content" in response:
            return response["content"]
        elif isinstance(response, str):
            return response
        else:
            raise RuntimeError(f"Unexpected response format from GPT5Wrapper: {type(response)}")
            
    except ImportError:
        # Fallback if GPT5 wrapper not available
        raise NotImplementedError("GPT5Wrapper not available. Wire this to your LLM provider (gpt-5-mini).")

def extract_structured(note_text: str) -> ExtractedCase:
    """
    Extract structured information from a clinical note using LLM.
    
    Args:
        note_text: The raw procedure note text
        
    Returns:
        ExtractedCase: Validated structured extraction
        
    Raises:
        RuntimeError: If LLM returns invalid JSON or schema validation fails
    """
    prompt = build_prompt(note_text)
    raw = call_gpt_5_mini(prompt)    # raw JSON string
    
    # Try to parse the JSON
    try:
        data: Dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as e:
        # Log the error for debugging
        logger.error(f"LLM returned non-JSON response: {raw[:400]}")
        # Optionally: retry with a 'return JSON only' reminder
        raise RuntimeError(f"Extractor returned non-JSON: {e}\nRaw: {raw[:400]}")

    # Validate against schema
    try:
        case = ExtractedCase(**data)
    except ValidationError as ve:
        logger.error(f"Schema validation failed: {ve}")
        raise RuntimeError(f"Extractor JSON failed schema validation:\n{ve}\nData: {json.dumps(data, indent=2)[:600]}")
    
    return case