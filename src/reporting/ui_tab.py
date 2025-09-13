"""Gradio UI tab for medical report generation."""

import gradio as gr
import json
import logging
from typing import Dict, Any, Optional, Tuple
from .integration import generate_report_and_codes, validate_miniprompt
from .llm_structurer import MockLLMClient

logger = logging.getLogger(__name__)

def build_reporter_tab():
    """Build the Gradio tab for report generation.
    
    Returns:
        Gradio Tab component with report generation interface
    """
    with gr.Tab("📝 Report Generator"):
        gr.Markdown("""
        ## Medical Report Generator
        
        Enter a brief procedure description (mini-prompt) to generate:
        1. **Synoptic Report** - RCS-18 compliant structured report
        2. **JSON Structure** - Validated procedure data
        3. **CPT Codes** - Automated coding suggestions
        """)
        
        with gr.Row():
            with gr.Column(scale=1):
                # Input section
                gr.Markdown("### Procedure Description")
                miniprompt_input = gr.Textbox(
                    label="Mini-Prompt",
                    placeholder="e.g., Ion robotic bronchoscopy RLL, CBCT confirmation, 23G TBNA x5 passes ROSE positive, cryo x3",
                    lines=4
                )
                
                # Patient context (optional)
                with gr.Accordion("Patient Information (Optional)", open=False):
                    patient_name = gr.Textbox(label="Patient Name", value="[Name]")
                    dod_id = gr.Textbox(label="DoD ID", value="[DoD ID]")
                    procedure_date = gr.Textbox(label="Date", value="2024-01-15")
                    location = gr.Textbox(label="Location", value="OR 1")
                    physician = gr.Textbox(label="Physician", value="[Physician Name], MD")
                
                # Options
                with gr.Accordion("Options", open=False):
                    validate_quality = gr.Checkbox(label="Run Quality Validators", value=True)
                    auto_fill = gr.Checkbox(label="Auto-fill Safe Defaults", value=True)
                    use_llm = gr.Checkbox(label="Use LLM for Structuring", value=False)
                
                # Action buttons
                with gr.Row():
                    validate_btn = gr.Button("🔍 Validate Only", variant="secondary")
                    generate_btn = gr.Button("🚀 Generate Report", variant="primary")
                    clear_btn = gr.Button("🗑️ Clear", variant="secondary")
            
            with gr.Column(scale=2):
                # Output section with tabs
                with gr.Tabs():
                    with gr.TabItem("📄 Report"):
                        report_output = gr.Textbox(
                            label="Generated Report",
                            lines=20,
                            max_lines=30,
                            interactive=False
                        )
                    
                    with gr.TabItem("🔧 JSON"):
                        json_output = gr.JSON(
                            label="Structured Data"
                        )
                    
                    with gr.TabItem("💊 CPT Codes"):
                        codes_output = gr.Textbox(
                            label="Generated CPT Codes",
                            lines=10,
                            interactive=False
                        )
                    
                    with gr.TabItem("✅ Validation"):
                        validation_output = gr.Textbox(
                            label="Quality Check Results",
                            lines=15,
                            interactive=False
                        )
        
        # Example prompts
        gr.Markdown("### Example Mini-Prompts")
        example_prompts = gr.Examples(
            examples=[
                ["Ion robotic bronchoscopy, RLL anterior segment, CBCT confirmation, 23G TBNA x5 ROSE positive, 1.1mm cryo x3, minimal bleeding"],
                ["EBUS staging via ETT, stations 4R (12mm), 7 (8mm), 11R (15mm), all with 22G x3 passes, ROSE adequate"],
                ["PDT in ICU, bronch guided, rings 2-3, Ciaglia Blue Rhino kit, size 8 Shiley, no complications"],
                ["Monarch navigation to LUL apical-posterior, rEBUS concentric, digital tomosynthesis, forceps biopsy x6"],
                ["Therapeutic cryotherapy for obstructing tracheal tumor, 2.4mm probe, 3 cycles 60s freeze, improved patency 30% to 80%"],
            ],
            inputs=miniprompt_input
        )
        
        # Event handlers
        def validate_only(miniprompt):
            """Quick validation without full generation."""
            try:
                result = validate_miniprompt(miniprompt)
                
                output = "### Validation Results\n\n"
                output += f"**Valid**: {'✅ Yes' if result['valid'] else '❌ No'}\n\n"
                
                if result['issues']:
                    output += "**Issues:**\n"
                    for issue in result['issues']:
                        output += f"- ❌ {issue}\n"
                    output += "\n"
                
                if result['warnings']:
                    output += "**Warnings:**\n"
                    for warning in result['warnings']:
                        output += f"- ⚠️ {warning}\n"
                    output += "\n"
                
                output += "**Parsed Information:**\n"
                output += f"- Procedure: {result['parsed'].proc_key}\n"
                output += f"- Targets: {len(result['parsed'].targets)} identified\n"
                output += f"- Imaging: {', '.join([k for k, v in result['parsed'].adjuncts.items() if v])}\n"
                
                return output
            except Exception as e:
                return f"❌ Validation error: {str(e)}"
        
        def generate_report(
            miniprompt, 
            patient_name, 
            dod_id, 
            procedure_date,
            location,
            physician,
            validate_quality,
            auto_fill,
            use_llm
        ):
            """Generate complete report and codes."""
            try:
                # Build patient context
                patient_ctx = {
                    "patient_name": patient_name or "[Patient Name]",
                    "dod_id": dod_id or "[DoD ID]",
                    "date": procedure_date or "[Date]",
                    "location": location or "[Location]",
                    "physician_name": physician.split(",")[0] if physician else "[Physician]",
                    "physician_title": "MD",
                    "datetime": f"{procedure_date} [Time]"
                }
                
                # Select LLM client
                llm_client = None if not use_llm else MockLLMClient()
                
                # Generate report and codes
                result = generate_report_and_codes(
                    miniprompt=miniprompt,
                    patient_ctx=patient_ctx,
                    llm_client=llm_client,
                    validate=validate_quality,
                    auto_fill=auto_fill
                )
                
                if not result["success"]:
                    return (
                        f"❌ Error: {result['error']}", 
                        {}, 
                        "",
                        "Generation failed"
                    )
                
                # Format report
                report = result["report_text"]
                
                # Format JSON (pretty print)
                json_data = result["structured_json"] if result["structured_json"] else {}
                
                # Format CPT codes
                codes_text = "### Professional Codes\n"
                for code in result["cpt_codes"].get("professional", []):
                    codes_text += f"  {code}\n"
                
                codes_text += "\n### Technical Codes\n"
                for code in result["cpt_codes"].get("technical", []):
                    codes_text += f"  {code}\n"
                
                if result["warnings"]:
                    codes_text += "\n### ⚠️ Warnings\n"
                    for warning in result["warnings"]:
                        codes_text += f"  - {warning}\n"
                
                # Format validation
                validation_text = result["validation"]["summary"]
                
                return report, json_data, codes_text, validation_text
                
            except Exception as e:
                logger.error(f"Report generation error: {e}", exc_info=True)
                return (
                    f"❌ Error: {str(e)}", 
                    {}, 
                    "",
                    f"Error: {str(e)}"
                )
        
        def clear_all():
            """Clear all inputs and outputs."""
            return "", "[Name]", "[DoD ID]", "2024-01-15", "OR 1", "[Physician Name], MD", "", {}, "", ""
        
        # Wire up events
        validate_btn.click(
            fn=validate_only,
            inputs=[miniprompt_input],
            outputs=[validation_output]
        )
        
        generate_btn.click(
            fn=generate_report,
            inputs=[
                miniprompt_input,
                patient_name,
                dod_id,
                procedure_date,
                location,
                physician,
                validate_quality,
                auto_fill,
                use_llm
            ],
            outputs=[
                report_output,
                json_output,
                codes_output,
                validation_output
            ]
        )
        
        clear_btn.click(
            fn=clear_all,
            outputs=[
                miniprompt_input,
                patient_name,
                dod_id,
                procedure_date,
                location,
                physician,
                report_output,
                json_output,
                codes_output,
                validation_output
            ]
        )

# Standalone function for integration
def build():
    """Build function for integration with main app."""
    return build_reporter_tab()

# Demo app for testing
def create_demo_app():
    """Create standalone demo app."""
    with gr.Blocks(title="IP Report Generator") as demo:
        gr.Markdown("# IP Assist - Medical Report Generator")
        build_reporter_tab()
    return demo

if __name__ == "__main__":
    # Run standalone demo
    demo = create_demo_app()
    demo.launch(
        server_name="0.0.0.0",
        server_port=7862,
        share=False
    )