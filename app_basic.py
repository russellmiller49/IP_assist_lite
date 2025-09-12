#!/usr/bin/env python3
"""
IP Assist Lite - Hugging Face Spaces Compatible Version
Medical Information Retrieval for Interventional Pulmonology
"""

import sys
import os
import time
import threading
from pathlib import Path
from typing import List, Tuple, Dict, Any
import json
import logging
from collections import OrderedDict

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

import gradio as gr
from datetime import datetime

# For HF Spaces, we need to handle the import differently
try:
    # Try importing from src (local development)
    from src.orchestration.langgraph_agent import IPAssistOrchestrator
    from src.retrieval.hybrid_retriever import HybridRetriever
    # Import V3 coding module
    from src.coding.ui_tab import build as build_coding_tab
except ImportError:
    # For HF Spaces, we'll create a simplified version
    print("⚠️ Running in HF Spaces mode - using simplified implementation")
    
    # Mock coding tab for HF Spaces
    def build_coding_tab():
        with gr.Tab("📋 Procedural Coding"):
            gr.Markdown("Coding module not available in HF Spaces simplified mode")
    
    # Create a mock orchestrator for HF Spaces
    class IPAssistOrchestrator:
        def __init__(self):
            self.model = "gpt-5-mini"
            print("Mock orchestrator initialized for HF Spaces")
        
        def set_model(self, model):
            self.model = model
        
        def process_query(self, query, **kwargs):
            # Return a mock response for HF Spaces
            return {
                "response": f"Mock response for query: {query}\n\nNote: This is a simplified version for HF Spaces deployment. The full medical AI capabilities require the complete codebase.",
                "query_type": "clinical",
                "is_emergency": False,
                "confidence_score": 0.85,
                "safety_flags": [],
                "citations": [],
                "needs_review": False
            }
    
    class HybridRetriever:
        def __init__(self):
            self.chunks = []
            self.cpt_index = {}
            self.chunk_map = {}

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Authentication credentials (set these in HF Spaces secrets)
AUTH_USERNAME = os.getenv("HF_USERNAME", "admin")
AUTH_PASSWORD = os.getenv("HF_PASSWORD", "ipassist2024")

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
_RESULT_CACHE = TTLCache(
    maxsize=int(os.getenv("RESULT_CACHE_MAX", "256")),
    ttl=int(os.getenv("RESULT_TTL_SEC", "600")),
)
_INDEX_FINGERPRINT = os.getenv("INDEX_FINGERPRINT", "v1")

# Stats cache
_STATS_CACHE = {"html": "", "ts": 0.0}
_STATS_TTL_SEC = int(os.getenv("STATS_TTL_SEC", "900"))

# Thread-safe orchestrator singleton
_orchestrator = None
_orch_lock = threading.Lock()

def get_orchestrator():
    global _orchestrator
    if _orchestrator is None:
        with _orch_lock:
            if _orchestrator is None:
                logger.info("Initializing orchestrator...")
                _orchestrator = IPAssistOrchestrator()
                logger.info("Orchestrator initialized")
    return _orchestrator

# Color coding for different elements
EMERGENCY_COLOR = "#ff4444"
WARNING_COLOR = "#ff9800"
SUCCESS_COLOR = "#4caf50"
INFO_COLOR = "#2196f3"

# Allowed models for HF Space UI (avoid accidental GPT-4 selection)
ALLOWED_MODELS = ["gpt-5-nano", "gpt-5-mini", "gpt-5"]

