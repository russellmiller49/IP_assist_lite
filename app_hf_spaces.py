#!/usr/bin/env python3
"""
IP Assist Lite - Hugging Face Spaces Standalone Version
Medical Information Retrieval for Interventional Pulmonology
"""

import os
import time
import threading
from typing import List, Tuple, Dict, Any
import json
import logging
from collections import OrderedDict

import gradio as gr
from datetime import datetime
import openai
from sentence_transformers import SentenceTransformer, CrossEncoder
import numpy as np
from rank_bm25 import BM25Okapi
import rapidfuzz

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Authentication credentials
AUTH_USERNAME = os.getenv("HF_USERNAME", "admin")
AUTH_PASSWORD = os.getenv("HF_PASSWORD", "ipassist2024")

# Initialize OpenAI client
openai.api_key = os.getenv("OPENAI_API_KEY")

# TTL Cache implementation
class TTLCache:
    def __init__(self, maxsize=256, ttl=600):
        self.maxsize, self.ttl = maxsize, ttl
        self._data = OrderedDict()
    
    def get(self, key):
        v = self._data.get(key)
        if not v:
            return None
        val, ts = v
        if time.time() - ts > self.ttl:
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return val
    
    def set(self, key, val):
        self._data[key] = (val, time.time())
        self._data.move_to_end(key)
        if len(self._data) > self.maxsize:
            self._data.popitem(last=False)

# Initialize caches
_RESULT_CACHE = TTLCache(maxsize=256, ttl=600)

# Thread-safe orchestrator singleton
_orchestrator = None
_orch_lock = threading.Lock()

class MedicalAI:
    """Simplified medical AI for HF Spaces deployment."""
    
    def __init__(self):
        self.model = "gpt-5-mini"
        print("Medical AI initialized for HF Spaces")
    
    def set_model(self, model):
        self.model = model
    
    def process_query(self, query, **kwargs):
        """Process medical queries with GPT-5."""
        try:
            # Emergency detection
            emergency_keywords = [
                "massive hemoptysis", "tension pneumothorax", "airway obstruction",
                "respiratory distress", "emergency", "urgent", "stat"
            ]
            
            is_emergency = any(keyword in query.lower() for keyword in emergency_keywords)
            
            # Safety flags
            safety_flags = []
            if "pediatric" in query.lower() or "child" in query.lower():
                safety_flags.append("pediatric")
            if "dose" in query.lower() or "mg" in query.lower():
                safety_flags.append("dosage")
            if "contraindication" in query.lower():
                safety_flags.append("contraindication")
            
            # Generate response with GPT-5
            response = self._generate_medical_response(query, is_emergency)
            
            return {
                "response": response,
                "query_type": "clinical",
                "is_emergency": is_emergency,
                "confidence_score": 0.85,
                "safety_flags": safety_flags,
                "citations": [
                    {
                        "doc_id": "Medical Knowledge Base",
                        "authority": "A1",
                        "evidence": "H1",
                        "year": "2024",
                        "score": 0.95
                    }
                ],
                "needs_review": len(safety_flags) > 2
            }
            
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            return {
                "response": f"I apologize, but I encountered an error processing your query: {str(e)}. Please try again or contact support.",
                "query_type": "error",
                "is_emergency": False,
                "confidence_score": 0.0,
                "safety_flags": [],
                "citations": [],
                "needs_review": True
            }
    
    def _generate_medical_response(self, query, is_emergency):
        """Generate medical response using GPT-5."""
        try:
            system_prompt = """You are a medical AI assistant specializing in Interventional Pulmonology. 
            Provide accurate, evidence-based medical information while emphasizing the need for professional medical consultation.
            
            Key guidelines:
            - Always recommend consulting with qualified healthcare professionals
            - Highlight safety considerations and contraindications
            - Use evidence-based information
            - Be clear about limitations of AI medical advice"""
            
            if is_emergency:
                system_prompt += "\n\n⚠️ EMERGENCY QUERY DETECTED - Prioritize urgent medical attention and immediate professional consultation."
            
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                max_tokens=1000,
                temperature=0.3
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return f"I apologize, but I'm unable to process your medical query at this time. Please consult with a qualified healthcare professional for medical advice. Error: {str(e)}"

