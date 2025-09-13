"""Integration facade for the complete reporting pipeline."""

import logging
from typing import Dict, Tuple, Any, Optional
from .reporter_engine import render_report
from .llm_structurer import structure_to_json, MockLLMClient
from .quality import run_all_validators, get_validation_summary, auto_fill_defaults
from ..coding.adapters.reporting_adapter import case_from_ip_report
from ..coding.rules import code_case
from ..coding.kb import CodingKB

logger = logging.getLogger(__name__)

def generate_report_and_codes(
    miniprompt: str,
    patient_ctx: Optional[Dict] = None,
    llm_client: Optional[Any] = None,
    validate: bool = True,
    auto_fill: bool = True
) -> Dict[str, Any]:
    """Generate report, structured JSON, and CPT codes from mini-prompt.
    
    This is the main entry point for the reporting pipeline:
    1. Parse mini-prompt → facts
    2. Generate synoptic report with RCS-18 compliance
    3. Structure to JSON via LLM
    4. Validate quality and safety
    5. Map to Case and generate CPT codes
    
    Args:
        miniprompt: Brief procedure description
        patient_ctx: Patient demographics and context
        llm_client: LLM client for structuring (uses mock if None)
        validate: Run quality validators
        auto_fill: Auto-fill safe defaults for missing fields
        
    Returns:
        Dictionary containing:
            - report_text: Generated synoptic report
            - structured_json: IPProcedureReport as dict
            - validation: Quality check results
            - cpt_codes: Generated CPT bundle
            - warnings: Any coding warnings
    """
    try:
        # Step 1: Generate synoptic report
        logger.info("Generating synoptic report from mini-prompt")
        report_result = render_report(miniprompt, patient_ctx)
        report_text = report_result["text"]
        
        # Step 2: Structure to JSON
        logger.info("Structuring report to JSON")
        if llm_client is None:
            logger.warning("No LLM client provided, using mock")
            llm_client = MockLLMClient()
        
        ip_report = structure_to_json(report_text, llm_client)
        
        # Step 3: Auto-fill defaults if requested
        if auto_fill:
            logger.info("Auto-filling safe defaults")
            ip_report = auto_fill_defaults(ip_report)
        
        # Step 4: Validate if requested
        validation_results = {}
        validation_summary = ""
        if validate:
            logger.info("Running quality validators")
            validation_results = run_all_validators(ip_report)
            validation_summary = get_validation_summary(validation_results)
            logger.info(f"Validation summary:\n{validation_summary}")
        
        # Step 5: Generate CPT codes
        logger.info("Generating CPT codes")
        case = case_from_ip_report(ip_report)
        kb = CodingKB()
        coding_result = code_case(case, kb)
        
        # Compile results
        return {
            "success": True,
            "report_text": report_text,
            "parsed_facts": report_result["parsed"],
            "structured_json": ip_report.dict(exclude_none=True),
            "validation": {
                "results": validation_results,
                "summary": validation_summary
            },
            "cpt_codes": {
                "professional": coding_result.professional_codes,
                "technical": coding_result.technical_codes,
                "combined": coding_result.all_codes()
            },
            "warnings": coding_result.warnings
        }
        
    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "report_text": None,
            "structured_json": None,
            "validation": {},
            "cpt_codes": {},
            "warnings": [f"Pipeline failed: {e}"]
        }

def process_batch(
    miniprompts: list,
    patient_ctx: Optional[Dict] = None,
    llm_client: Optional[Any] = None
) -> list:
    """Process multiple mini-prompts in batch.
    
    Args:
        miniprompts: List of mini-prompt strings
        patient_ctx: Shared patient context
        llm_client: LLM client for structuring
        
    Returns:
        List of results from generate_report_and_codes
    """
    results = []
    for i, prompt in enumerate(miniprompts):
        logger.info(f"Processing prompt {i+1}/{len(miniprompts)}")
        result = generate_report_and_codes(prompt, patient_ctx, llm_client)
        results.append(result)
    return results

def validate_miniprompt(miniprompt: str) -> Dict[str, Any]:
    """Quick validation of mini-prompt without full pipeline.
    
    Args:
        miniprompt: Brief procedure description
        
    Returns:
        Validation results
    """
    from .parser import parse_miniprompt
    
    parsed = parse_miniprompt(miniprompt)
    
    issues = []
    warnings = []
    
    # Check procedure detection
    if parsed.proc_key == "standard_bronchoscopy_optional_ebus_lma":
        warnings.append("Procedure type not clearly identified, defaulting to standard bronchoscopy")
    
    # Check for critical information
    if not parsed.targets:
        issues.append("No anatomical targets identified")
    
    if not parsed.tokens:
        warnings.append("No specific procedural details extracted")
    
    # Check for safety information
    if "bleeding" not in parsed.complications and "pneumothorax" not in parsed.complications:
        warnings.append("No explicit complications status mentioned")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "parsed": parsed
    }

def example_run():
    """Run example mini-prompt through pipeline."""
    miniprompt = """Ion robotic bronchoscopy, normal exam, anterior segment right lower lobe, 
    No radial signal on first attempt. Cios spin, readjusted. + radial signal, 
    repeat spin, tool in lesion (23G needle, ROSE positive), biopsy with 1.1 cryo ×3 
    and 5 needle passes. No complications, minimal bleeding."""
    
    patient_ctx = {
        "patient_name": "John Doe",
        "dod_id": "123456789",
        "date": "2024-01-15",
        "location": "OR 1",
        "physician_name": "Dr. Smith",
        "physician_title": "MD",
        "datetime": "2024-01-15 10:30"
    }
    
    result = generate_report_and_codes(miniprompt, patient_ctx)
    
    if result["success"]:
        print("=== REPORT ===")
        print(result["report_text"][:500] + "...")
        print("\n=== VALIDATION ===")
        print(result["validation"]["summary"])
        print("\n=== CPT CODES ===")
        for code in result["cpt_codes"]["combined"]:
            print(f"  {code}")
    else:
        print(f"Error: {result['error']}")
    
    return result

if __name__ == "__main__":
    # Run example when module is executed directly
    example_run()