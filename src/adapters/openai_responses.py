"""OpenAI Responses API helpers for structured extraction, reranking, and answer generation."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import yaml
from openai import OpenAI
from pydantic import BaseModel, Field
from tenacity import RetryError, retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from dotenv import load_dotenv

# ----------------- Pydantic models for structured extraction -----------------


class EvidenceItem(BaseModel):
    type: str = Field(description="RCT | meta-analysis | guideline | expert | cohort | case-series")
    claim: str
    data: Optional[str] = None
    source: Optional[str] = None
    confidence: str = Field(description="high | moderate | low")


class ClinicalThreshold(BaseModel):
    parameter: str
    threshold: str
    action: str
    evidence_basis: Optional[str] = None


class Complication(BaseModel):
    name: str
    rate: Optional[str] = None


class Procedure(BaseModel):
    name: str
    indications: List[str] = Field(default_factory=list)
    contraindications: List[str] = Field(default_factory=list)
    technique_notes: List[str] = Field(default_factory=list)
    complications: List[Complication] = Field(default_factory=list)


class Extraction(BaseModel):
    primary_topic: str
    secondary_topics: List[str] = Field(default_factory=list)
    evidence_items: List[EvidenceItem] = Field(default_factory=list)
    clinical_thresholds: List[ClinicalThreshold] = Field(default_factory=list)
    procedures: List[Procedure] = Field(default_factory=list)
    diagnostic_criteria: List[Dict[str, Any]] = Field(default_factory=list)
    management_algorithms: List[Dict[str, Any]] = Field(default_factory=list)


# ----------------- Config + client -----------------


CONFIG_PATH = Path("configs/models.yaml")
_CFG: Dict[str, Any] = {}
if CONFIG_PATH.exists():
    try:
        _CFG = yaml.safe_load(CONFIG_PATH.read_text()) or {}
    except yaml.YAMLError:
        _CFG = {}

load_dotenv()

_CLIENT = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

_MODEL_ENV_OVERRIDES = {
    "generation_model": os.getenv("IP_GENERATION_MODEL"),
    "extraction_model": os.getenv("IP_EXTRACTION_MODEL"),
    "rerank_model": os.getenv("IP_RERANK_MODEL"),
    "embed_model": os.getenv("IP_EMBED_MODEL"),
}


def _cfg_defaults() -> Dict[str, Any]:
    defaults = _CFG.get("responses_defaults", {}) if isinstance(_CFG, dict) else {}
    temp_env = os.getenv("IP_RESPONSES_TEMPERATURE")
    max_env = os.getenv("IP_RESPONSES_MAX_OUTPUT")
    resolved = {
        "temperature": defaults.get("temperature", 0.1),
        "max_output_tokens": defaults.get("max_output_tokens", 1800),
    }
    if temp_env is not None:
        try:
            resolved["temperature"] = float(temp_env)
        except ValueError:
            pass
    if max_env is not None:
        try:
            resolved["max_output_tokens"] = int(max_env)
        except ValueError:
            pass
    return resolved


def _resolve_model(name: str, fallback: str) -> str:
    if _MODEL_ENV_OVERRIDES.get(name):
        return _MODEL_ENV_OVERRIDES[name]  # type: ignore[index]
    if isinstance(_CFG, dict) and _CFG.get(name):
        return _CFG[name]
    return fallback


def _ensure_api_key() -> None:
    if not _CLIENT.api_key:
        raise RuntimeError("OPENAI_API_KEY is not set for OpenAI client usage.")


def _response_retry() -> Dict[str, Any]:
    return {
        "stop": stop_after_attempt(3),
        "wait": wait_exponential(multiplier=0.5, min=0.5, max=4),
        "retry": retry_if_exception_type(Exception),
        "reraise": True,
    }


def _coerce_output_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if isinstance(text, str) and text:
        return text
    if hasattr(response, "model_dump"):
        payload = response.model_dump()
    else:
        payload = getattr(response, "__dict__", {})
    if isinstance(payload, dict):
        # Responses API shape
        output_items = payload.get("output")
        if isinstance(output_items, list):
            collected: List[str] = []
            for item in output_items:
                if not isinstance(item, dict):
                    continue
                block_type = item.get("type")
                if block_type in {"text", "output_text"} and isinstance(item.get("text"), str):
                    collected.append(item["text"])
                elif block_type == "message":
                    for block in item.get("content", []) or []:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") in {"text", "output_text"} and isinstance(block.get("text"), str):
                            collected.append(block["text"])
            if collected:
                return "\n".join(collected)
        # Chat completions fallback
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict) and isinstance(message.get("content"), str):
                    return message["content"]
    raise ValueError("OpenAI response did not contain any text payload.")


@retry(**_response_retry())
def _responses_create(**kwargs: Any):
    _ensure_api_key()
    return _CLIENT.responses.create(**kwargs)


# ----------------- Structured extraction via JSON Schema -----------------


def extract_structured(raw_text: str) -> Extraction:
    schema = {
        "name": "ClinicalExtraction",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "primary_topic": {"type": "string"},
                "secondary_topics": {"type": "array", "items": {"type": "string"}},
                "evidence_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "type": {"type": "string"},
                            "claim": {"type": "string"},
                            "data": {"type": "string"},
                            "source": {"type": "string"},
                            "confidence": {"type": "string"},
                        },
                        "required": ["type", "claim", "confidence"],
                    },
                },
                "clinical_thresholds": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "parameter": {"type": "string"},
                            "threshold": {"type": "string"},
                            "action": {"type": "string"},
                            "evidence_basis": {"type": "string"},
                        },
                        "required": ["parameter", "threshold", "action"],
                    },
                },
                "procedures": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "name": {"type": "string"},
                            "indications": {"type": "array", "items": {"type": "string"}},
                            "contraindications": {"type": "array", "items": {"type": "string"}},
                            "technique_notes": {"type": "array", "items": {"type": "string"}},
                            "complications": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "name": {"type": "string"},
                                        "rate": {"type": "string"},
                                    },
                                    "required": ["name"],
                                },
                            },
                        },
                        "required": ["name"],
                    },
                },
                "diagnostic_criteria": {"type": "array", "items": {"type": "object"}},
                "management_algorithms": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["primary_topic"],
        },
        "strict": True,
    }

    defaults = _cfg_defaults()
    response = _responses_create(
        model=_resolve_model("extraction_model", "gpt-5-mini"),
        input=[
            {
                "role": "system",
                "content": "Extract clinically precise structured data from interventional pulmonology text. Output must match the schema exactly.",
            },
            {"role": "user", "content": raw_text},
        ],
        response_format={"type": "json_schema", "json_schema": schema},
        temperature=defaults.get("temperature", 0.1),
        max_output_tokens=defaults.get("max_output_tokens", 1800),
    )
    payload = _coerce_output_text(response)
    data = json.loads(payload)
    return Extraction.model_validate(data)


# ----------------- Final grounded answer synthesis -----------------


def generate_grounded(
    question: str,
    passages: Sequence[str],
    *,
    temperature: Optional[float] = None,
    max_output_tokens: Optional[int] = None,
) -> str:
    defaults = _cfg_defaults()
    resolved_temp = temperature if temperature is not None else max(defaults.get("temperature", 0.1), 0.1)
    resolved_max = max_output_tokens if max_output_tokens is not None else defaults.get("max_output_tokens", 1800)

    context = "\n\n".join(f"[{idx + 1}] {chunk}" for idx, chunk in enumerate(passages[:12]))
    prompt = (
        "Write a safe, evidence-aware response for an interventional pulmonology clinician. "
        "Cite supporting passages as [#]. If uncertain or missing evidence, say so explicitly.\n\n"
        f"CONTEXT PASSAGES:\n{context}\n\nQUESTION:\n{question}"
    )

    response = _responses_create(
        model=_resolve_model("generation_model", "gpt-5"),
        input=[{"role": "user", "content": prompt}],
        temperature=resolved_temp,
        max_output_tokens=resolved_max,
    )
    return _coerce_output_text(response)


# ----------------- Lightweight self-rerank -----------------


def rerank(query: str, candidates: Sequence[str], limit: int = 8) -> List[int]:
    if not candidates:
        return []

    joined = "\n\n".join(f"[{idx}] {text}" for idx, text in enumerate(candidates))
    prompt = (
        "You are re-ranking retrieved passages for an interventional pulmonology assistant. "
        "Return the indices of the top passages as a JSON list in descending relevance order.\n\n"
        f"Query: {query}\n\nCandidates:\n{joined}"
    )

    schema = {
        "name": "RerankResponse",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "indices": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 0, "maximum": len(candidates) - 1},
                    "maxItems": limit,
                }
            },
            "required": ["indices"],
        },
    }

    try:
        response = _responses_create(
            model=_resolve_model("rerank_model", "gpt-5-mini"),
            input=[{"role": "user", "content": prompt}],
            response_format={"type": "json_schema", "json_schema": schema},
            temperature=0,
            max_output_tokens=200,
        )
        payload = json.loads(_coerce_output_text(response))
        indices = payload.get("indices", [])
        if isinstance(indices, list):
            cleaned = [int(i) for i in indices if isinstance(i, int) and 0 <= i < len(candidates)]
            if cleaned:
                return cleaned[:limit]
    except RetryError:
        pass
    except Exception:
        pass

    return list(range(min(limit, len(candidates))))


__all__ = [
    "ClinicalThreshold",
    "Complication",
    "EvidenceItem",
    "Extraction",
    "Procedure",
    "extract_structured",
    "generate_grounded",
    "rerank",
]
