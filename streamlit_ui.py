#!/usr/bin/env python3
"""
Streamlit UI for IP Assist Lite
Alternative to Gradio when frontend templates are missing
"""

import sys
import os
from pathlib import Path
import json
import streamlit as st

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ui.gradio_app import get_orchestrator, process_query, search_cpt, get_system_stats

st.set_page_config(
    page_title="IP Assist Lite",
    page_icon="🏥",
    layout="wide"
)

st.title("🏥 IP Assist Lite")
st.markdown("### Medical Information Retrieval for Interventional Pulmonology")

# Initialize orchestrator
@st.cache_resource
def get_cached_orchestrator():
    return get_orchestrator()

# Sidebar controls
st.sidebar.title("Controls")
use_reranker = st.sidebar.checkbox("Use Reranker", value=True)
top_k = st.sidebar.slider("Number of Results", 1, 10, 5)

# Main interface
tab1, tab2, tab3 = st.tabs(["Query Assistant", "CPT Search", "Statistics"])

with tab1:
    st.header("Query Assistant")
    
    query = st.text_area(
        "Enter your medical query:",
        placeholder="e.g., What are the contraindications for bronchoscopy?",
        height=100
    )
    
    if st.button("🔍 Submit Query", type="primary"):
        if query.strip():
            with st.spinner("Processing query..."):
                try:
                    html, status, metadata = process_query(query, use_reranker, top_k)
                    
                    st.markdown("### Response")
                    st.markdown(html, unsafe_allow_html=True)
                    
                    st.markdown("### Status")
                    st.success(status)
                    
                    st.markdown("### Metadata")
                    st.json(json.loads(metadata))
                    
                except Exception as e:
                    st.error(f"Error processing query: {e}")
        else:
            st.warning("Please enter a query")

with tab2:
    st.header("CPT Code Search")
    
    cpt_code = st.text_input(
        "Enter CPT Code:",
        placeholder="e.g., 31622",
        max_chars=5
    )
    
    if st.button("Search CPT", type="primary"):
        if cpt_code.strip():
            with st.spinner("Searching CPT code..."):
                try:
                    result = search_cpt(cpt_code)
                    st.markdown("### CPT Results")
                    st.markdown(result, unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Error searching CPT: {e}")
        else:
            st.warning("Please enter a CPT code")

with tab3:
    st.header("System Statistics")
    
    if st.button("📊 Load Statistics", type="secondary"):
        with st.spinner("Loading statistics..."):
            try:
                stats = get_system_stats()
                st.markdown("### System Statistics")
                st.markdown(stats, unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Error loading statistics: {e}")

# Footer
st.markdown("---")
st.markdown("""
### ⚠️ Important Notice
This system is for informational purposes only. Always verify medical information with official guidelines 
and consult with qualified healthcare professionals before making clinical decisions.
""")