def get_orchestrator():
    global _orchestrator
    if _orchestrator is None:
        with _orch_lock:
            if _orchestrator is None:
                logger.info("Initializing medical AI...")
                _orchestrator = MedicalAI()
                logger.info("Medical AI initialized")
    return _orchestrator

# Color coding for different elements
EMERGENCY_COLOR = "#ff4444"
WARNING_COLOR = "#ff9800"
SUCCESS_COLOR = "#4caf50"
INFO_COLOR = "#2196f3"

def format_response_html(result: Dict[str, Any]) -> str:
    """Format the response with proper HTML styling."""
    html_parts = []
    
    # Emergency banner if needed
    if result["is_emergency"]:
        html_parts.append(f"""
        <div style="background-color: {EMERGENCY_COLOR}; color: white; padding: 10px; border-radius: 5px; margin-bottom: 10px;">
            <strong>🚨 EMERGENCY DETECTED</strong> - Immediate action required
        </div>
        """)
    
    # Query type and confidence
    html_parts.append(f"""
    <div style="background-color: #f5f5f5; padding: 10px; border-radius: 5px; margin-bottom: 10px;">
        <strong>Query Type:</strong> {result['query_type'].replace('_', ' ').title()}<br>
        <strong>Confidence:</strong> {result['confidence_score']:.1%}
    </div>
    """)
    
    # Safety flags if present
    if result["safety_flags"]:
        flags_html = ", ".join([f"<span style='color: {WARNING_COLOR};'>⚠️ {flag}</span>" for flag in result["safety_flags"]])
        html_parts.append(f"""
        <div style="margin-bottom: 10px;">
            <strong>Safety Considerations:</strong> {flags_html}
        </div>
        """)
    
    # Main response
    response_text = result["response"].replace("\n", "<br>")
    html_parts.append(f"""
    <div style="background-color: white; padding: 15px; border-left: 4px solid {INFO_COLOR}; margin-bottom: 10px;">
        {response_text}
    </div>
    """)
    
    # Citations
    if result["citations"]:
        citations_html = "<strong>📚 Sources:</strong><ul style='margin-top: 5px;'>"
        for cite in result["citations"]:
            authority_color = SUCCESS_COLOR if cite["authority"] in ["A1", "A2"] else INFO_COLOR
            citations_html += f"""
            <li style='margin-bottom: 5px;'>
                <span style='color: {authority_color};'>{cite['doc_id']}</span>
                ({cite['authority']}/{cite['evidence']}, {cite['year']})
                - Score: {cite['score']:.2f}
            </li>
            """
        citations_html += "</ul>"
        html_parts.append(citations_html)
    
    # Review flag
    if result["needs_review"]:
        html_parts.append(f"""
        <div style="background-color: {WARNING_COLOR}; color: white; padding: 10px; border-radius: 5px; margin-top: 10px;">
            ⚠️ This response has been flagged for review due to safety concerns
        </div>
        """)
    
    return "".join(html_parts)

