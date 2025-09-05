#!/usr/bin/env python3
"""
Gradio UI for IP Assist Lite
Interactive interface for medical information retrieval
"""

import sys
from pathlib import Path
from typing import List, Tuple, Dict, Any
import json
import logging

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import gradio as gr
from datetime import datetime

from orchestration.langgraph_agent import IPAssistOrchestrator
from retrieval.hybrid_retriever import HybridRetriever

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize orchestrator
orchestrator = None

def get_orchestrator():
    global orchestrator
    if orchestrator is None:
        logger.info("Initializing orchestrator...")
        orchestrator = IPAssistOrchestrator()
        logger.info("Orchestrator initialized")
    return orchestrator

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

def process_query(query: str, use_reranker: bool = True, top_k: int = 5) -> Tuple[str, str, str]:
    """Process a query and return formatted results."""
    if not query.strip():
        return "", "Please enter a query", ""
    
    try:
        orch = get_orchestrator()
        result = orch.process_query(query)
        
        # Format main response
        response_html = format_response_html(result)
        
        # Format metadata as JSON
        metadata = {
            "query_type": result["query_type"],
            "is_emergency": result["is_emergency"],
            "confidence_score": f"{result['confidence_score']:.2%}",
            "safety_flags": result["safety_flags"],
            "needs_review": result["needs_review"],
            "citations_count": len(result["citations"]),
            "timestamp": datetime.now().isoformat()
        }
        metadata_json = json.dumps(metadata, indent=2)
        
        # Status message
        if result["is_emergency"]:
            status = "🚨 Emergency query processed successfully"
        elif result["needs_review"]:
            status = "⚠️ Query processed - review recommended"
        else:
            status = "✅ Query processed successfully"
        
        return response_html, status, metadata_json
        
    except Exception as e:
        logger.error(f"Error processing query: {e}")
        error_msg = f"❌ Error: {str(e)}"
        return "", error_msg, ""

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

def get_system_stats() -> str:
    """Get system statistics."""
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

# Build Gradio interface
def build_interface():
    """Build the Gradio interface."""
    
    with gr.Blocks(title="IP Assist Lite", theme=gr.themes.Soft()) as demo:
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
                    inputs=[query_input, use_reranker, top_k],
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
                
                # Load stats on tab load
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
    demo = build_interface()
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,  # Set to True to create a public link
        show_error=True
    )