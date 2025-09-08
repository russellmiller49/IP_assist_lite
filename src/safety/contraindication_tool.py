"""
Contraindication tool schema for IP Assist Lite
Provides safety checking tools compatible with GPT-5 tool calling
"""

from typing import Dict, Any, List, Optional


def contraindication_tool_schema() -> Dict[str, Any]:
    """
    Return the schema for the contraindication decision tool.
    Compatible with both Responses API and Chat Completions API.
    """
    return {
        "type": "function",
        "function": {
            "name": "emit_contraindication_decision",
            "description": "Return contraindication status and rationale for a proposed intervention.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {"type": "string", "description": "Patient identifier"},
                    "intervention": {"type": "string", "description": "The proposed medical intervention"},
                    "decision": {
                        "type": "string",
                        "enum": ["contraindicated", "use_with_caution", "proceed"],
                        "description": "Safety decision for the intervention"
                    },
                    "rationale": {"type": "string", "description": "Detailed explanation for the decision"}
                },
                "required": ["patient_id", "intervention", "decision", "rationale"]
            },
        },
    }


# Legacy aliases for backward compatibility
CONTRAINDICATION_TOOL = [{
    "type": "function",
    "name": "emit_decision",
    "description": "Emit a structured procedural safety decision.",
    "parameters": {
        "type": "object",
        "properties": {
            "procedure": {"type":"string", "enum": ["Rigid bronchoscopy","Flexible bronchoscopy"]},
            "proceed": {"type":"boolean"},
            "risk_level": {"type":"string", "enum": ["low","moderate","high"]},
            "reasons": {"type":"array","items":{"type":"string"}},
            "notes": {"type":"string"}
        },
        "required": ["procedure","proceed","reasons"]
    }
}]

FORCE_DECISION_TOOL = "required"

__all__ = [
    "contraindication_tool_schema",
    "CONTRAINDICATION_TOOL",
    "FORCE_DECISION_TOOL"
]