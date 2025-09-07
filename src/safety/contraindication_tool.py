# JSON-mode style tool schema for structured safety decisions.
# Use with Responses API by passing as `tools` and enforcing via tool_choice.
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

# Force JSON-mode: the model must call the single tool above.
# For chat completions API, use "required" to force tool use
FORCE_DECISION_TOOL = "required"

__all__ = ["CONTRAINDICATION_TOOL", "FORCE_DECISION_TOOL"]