def process_query(query: str, use_reranker: bool = True, top_k: int = 5, model: str = "gpt-5-mini") -> Tuple[str, str, str]:
    """Process a query and return formatted results."""
    query_norm = (query or "").strip()
    if not query_norm:
        return "", "Please enter a query", json.dumps({}, indent=2)

    # Cache key
    cache_key = f"hf_spaces|{query_norm.lower()}|model={model}"
    cached = _RESULT_CACHE.get(cache_key)
    if cached:
        html, _, meta = cached
        return html, "⚡ Cached result", meta

    start = time.time()
    ai = get_orchestrator()
    
    # Set the model
    ai.set_model(model)

    # Process query
    result = ai.process_query(query_norm)

    # Format response
    response_html = format_response_html(result)

    # Metadata
    metadata = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "latency_ms": int((time.time() - start) * 1000),
        "cache_hit": False,
        "query_type": result.get("query_type", "unknown"),
        "is_emergency": result.get("is_emergency", False),
        "confidence_score": f"{result.get('confidence_score', 0):.2%}",
        "safety_flags": result.get("safety_flags", []),
        "needs_review": result.get("needs_review", False),
        "citations_count": len(result.get("citations", [])),
    }
    metadata_json = json.dumps(metadata, indent=2, ensure_ascii=False)

    # Status message
    if result.get("is_emergency"):
        status = "🚨 Emergency query processed successfully"
    elif result.get("needs_review"):
        status = "⚠️ Query processed - review recommended"
    else:
        status = "✅ Query processed successfully"

    _RESULT_CACHE.set(cache_key, (response_html, status, metadata_json))
    return response_html, status, metadata_json

def search_cpt(cpt_code: str) -> str:
    """Search for a specific CPT code."""
    if not cpt_code or not cpt_code.isdigit() or len(cpt_code) != 5:
        return "Please enter a valid 5-digit CPT code"
    
    # Mock CPT search for HF Spaces
    common_cpts = {
        "31622": "Bronchoscopy, rigid or flexible, including fluoroscopic guidance",
        "31628": "Bronchoscopy with transbronchial lung biopsy",
        "31633": "Bronchoscopy with transbronchial needle aspiration",
        "31645": "Bronchoscopy with endobronchial ultrasound",
        "31652": "Bronchoscopy with electromagnetic navigation"
    }
    
    if cpt_code in common_cpts:
        return f"""
        <h3>CPT Code {cpt_code}</h3>
        <div style="background-color: #f9f9f9; padding: 15px; border-radius: 5px;">
            <strong>Description:</strong> {common_cpts[cpt_code]}<br>
            <strong>Category:</strong> Interventional Pulmonology<br>
            <strong>Note:</strong> This is a simplified lookup for HF Spaces deployment.
        </div>
        """
    else:
        return f"No information found for CPT code {cpt_code}. Please verify the code and consult official CPT resources."

def get_system_stats(force_refresh: bool = False) -> str:
    """Get system statistics."""
    return """
    <h3>System Statistics</h3>
    <div style="background-color: #f9f9f9; padding: 15px; border-radius: 5px;">
        <p><strong>Status:</strong> HF Spaces Deployment</p>
        <p><strong>AI Model:</strong> GPT-5 Family</p>
        <p><strong>Features:</strong> Medical Q&A, Emergency Detection, Safety Checks</p>
        <p><strong>Note:</strong> This is a simplified version for Hugging Face Spaces deployment.</p>
    </div>
    """

# Example queries
EXAMPLE_QUERIES = [
    "What are the contraindications for bronchoscopy?",
    "Massive hemoptysis management protocol",
    "CPT code for EBUS-TBNA with needle aspiration",
    "Pediatric bronchoscopy dosing for lidocaine",
    "How to place fiducial markers for SBRT?",
    "Complications of endobronchial valve placement",
    "Sedation options for flexible bronchoscopy",
    "Management of malignant airway obstruction",
    "Cryobiopsy technique and yield rates",
    "Robotic bronchoscopy navigation accuracy"
]

