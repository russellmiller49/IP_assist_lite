"""LLM-based structurer for converting reports to JSON."""

import json
import logging
from typing import Dict, Any, Optional
from pydantic import ValidationError
from .schema_contract import IPProcedureReport

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a medical coding structurer. Output ONLY minified JSON that validates
against the provided JSON Schema. No comments, no prose, no markdown code blocks.
For any missing required field, infer from context or set a safe default ("Not documented", false, 0).
Focus on extracting: procedure details, patient info, anatomical targets, imaging used, 
sampling performed, complications, and all RCS-18 required fields."""

def structure_to_json(
    report_text: str, 
    llm_client: Any,
    max_retries: int = 3
) -> IPProcedureReport:
    """Convert report text to validated IPProcedureReport.
    
    Args:
        report_text: The medical report text
        llm_client: LLM client with complete() method
        max_retries: Maximum validation retry attempts
        
    Returns:
        Validated IPProcedureReport object
        
    Raises:
        ValueError: If unable to produce valid JSON after retries
    """
    # Load schema for prompting
    schema_excerpt = _get_schema_excerpt()
    
    for attempt in range(max_retries):
        try:
            # Create extraction prompt
            prompt = _create_extraction_prompt(report_text, schema_excerpt)
            
            # Get LLM response
            raw_response = llm_client.complete(prompt=prompt)
            
            # Clean response (remove markdown if present)
            cleaned = _clean_json_response(raw_response)
            
            # Parse JSON
            data = json.loads(cleaned)
            
            # Validate with Pydantic
            obj = IPProcedureReport(**data)
            
            logger.info(f"Successfully structured report on attempt {attempt + 1}")
            return obj
            
        except json.JSONDecodeError as e:
            logger.warning(f"JSON decode error on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                # Try to repair JSON
                raw_response = _repair_json(llm_client, cleaned, str(e))
                
        except ValidationError as e:
            logger.warning(f"Validation error on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                # Send validation error back for repair
                raw_response = _repair_with_schema_errors(llm_client, data, e)
                
        except Exception as e:
            logger.error(f"Unexpected error on attempt {attempt + 1}: {e}")
            if attempt >= max_retries - 1:
                raise
    
    raise ValueError(f"Unable to produce valid JSON after {max_retries} retries")

def _create_extraction_prompt(report_text: str, schema: str) -> str:
    """Create the extraction prompt for the LLM."""
    return f"""{SYSTEM_PROMPT}

SCHEMA (key fields to extract):
{schema}

REPORT TO CONVERT:
<<<
{report_text}
>>>

Extract all information into the JSON structure. Pay special attention to:
- Procedure type and platform used
- All EBUS stations sampled with details
- Imaging modalities (CBCT, rEBUS, fluoroscopy)
- Sampling methods (TBNA gauge, passes, cryobiopsy details)
- Complications and blood loss
- All dates, times, personnel names

OUTPUT JSON:"""

def _repair_json(llm_client: Any, invalid_json: str, error: str) -> str:
    """Attempt to repair invalid JSON."""
    repair_prompt = f"""Fix this JSON to be valid. The error was: {error}

INVALID JSON:
{invalid_json}

OUTPUT VALID JSON:"""
    
    return llm_client.complete(prompt=repair_prompt)

def _repair_with_schema_errors(llm_client: Any, data: Dict, validation_error: ValidationError) -> str:
    """Repair JSON based on schema validation errors."""
    errors = validation_error.errors()
    error_summary = "\n".join([f"- {e['loc']}: {e['msg']}" for e in errors[:5]])
    
    repair_prompt = f"""Fix this JSON to satisfy the schema validation. 

VALIDATION ERRORS:
{error_summary}

CURRENT JSON:
{json.dumps(data, indent=2)}

