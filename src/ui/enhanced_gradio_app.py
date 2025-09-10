#!/usr/bin/env python3
"""
Enhanced Gradio interface for IP Assist with conversation support.
Features:
- Follow-up questions with conversation context
- AMA format citations with inline (Author, Year)
- Concealed hierarchy (only shows articles in references)
"""

import gradio as gr
import json
import time
import hashlib
import uuid
import re
from typing import Dict, Any, Tuple, List, Optional
from pathlib import Path
import sys
import os
import logging

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.retrieval.hybrid_retriever import HybridRetriever
from src.llm.gpt5_medical import GPT5Medical
from src.orchestrator.enhanced_orchestrator import EnhancedOrchestrator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Color scheme
INFO_COLOR = "#2196F3"
SUCCESS_COLOR = "#4CAF50"
WARNING_COLOR = "#FF9800"
EMERGENCY_COLOR = "#F44336"

# Global orchestrator instance
_orchestrator = None
_session_states = {}  # Store session states

def get_orchestrator() -> EnhancedOrchestrator:
    """Get or create the orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        logger.info("Initializing enhanced orchestrator...")
        
        # Initialize retriever
        retriever = HybridRetriever(
            chunks_file="data/chunks/chunks.jsonl",
            qdrant_host=os.getenv("QDRANT_HOST", "localhost"),
            qdrant_port=int(os.getenv("QDRANT_PORT", "6333")),
            collection_name="ip_medcpt"
        )
        
        # Initialize LLM client
        llm_client = GPT5Medical(
            model=os.getenv("IP_GPT5_MODEL", "gpt-4o-mini")
        )
        
        _orchestrator = EnhancedOrchestrator(retriever, llm_client)
        logger.info("Enhanced orchestrator initialized")
    
    return _orchestrator

def format_response_html(result: Dict[str, Any], include_query: bool = False) -> str:
    """Format the response with enhanced AMA citations."""
    html_parts = []
    
    # Include the query if requested
    if include_query and result.get('query'):
        html_parts.append(f"""
        <div style="background-color: #f0f0f0; padding: 12px; border-radius: 8px; margin-bottom: 10px;">
            <strong>Q:</strong> {result.get('query')}
        </div>
        """)
    
    # Query type and confidence
    html_parts.append(f"""
    <div style="background-color: #f5f5f5; padding: 10px; border-radius: 5px; margin-bottom: 10px;">
        <strong>Query Type:</strong> {result.get('query_type', 'clinical').replace('_', ' ').title()}<br>
        <strong>Confidence:</strong> {result.get('confidence_score', 0.85):.1%}<br>
        <strong>Model:</strong> {result.get('model_used', 'GPT-4')}
    </div>
    """)
    
    # Safety flags if present
    if result.get("safety_flags"):
        flags_html = ", ".join([f"<span style='color: {WARNING_COLOR};'>⚠️ {flag}</span>" 
                               for flag in result["safety_flags"]])
        html_parts.append(f"""
        <div style="margin-bottom: 10px;">
            <strong>Clinical Considerations:</strong> {flags_html}
        </div>
        """)
    
    # Main response with inline citations preserved and markdown formatting
    response_text = result.get("response", "")
    
    # Convert markdown formatting to HTML
    # Bold headers
    response_text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', response_text)
    # Bullet points
    response_text = re.sub(r'^• ', '• ', response_text, flags=re.MULTILINE)
    # Preserve paragraph breaks
    response_text = response_text.replace('\n\n', '</p><p>')
    response_text = response_text.replace('\n', '<br>')
    
    html_parts.append(f"""
    <div style="background-color: white; padding: 15px; border-left: 4px solid {SUCCESS_COLOR}; margin-bottom: 15px; line-height: 1.6;">
        <p>{response_text}</p>
    </div>
    """)
    
    # References in AMA format (only articles shown)
    if result.get("citations"):
        html_parts.append("<div style='margin-top: 20px;'>")
        html_parts.append("<h3 style='color: #333; border-bottom: 2px solid #333; padding-bottom: 5px;'>References</h3>")
        html_parts.append("<ol style='padding-left: 20px;'>")
        
        # Use the ama_format field if available, otherwise construct it
        for i, cite in enumerate(result["citations"], 1):
            if 'ama_format' in cite:
                citation_text = cite['ama_format']
            else:
                # Fallback formatting
                author = cite.get('author', 'Unknown')
                year = cite.get('year', '')
                title = cite.get('title', cite.get('doc_id', 'Study'))
                
                # Clean up author
                if author and 'et al' not in author:
                    author = f"{author} et al"
                
                citation_text = f"{author}. {title}. {year}."
            
            html_parts.append(f"""
            <li style='margin-bottom: 8px; color: #333;'>
                {citation_text}
            </li>
            """)
        
        html_parts.append("</ol>")
        html_parts.append("</div>")
    
    # Footer
    html_parts.append(f"""
    <div style="margin-top: 20px; padding-top: 10px; border-top: 1px solid #ddd; font-size: 0.9em; color: #666;">
        Created by Russell Miller, MD | IP Assist Lite
    </div>
    """)
    
    return "".join(html_parts)

def process_query(query: str, 
                 session_state: Optional[str] = None,
                 conversation_history: Optional[str] = None,
                 model: str = "gpt-5-mini") -> Tuple[str, str, str, str]:
    """Process a query with conversation support."""
    
    if not query or not query.strip():
        return "", "Please enter a query", ""
    
    # Generate or use session ID
    if not session_state:
        session_state = str(uuid.uuid4())
    
    try:
        orchestrator = get_orchestrator()
        
        # Set the model
        orchestrator.llm.model = model
        
        # Process query with session context
        result = orchestrator.process_query(
            query=query.strip(),
            session_id=session_state,
            use_reranker=True,
            top_k=10
        )
        
        # Format response with query included
        html_response = format_response_html(result, include_query=True)
        
        # Store session state
        global _session_states
        _session_states[session_state] = {
            'last_query': query,
            'last_response': result.get('response', ''),
            'timestamp': time.time()
        }
        
        # Build conversation history
        if conversation_history:
            full_conversation = conversation_history + "\n" + html_response
        else:
            full_conversation = html_response
        
        # Return conversation history, empty input, empty status, and session state
        return full_conversation, "", "", session_state
        
    except Exception as e:
        logger.error(f"Error processing query: {e}", exc_info=True)
        error_html = f"""
        <div style="background-color: {EMERGENCY_COLOR}; color: white; padding: 10px; border-radius: 5px;">
            ❌ Error: {str(e)}
        </div>
        """
        # Return error, clear input, status message, session state
        return error_html, "", "Error occurred", session_state

def clear_conversation():
    """Clear the conversation history."""
    session_id = str(uuid.uuid4())
    # Return empty query, empty response, new session, and status
    return "", "", session_id, "Conversation cleared. Starting new session."

def create_interface():
    """Create the enhanced Gradio interface."""
    
    with gr.Blocks(title="IP Assist Lite - Enhanced", theme=gr.themes.Base()) as app:
        # Session state
        session_state = gr.State(str(uuid.uuid4()))
        conversation_state = gr.State("")
        
        gr.Markdown("""
        # 🏥 IP Assist Lite - Enhanced Edition
        ### Evidence-Based Interventional Pulmonology Assistant
        *Created by Russell Miller, MD*
        
        **Features:**
        - 💬 Follow-up questions with conversation context
        - 📚 AMA format citations with inline references
        - 🔍 Intelligent article augmentation
        - ⚡ Hierarchical evidence synthesis
        """)
        
        with gr.Row():
            with gr.Column(scale=3):
                query_input = gr.Textbox(
                    label="Enter your question",
                    placeholder="e.g., What are the indications for transbronchial ablation?",
                    lines=3
                )
                
                with gr.Row():
                    submit_btn = gr.Button("🔍 Submit Query", variant="primary")
                    clear_btn = gr.Button("🔄 New Conversation", variant="secondary")
                
                model_dropdown = gr.Dropdown(
                    choices=["gpt-5-mini", "gpt-5", "gpt-4o-mini", "gpt-4o"],
                    value="gpt-5-mini",
                    label="Model Selection"
                )
                
                status_output = gr.Textbox(
                    label="Status",
                    interactive=False,
                    visible=False
                )
        
        with gr.Column(scale=7):
            response_output = gr.HTML(
                label="Response",
                value="""
                <div style='padding: 20px; background: #f9f9f9; border-radius: 10px;'>
                    <h3>Welcome to IP Assist Lite Enhanced</h3>
                    <p>Ask any question about interventional pulmonology procedures, techniques, or guidelines.</p>
                    <p><strong>New features:</strong></p>
                    <ul>
                        <li>Ask follow-up questions to dive deeper</li>
                        <li>Professional AMA format citations</li>
                        <li>Evidence-based answers from authoritative sources</li>
                    </ul>
                </div>
                """
            )
        
        # Examples section
        with gr.Row():
            gr.Examples(
                examples=[
                    ["What are the indications for transbronchial ablation?"],
                    ["Can you explain more about the contraindications?"],  # Follow-up
                    ["What are the CPT codes for EBUS-TBNA?"],
                    ["How do you manage massive hemoptysis?"],
                    ["What is the training requirement for bronchoscopic lung volume reduction?"],
                    ["What are the energy settings for microwave ablation?"]  # Follow-up
                ],
                inputs=query_input,
                label="Example Questions (including follow-ups)"
            )
        
        # Event handlers
        submit_btn.click(
            fn=process_query,
            inputs=[query_input, session_state, conversation_state, model_dropdown],
            outputs=[response_output, query_input, status_output, session_state]
        ).then(
            lambda x: x,  # Update conversation state with new response
            inputs=[response_output],
            outputs=[conversation_state]
        )
        
        clear_btn.click(
            fn=clear_conversation,
            inputs=[],
            outputs=[query_input, response_output, session_state, status_output]
        ).then(
            lambda: "",  # Clear conversation state
            inputs=[],
            outputs=[conversation_state]
        )
        
        query_input.submit(
            fn=process_query,
            inputs=[query_input, session_state, conversation_state, model_dropdown],
            outputs=[response_output, query_input, status_output, session_state]
        ).then(
            lambda x: x,  # Update conversation state with new response
            inputs=[response_output],
            outputs=[conversation_state]
        )
    
    return app

if __name__ == "__main__":
    app = create_interface()
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True
    )