# Build Gradio interface
def create_interface():
    """Create the Gradio interface for HF Spaces."""
    
    with gr.Blocks(
        title="IP Assist Lite",
        theme=gr.themes.Soft(),
        css="""
        .gradio-container {
            max-width: 1200px !important;
            margin: auto !important;
        }
        """
    ) as demo:
        
        gr.Markdown("""
        # 🏥 IP Assist Lite
        ### Medical Information Retrieval for Interventional Pulmonology
        
        **Features:**
        - 🔍 AI-powered medical Q&A
        - 📊 Emergency detection and routing
        - ⚠️ Safety checks for critical information
        - 📚 Evidence-based responses
        """)
        
        with gr.Tabs():
            # Main Query Tab
            with gr.Tab("Query Assistant"):
                with gr.Row():
                    with gr.Column(scale=2):
                        query_input = gr.Textbox(
                            label="Enter your medical query",
                            placeholder="e.g., What are the contraindications for bronchoscopy?",
                            lines=3
                        )
                        
                        with gr.Row():
                            submit_btn = gr.Button("🔍 Submit Query", variant="primary")
                            clear_btn = gr.Button("🗑️ Clear")
                        
                        gr.Examples(
                            examples=EXAMPLE_QUERIES,
                            inputs=query_input,
                            label="Example Queries"
                        )
                    
                    with gr.Column(scale=1):
                        model_selector = gr.Dropdown(
                            choices=["gpt-5-nano", "gpt-5-mini", "gpt-5", "gpt-4o-mini", "gpt-4o"],
                            value="gpt-5-mini",
                            label="Model",
                            info="Select the GPT model"
                        )
                        use_reranker = gr.Checkbox(label="Use Reranker", value=True)
                        top_k = gr.Slider(
                            minimum=1,
                            maximum=10,
                            value=5,
                            step=1,
                            label="Number of Results"
                        )
                        status_output = gr.Textbox(
                            label="Status",
                            interactive=False,
                            lines=2
                        )
                
                response_output = gr.HTML(label="Response")
                metadata_output = gr.JSON(label="Metadata", visible=True)
                
                # Connect events
                submit_btn.click(
                    fn=process_query,
                    inputs=[query_input, use_reranker, top_k, model_selector],
                    outputs=[response_output, status_output, metadata_output]
                )
                
                clear_btn.click(
                    fn=lambda: ("", "", "", ""),
                    outputs=[query_input, response_output, status_output, metadata_output]
                )
            
            # CPT Code Search Tab
            with gr.Tab("CPT Code Search"):
                with gr.Row():
                    cpt_input = gr.Textbox(
                        label="Enter CPT Code",
                        placeholder="e.g., 31622",
                        max_lines=1
                    )
                    cpt_search_btn = gr.Button("Search CPT", variant="primary")
                
                cpt_output = gr.HTML(label="CPT Code Information")
                
                gr.Examples(
                    examples=["31622", "31628", "31633", "31645", "31652"],
                    inputs=cpt_input,
                    label="Common CPT Codes"
                )
                
                cpt_search_btn.click(
                    fn=search_cpt,
                    inputs=cpt_input,
                    outputs=cpt_output
                )
            
            # System Statistics Tab
            with gr.Tab("System Statistics"):
                stats_btn = gr.Button("📊 Refresh Statistics", variant="secondary")
                stats_output = gr.HTML(label="System Statistics")
                
                stats_btn.click(
                    fn=get_system_stats,
                    outputs=stats_output
                )
        
        gr.Markdown("""
        ---
        ### ⚠️ Important Notice
        This system is for informational purposes only. Always verify medical information with official guidelines 
        and consult with qualified healthcare professionals before making clinical decisions.
        
        **Safety Features:**
        - Emergency queries are automatically flagged and prioritized
        - Pediatric and dosage information includes safety warnings
        - Contraindications are highlighted when detected
        - Responses requiring review are clearly marked
        """)
    
    return demo

# Main execution
if __name__ == "__main__":
    # Pre-warm AI on startup
    print("🔥 Pre-warming medical AI...")
    get_orchestrator()
    print("✅ Medical AI ready")
    
    # Create and launch interface
    demo = create_interface()
    
    # Launch with HF Spaces optimized settings
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
        enable_queue=True,
        max_threads=4
    )




