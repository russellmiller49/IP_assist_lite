#!/usr/bin/env python3
"""
Gradio UI for IP Assist Lite with GPT-5 Integration
Test interface for GPT-5 medical response generation
"""

import sys
from pathlib import Path
from typing import Dict, Any
import json
import logging
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import gradio as gr
from llm.gpt5_medical import GPT5MedicalGenerator, num_tokens
from safety.contraindication_tool import CONTRAINDICATION_TOOL, FORCE_DECISION_TOOL
from utils.serialization import to_jsonable

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize GPT-5 generator
gpt5_generator = None

def get_gpt5_generator(model="gpt-5-mini", reasoning="medium", verbosity="medium"):
    """Get or create GPT-5 generator with specified settings."""
    global gpt5_generator
    gpt5_generator = GPT5MedicalGenerator(
        model=model,
        max_output=8000,
        reasoning_effort=reasoning,
        verbosity=verbosity
    )
    return gpt5_generator

def process_medical_query(
    query: str,
    model: str,
    reasoning_effort: str,
    verbosity: str,
    include_context: bool,
    test_context: str
) -> tuple:
    """Process a medical query using GPT-5."""
    
    if not query.strip():
        return "", "Please enter a query", "{}"
    
    try:
        # Initialize generator with selected settings
        gen = get_gpt5_generator(model, reasoning_effort, verbosity)
        
        # Prepare system prompt
        system_prompt = """You are an expert interventional pulmonology assistant.
Provide accurate, evidence-based medical information.
Cite sources as [A1-PAPOIP-2025], [A2-Practical-Guide], etc.
If uncertain, state so explicitly.
For emergency situations, provide immediate actionable guidance."""
        
        # Prepare user prompt
        if include_context and test_context.strip():
            user_prompt = f"Context:\n{test_context}\n\nQuestion: {query}"
        else:
            user_prompt = query
        
        # Count tokens
        token_count = num_tokens(system_prompt) + num_tokens(user_prompt)
        
        # Generate response
        start_time = datetime.now()
        result = gen.generate(
            system=system_prompt,
            user=user_prompt
        )
        elapsed = (datetime.now() - start_time).total_seconds()
        
        # Format response
        response = result.get("text", "No response generated")
        
        # Create metadata
        usage = result.get("usage", {})
        # Convert usage to serializable format
        serializable_usage = {}
        if usage:
            for key, value in usage.items():
                if hasattr(value, '__dict__'):
                    serializable_usage[key] = str(value)
                else:
                    serializable_usage[key] = value
        
        metadata = {
            "model": model,
            "reasoning_effort": reasoning_effort,
            "verbosity": verbosity,
            "input_tokens": token_count,
            "response_time_seconds": round(elapsed, 2),
            "usage": serializable_usage,
            "timestamp": datetime.now().isoformat()
        }
        
        status = f"✅ Generated in {elapsed:.2f}s | Input tokens: {token_count}"
        
        return response, status, json.dumps(to_jsonable(metadata), indent=2, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"Error processing query: {e}")
        error_msg = f"❌ Error: {str(e)}"
        error_metadata = {
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
        return "", error_msg, json.dumps(to_jsonable(error_metadata), indent=2, ensure_ascii=False)

def test_safety_decision(
    procedure: str,
    patient_context: str,
    model: str
) -> tuple:
    """Test GPT-5 safety decision with structured output."""
    
    if not procedure.strip() or not patient_context.strip():
        return "", "Please enter both procedure and patient context", "{}"
    
    try:
        gen = get_gpt5_generator(model, "high", "low")  # High reasoning for safety
        
        system_prompt = """You are a medical safety evaluator.
Analyze the procedure and patient context for contraindications and risks.
You MUST use the emit_decision tool to provide a structured safety assessment.
Base your decision on medical evidence and safety protocols."""
        
        user_prompt = f"""Procedure: {procedure}
Patient Context: {patient_context}

Evaluate if this procedure should proceed based on safety considerations."""
        
        # Generate with forced tool use
        result = gen.generate(
            system=system_prompt,
            user=user_prompt,
            tools=CONTRAINDICATION_TOOL,
            tool_choice=FORCE_DECISION_TOOL
        )
        
        # Extract tool call decision
        tool_calls = result.get("tool_calls", [])
        if tool_calls:
            decision = tool_calls[0]
            # Format decision nicely
            decision_text = f"""
**Safety Assessment**

**Procedure:** {decision.get('function', {}).get('arguments', {}).get('procedure', 'Unknown')}
**Decision:** {'✅ PROCEED' if decision.get('function', {}).get('arguments', {}).get('proceed', False) else '❌ DO NOT PROCEED'}
**Risk Level:** {decision.get('function', {}).get('arguments', {}).get('risk_level', 'Unknown').upper()}

**Reasons:**
"""
            reasons = decision.get('function', {}).get('arguments', {}).get('reasons', [])
            for reason in reasons:
                decision_text += f"• {reason}\n"
            
            notes = decision.get('function', {}).get('arguments', {}).get('notes', '')
            if notes:
                decision_text += f"\n**Additional Notes:** {notes}"
            
            status = "✅ Safety assessment completed"
            metadata = {
                "model": model,
                "tool_call": "emit_decision",
                "decision": decision.get('function', {}).get('arguments', {}),
                "timestamp": datetime.now().isoformat()
            }
        else:
            decision_text = result.get("text", "No structured decision generated")
            status = "⚠️ No structured decision (free text response)"
            metadata = {
                "model": model,
                "response_type": "text",
                "timestamp": datetime.now().isoformat()
            }
        
        return decision_text, status, json.dumps(to_jsonable(metadata), indent=2, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"Error in safety decision: {e}")
        error_msg = f"❌ Error: {str(e)}"
        return "", error_msg, "{}"

# Example queries for testing
EXAMPLE_MEDICAL_QUERIES = [
    "What are the contraindications for rigid bronchoscopy?",
    "Management protocol for massive hemoptysis >300ml",
    "CPT code and RVU for EBUS-TBNA with needle aspiration",
    "Pediatric dosing for lidocaine in flexible bronchoscopy",
    "Step-by-step fiducial marker placement for SBRT",
    "Compare Zephyr vs Spiration valves for BLVR"
]

EXAMPLE_PROCEDURES = [
    "Rigid bronchoscopy",
    "Flexible bronchoscopy",
    "EBUS-TBNA",
    "Endobronchial valve placement",
    "Photodynamic therapy"
]

EXAMPLE_PATIENT_CONTEXTS = [
    "85-year-old with severe COPD, FEV1 25%, on home oxygen",
    "Pregnant patient, 28 weeks gestation, with suspected sarcoidosis",
    "Child age 3 with suspected foreign body aspiration",
    "Patient with bleeding disorder, INR 3.5, platelets 40k",
    "Recent MI 2 weeks ago, ejection fraction 30%"
]

EXAMPLE_CONTEXT = """From PAPOIP 2025 Guidelines:
- Fiducial markers: Place 3-6 markers, 1.5-5cm apart, non-collinear arrangement
- MT Competency: Requires 20 supervised procedures, 10/year maintenance
- SEMS in benign disease: Contraindicated in resectable disease
- Emergency hemoptysis: Lateral decubitus (bleeding side down), secure airway"""

def build_gpt5_test_interface():
    """Build the GPT-5 test interface."""
    
    with gr.Blocks(title="IP Assist GPT-5 Test", theme=gr.themes.Soft()) as demo:
        gr.Markdown("""
        # 🧪 IP Assist Lite - GPT-5 Testing Interface
        ### Test GPT-5 Medical Response Generation
        
        **Features:**
        - 🤖 GPT-5 model variants (full, mini, nano)
        - 🧠 Reasoning effort control (minimal to high)
        - 📝 Verbosity settings
        - ⚕️ Structured safety decisions
        - 📊 Token counting and performance metrics
        """)
        
        with gr.Tabs():
            # Medical Query Tab
            with gr.Tab("Medical Query Generation"):
                with gr.Row():
                    with gr.Column(scale=2):
                        query_input = gr.Textbox(
                            label="Medical Query",
                            placeholder="Enter your medical question...",
                            lines=3
                        )
                        
                        include_context = gr.Checkbox(
                            label="Include test context",
                            value=False
                        )
                        
                        context_input = gr.Textbox(
                            label="Test Context (optional)",
                            placeholder="Add medical context or guidelines here...",
                            lines=5,
                            value=EXAMPLE_CONTEXT,
                            visible=False
                        )
                        
                        include_context.change(
                            fn=lambda x: gr.update(visible=x),
                            inputs=include_context,
                            outputs=context_input
                        )
                        
                        gr.Examples(
                            examples=EXAMPLE_MEDICAL_QUERIES,
                            inputs=query_input,
                            label="Example Queries"
                        )
                    
                    with gr.Column(scale=1):
                        model_select = gr.Dropdown(
                            choices=["gpt-5", "gpt-5-mini", "gpt-5-nano"],
                            value="gpt-5-mini",
                            label="GPT-5 Model"
                        )
                        
                        reasoning_select = gr.Dropdown(
                            choices=["minimal", "low", "medium", "high"],
                            value="medium",
                            label="Reasoning Effort"
                        )
                        
                        verbosity_select = gr.Dropdown(
                            choices=["low", "medium", "high"],
                            value="medium",
                            label="Verbosity"
                        )
                        
                        submit_btn = gr.Button("🚀 Generate Response", variant="primary")
                        status_output = gr.Textbox(
                            label="Status",
                            interactive=False,
                            lines=2
                        )
                
                response_output = gr.Textbox(
                    label="GPT-5 Response",
                    lines=15,
                    interactive=False
                )
                
                metadata_output = gr.JSON(label="Response Metadata")
                
                submit_btn.click(
                    fn=process_medical_query,
                    inputs=[
                        query_input,
                        model_select,
                        reasoning_select,
                        verbosity_select,
                        include_context,
                        context_input
                    ],
                    outputs=[response_output, status_output, metadata_output]
                )
            
            # Safety Decision Tab
            with gr.Tab("Safety Decision Testing"):
                gr.Markdown("""
                ### Test Structured Safety Decisions
                Uses GPT-5 with JSON-mode tool calling to provide structured procedural safety assessments.
                """)
                
                with gr.Row():
                    with gr.Column():
                        procedure_input = gr.Dropdown(
                            choices=EXAMPLE_PROCEDURES,
                            label="Procedure",
                            allow_custom_value=True
                        )
                        
                        patient_context = gr.Textbox(
                            label="Patient Context",
                            placeholder="Describe patient condition, comorbidities, contraindications...",
                            lines=5
                        )
                        
                        model_safety = gr.Dropdown(
                            choices=["gpt-5", "gpt-5-mini"],
                            value="gpt-5-mini",
                            label="Model for Safety Assessment"
                        )
                        
                        assess_btn = gr.Button("⚕️ Assess Safety", variant="primary")
                        
                        gr.Examples(
                            examples=[[p, c] for p in EXAMPLE_PROCEDURES[:2] 
                                     for c in EXAMPLE_PATIENT_CONTEXTS[:2]],
                            inputs=[procedure_input, patient_context],
                            label="Example Scenarios"
                        )
                    
                    with gr.Column():
                        safety_status = gr.Textbox(
                            label="Assessment Status",
                            interactive=False,
                            lines=1
                        )
                
                safety_output = gr.Markdown(label="Safety Assessment")
                safety_metadata = gr.JSON(label="Decision Metadata")
                
                assess_btn.click(
                    fn=test_safety_decision,
                    inputs=[procedure_input, patient_context, model_safety],
                    outputs=[safety_output, safety_status, safety_metadata]
                )
            
            # Model Comparison Tab
            with gr.Tab("Model Comparison"):
                gr.Markdown("""
                ### Compare GPT-5 Model Variants
                Test the same query across different models and settings to compare performance.
                """)
                
                comparison_query = gr.Textbox(
                    label="Test Query",
                    value="List contraindications for rigid bronchoscopy in a concise format",
                    lines=2
                )
                
                compare_btn = gr.Button("🔄 Compare All Models", variant="primary")
                
                with gr.Row():
                    gpt5_full = gr.Textbox(label="GPT-5 Full", lines=8, interactive=False)
                    gpt5_mini = gr.Textbox(label="GPT-5 Mini", lines=8, interactive=False)
                    gpt5_nano = gr.Textbox(label="GPT-5 Nano", lines=8, interactive=False)
                
                comparison_stats = gr.JSON(label="Comparison Statistics")
                
                def compare_models(query):
                    results = {}
                    outputs = []
                    
                    for model in ["gpt-5", "gpt-5-mini", "gpt-5-nano"]:
                        try:
                            gen = get_gpt5_generator(model, "medium", "low")
                            start = datetime.now()
                            result = gen.generate(
                                system="You are an IP expert. Be concise.",
                                user=query
                            )
                            elapsed = (datetime.now() - start).total_seconds()
                            
                            response = result.get("text", "No response")
                            outputs.append(response)
                            
                            results[model] = {
                                "response_time": round(elapsed, 2),
                                "response_length": len(response),
                                "token_count": num_tokens(response)
                            }
                        except Exception as e:
                            outputs.append(f"Error: {str(e)}")
                            results[model] = {"error": str(e)}
                    
                    return outputs[0], outputs[1], outputs[2], results
                
                compare_btn.click(
                    fn=compare_models,
                    inputs=comparison_query,
                    outputs=[gpt5_full, gpt5_mini, gpt5_nano, comparison_stats]
                )
        
        gr.Markdown("""
        ---
        ### 📝 Notes
        - **Model Selection**: GPT-5 for maximum accuracy, Mini for balance, Nano for speed
        - **Reasoning Effort**: Higher = more thorough analysis but slower
        - **Verbosity**: Controls response length and detail level
        - **Safety Decisions**: Uses structured JSON output for consistent formatting
        
        ### ⚠️ Testing Notice
        This is a testing interface. Ensure OPENAI_API_KEY is set in your .env file.
        """)
    
    return demo

# Main execution
if __name__ == "__main__":
    demo = build_gpt5_test_interface()
    demo.launch(
        server_name="127.0.0.1",  # Use localhost instead of 0.0.0.0
        server_port=7861,  # Different port from main app
        share=True,  # Create shareable link
        show_error=True
    )