Provide corrected JSON that addresses all validation errors:"""
    
    return llm_client.complete(prompt=repair_prompt)

def _clean_json_response(response: str) -> str:
    """Clean LLM response to extract pure JSON."""
    # Remove markdown code blocks if present
    if "```json" in response:
        response = response.split("```json")[1].split("```")[0]
    elif "```" in response:
        response = response.split("```")[1].split("```")[0]
    
    # Strip whitespace
    response = response.strip()
    
    # Ensure it starts with { or [
    if not response.startswith(("{", "[")):
        # Try to find JSON in the response
        for i, char in enumerate(response):
            if char in "{[":
                response = response[i:]
                break
    
    return response

def _get_schema_excerpt() -> str:
    """Get a condensed schema excerpt for prompting."""
    return """
{
  "version": "1.0",
  "procedure_key": "robotic_ion|ebus_systematic_staging_ett|pdt|...",
  "patient": {
    "name": "string",
    "dod_id": "string",
    "dob": "YYYY-MM-DD"
  },
  "context": {
    "date": "YYYY-MM-DD",
    "location": "string",
    "elective_vs_emergency": "elective|emergency",
    "asa": "I|II|III|IV|V"
  },
  "anesthesia": {
    "method": "GA|Moderate|Local",
    "airway": "ETT|LMA|None",
    "topical_lidocaine": {
      "mg": number,
      "mg_per_kg": number
    }
  },
  "findings": {
    "lesions": [{
      "location": "string",
      "size_mm": number
    }]
  },
  "imaging_guidance": {
    "cbct": {"system": "Cios_Spin|...", "spins": number},
    "rebus": {"view": "concentric|eccentric|aerated"}
  },
  "ebus": {
    "stations": [{
      "station": "4R|7|...",
      "short_axis_mm": number,
      "elastography": "predominantly_blue_stiff|heterogeneous|mostly_green_soft",
      "sampled": boolean,
      "passes": number,
      "needle_gauge": "21G|22G|25G",
      "rose": "adequate|malignant|..."
    }]
  },
  "sampling": {
    "tbna": [{"site": "string", "gauge": "string", "passes": number}],
    "tbbx": [{"lobe": "string", "forceps_bites": number}],
    "cryo_biopsy": [{"probe_mm": number, "freezes": number, "freeze_sec": number}]
  },
  "complications": {
    "pneumothorax": {"present": boolean},
    "bleeding": {"severity": "none|minor|moderate|brisk"},
    "other": ["string"]
  },
  "postop": {
    "ebl_ml": number,
    "disposition": "PACU|ICU|Ward",
    "followups": [{"service": "string", "when": "string"}]
  }
}
"""

class MockLLMClient:
    """Mock LLM client for testing."""
    
    def complete(self, prompt: str) -> str:
        """Return a mock JSON response."""
        return json.dumps({
            "version": "1.0",
            "procedure_key": "robotic_ion",
            "patient": {
                "name": "Test Patient",
                "dod_id": "123456789",
                "dob": "1950-01-01"
            },
            "context": {
                "date": "2024-01-15",
                "location": "OR 1",
                "elective_vs_emergency": "elective",
                "asa": "II"
            },
            "anesthesia": {
                "method": "GA",
                "airway": "ETT",
                "topical_lidocaine": {
                    "mg": 60,
                    "mg_per_kg": 0.8
                }
            },
            "findings": {
                "lesions": [{
                    "location": "RLL",
                    "size_mm": 15
                }]
            },
            "imaging_guidance": {
                "cbct": {
                    "system": "Cios_Spin",
                    "spins": 2
                },
                "rebus": {
                    "used": True,
                    "view": "concentric"
                }
            },
            "sampling": {
                "tbna": [{
                    "site": "RLL",
                    "gauge": "23G",
                    "passes": 5
                }],
                "cryo_biopsy": [{
                    "probe_mm": 1.1,
                    "freezes": 3,
                    "freeze_sec": 6
                }]
            },
            "complications": {
                "pneumothorax": {"present": False},
                "bleeding": {"severity": "none"}
            },
            "postop": {
                "ebl_ml": 5,
                "disposition": "PACU"
            }
        })