def _sanitize_model(selected: str | None) -> str:
    m = (selected or os.getenv("IP_GPT5_MODEL", "gpt-5-mini")).strip()
    return m if m in ALLOWED_MODELS else "gpt-5-mini"

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
    
    # Query type, confidence, and model used
    model_used = result.get("model_used") or result.get("llm_model_used") or "—"
    html_parts.append(f"""
    <div style="background-color: #f5f5f5; padding: 10px; border-radius: 5px; margin-bottom: 10px;">
        <strong>Query Type:</strong> {result['query_type'].replace('_', ' ').title()}<br>
        <strong>Confidence:</strong> {result['confidence_score']:.1%}<br>
        <strong>Model:</strong> {model_used}
    </div>
    """)

    # LLM warning banner (e.g., fallback used)
    if result.get("llm_warning"):
        html_parts.append(f"""
        <div style="background-color: {WARNING_COLOR}; color: white; padding: 8px; border-radius: 5px; margin-bottom: 10px;">
            {result.get('llm_warning')}
        </div>
        """)
    
    # LLM error banner (e.g., GPT-5 unavailable or auth issue)
    if result.get("llm_error"):
        html_parts.append(f"""
        <div style="background-color: {EMERGENCY_COLOR}; color: white; padding: 8px; border-radius: 5px; margin-bottom: 10px;">
            ❌ {result.get('llm_error')}
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
                <span style='color: {authority_color};'>{cite['doc_id'][:50]}...</span>
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

    # Budget knobs (two-stage)
    retrieve_m = int(os.getenv("RETRIEVE_M", "30"))
    rerank_n   = int(os.getenv("RERANK_N", "10"))
    k          = max(1, min(int(top_k), rerank_n))

    # Cache key (includes knobs + index version + model)
    cache_key = f"{_INDEX_FINGERPRINT}|{query_norm.lower()}|rerank={bool(use_reranker)}|k={k}|M={retrieve_m}|N={rerank_n}|model={_sanitize_model(model)}"
    cached = _RESULT_CACHE.get(cache_key)
    if cached:
        html, _, meta = cached
        return html, "⚡ Cached result", meta

    start = time.time()
    orch = get_orchestrator()

    # Sanitize and set the model in orchestrator (avoid accidental GPT-4 selection)
    chosen_model = _sanitize_model(model)
    orch.set_model(chosen_model)

    # Call the orchestrator; try a v2 signature first, then fall back safely
    try:
        result = orch.process_query(
            query_norm,
            use_reranker=bool(use_reranker),
            top_k=int(k),
            retrieve_m=int(retrieve_m),
            rerank_n=int(rerank_n),
        )
    except TypeError:
        # Older signature: try passing just the basics
        try:
            result = orch.process_query(
                query_norm,
                use_reranker=bool(use_reranker),
                top_k=int(k),
            )
        except TypeError:
            # Legacy: last resort
            result = orch.process_query(query_norm)

    # Format your existing result as before
    response_html = format_response_html(result)

    # Minimal metadata for quick inspection
    metadata = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "latency_ms": int((time.time() - start) * 1000),
        "reranker_used": bool(use_reranker),
        "top_k": int(k),
        "retrieved_m": int(retrieve_m),
        "rerank_n": int(rerank_n) if use_reranker else 0,
        "cache_hit": False,
        "query_type": result.get("query_type", "unknown"),
        "is_emergency": result.get("is_emergency", False),
        "confidence_score": f"{result.get('confidence_score', 0):.2%}",
        "safety_flags": result.get("safety_flags", []),
        "needs_review": result.get("needs_review", False),
        "citations_count": len(result.get("citations", [])),
        # LLM telemetry
        "model_requested": chosen_model,
        "model_used": result.get("model_used"),
        "llm_warning": result.get("llm_warning"),
        "llm_error": result.get("llm_error"),
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
    
    try:
        orch = get_orchestrator()
        retriever = orch.retriever
        
        if cpt_code in retriever.cpt_index:
            chunk_ids = retriever.cpt_index[cpt_code]
            results_html = f"<h3>Found {len(chunk_ids)} results for CPT {cpt_code}</h3>"
            
            for i, chunk_id in enumerate(chunk_ids[:5], 1):
                if chunk_id in retriever.chunk_map:
                    chunk = retriever.chunk_map[chunk_id]
                    results_html += f"""
                    <div style="background-color: #f9f9f9; padding: 10px; margin: 10px 0; border-radius: 5px;">
                        <strong>Result {i}</strong><br>
                        <strong>Document:</strong> {chunk.get('doc_id', 'Unknown')}<br>
                        <strong>Section:</strong> {chunk.get('section_title', 'Unknown')}<br>
                        <strong>Year:</strong> {chunk.get('year', 'Unknown')}<br>
                        <div style="margin-top: 10px; padding: 10px; background-color: white; border-left: 3px solid #2196f3;">
                            {chunk['text'][:500]}...
                        </div>
                    </div>
                    """
            return results_html
        else:
            return f"No results found for CPT code {cpt_code}"
            
    except Exception as e:
        logger.error(f"CPT search error: {e}")
        return f"Error searching for CPT code: {str(e)}"

def get_system_stats(force_refresh: bool = False) -> str:
    """Get system statistics."""
    now = time.time()
    if not force_refresh and _STATS_CACHE["html"] and now - _STATS_CACHE["ts"] < _STATS_TTL_SEC:
        return _STATS_CACHE["html"]

    try:
        orch = get_orchestrator()
        chunks = orch.retriever.chunks
        
        # Calculate statistics
        stats = {
            "Total Chunks": len(chunks),
            "Unique Documents": len(set(c.get("doc_id", "") for c in chunks)),
            "Authority Tiers": {},
            "Evidence Levels": {},
            "Document Types": {}
        }
        
        for chunk in chunks:
            # Authority
            at = chunk.get("authority_tier", "Unknown")
            stats["Authority Tiers"][at] = stats["Authority Tiers"].get(at, 0) + 1
            
            # Evidence
            el = chunk.get("evidence_level", "Unknown")
            stats["Evidence Levels"][el] = stats["Evidence Levels"].get(el, 0) + 1
            
            # Type
            dt = chunk.get("doc_type", "Unknown")
            stats["Document Types"][dt] = stats["Document Types"].get(dt, 0) + 1
        
        # Format as HTML
        html = "<h3>System Statistics</h3>"
        html += f"<p><strong>Total Chunks:</strong> {stats['Total Chunks']:,}</p>"
        html += f"<p><strong>Unique Documents:</strong> {stats['Unique Documents']:,}</p>"
        
        html += "<h4>Authority Distribution</h4><ul>"
        for tier, count in sorted(stats["Authority Tiers"].items()):
            html += f"<li>{tier}: {count:,}</li>"
        html += "</ul>"
        
        html += "<h4>Evidence Level Distribution</h4><ul>"
        for level, count in sorted(stats["Evidence Levels"].items()):
            html += f"<li>{level}: {count:,}</li>"
        html += "</ul>"
        
        html += "<h4>Document Type Distribution</h4><ul>"
        for dtype, count in sorted(stats["Document Types"].items(), key=lambda x: x[1], reverse=True)[:10]:
            html += f"<li>{dtype}: {count:,}</li>"
        html += "</ul>"
        
        _STATS_CACHE["html"] = html
        _STATS_CACHE["ts"] = now
        return html
        
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return f"Error getting statistics: {str(e)}"

# Example queries for quick testing
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

# Authentication function
def authenticate(username, password):
    """Simple authentication check."""
    return username == AUTH_USERNAME and password == AUTH_PASSWORD

# Build Gradio interface optimized for HF Spaces
def create_interface():
    """Create the Gradio interface optimized for Hugging Face Spaces."""
    
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
        - 🔍 Hybrid search with MedCPT embeddings
        - 📊 Hierarchy-aware ranking (Authority & Evidence)
        - 🚨 Emergency detection and routing
        - ⚠️ Safety checks for critical information
        - 📚 Source citations with confidence scoring
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
                            choices=ALLOWED_MODELS,
                            value="gpt-5-mini",
                            label="Model",
                            info="Select the GPT-5 model"
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
            
            # V3 Procedural Coding Tab
            build_coding_tab()
        
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
    # Pre-warm orchestrator on startup
    print("🔥 Pre-warming orchestrator...")
    get_orchestrator()
    print("✅ Orchestrator ready")
    
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
