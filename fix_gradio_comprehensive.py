#!/usr/bin/env python3
"""
Comprehensive Gradio Fix Solution
Addresses the jinja2.exceptions.TemplateNotFound: 'frontend/index.html' error
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def run_command(cmd, description):
    """Run a command and return success status."""
    print(f"🔄 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ {description} - Success")
            return True
        else:
            print(f"❌ {description} - Failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ {description} - Error: {e}")
        return False

def check_gradio_installation():
    """Check current Gradio installation."""
    print("🔍 Checking Gradio installation...")
    
    try:
        import gradio as gr
        print(f"✅ Gradio version: {gr.__version__}")
        
        # Check if frontend files exist
        gradio_path = Path(gr.__file__).parent
        frontend_path = gradio_path / "frontend"
        
        if frontend_path.exists():
            print(f"✅ Frontend directory exists: {frontend_path}")
            index_file = frontend_path / "index.html"
            if index_file.exists():
                print(f"✅ index.html exists: {index_file}")
                return True
            else:
                print(f"❌ index.html missing: {index_file}")
                return False
        else:
            print(f"❌ Frontend directory missing: {frontend_path}")
            return False
            
    except ImportError:
        print("❌ Gradio not installed")
        return False

def fix_gradio_installation():
    """Fix Gradio installation using multiple methods."""
    print("\n🔧 Attempting to fix Gradio installation...")
    
    # Method 1: Reinstall Gradio
    print("\n📦 Method 1: Reinstalling Gradio...")
    if run_command("pip uninstall gradio -y", "Uninstalling Gradio"):
        if run_command("pip install gradio==4.44.0", "Installing stable Gradio version"):
            if check_gradio_installation():
                return True
    
    # Method 2: Install with --force-reinstall
    print("\n📦 Method 2: Force reinstall...")
    if run_command("pip install --force-reinstall --no-cache-dir gradio", "Force reinstalling Gradio"):
        if check_gradio_installation():
            return True
    
    # Method 3: Install from source
    print("\n📦 Method 3: Installing from GitHub source...")
    if run_command("pip install git+https://github.com/gradio-app/gradio.git", "Installing from GitHub"):
        if check_gradio_installation():
            return True
    
    # Method 4: Downgrade to known working version
    print("\n📦 Method 4: Downgrading to Gradio 4.20.0...")
    if run_command("pip install gradio==4.20.0", "Installing Gradio 4.20.0"):
        if check_gradio_installation():
            return True
    
    return False

def create_alternative_ui():
    """Create alternative UI solutions."""
    print("\n🎨 Creating alternative UI solutions...")
    
    # Solution 1: FastAPI-only interface
    fastapi_ui = '''#!/usr/bin/env python3
"""
FastAPI-only UI for IP Assist Lite
Alternative to Gradio when frontend templates are missing
"""

import sys
import os
from pathlib import Path
from typing import Dict, Any
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

from ui.gradio_app import get_orchestrator, process_query, search_cpt, get_system_stats

app = FastAPI(title="IP Assist Lite", description="Medical Information Retrieval")

# Simple HTML template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>IP Assist Lite</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .header { text-align: center; margin-bottom: 30px; }
        .query-section { margin-bottom: 30px; }
        textarea { width: 100%; height: 100px; padding: 10px; border: 1px solid #ddd; border-radius: 5px; }
        button { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; margin: 5px; }
        button:hover { background: #0056b3; }
        .results { margin-top: 20px; padding: 20px; background: #f8f9fa; border-radius: 5px; }
        .error { color: red; }
        .success { color: green; }
        .tabs { display: flex; margin-bottom: 20px; }
        .tab { padding: 10px 20px; background: #e9ecef; margin-right: 5px; cursor: pointer; border-radius: 5px 5px 0 0; }
        .tab.active { background: white; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏥 IP Assist Lite</h1>
            <p>Medical Information Retrieval for Interventional Pulmonology</p>
        </div>
        
        <div class="tabs">
            <div class="tab active" onclick="showTab('query')">Query Assistant</div>
            <div class="tab" onclick="showTab('cpt')">CPT Search</div>
            <div class="tab" onclick="showTab('stats')">Statistics</div>
        </div>
        
        <div id="query" class="tab-content active">
            <div class="query-section">
                <h3>Enter your medical query:</h3>
                <form id="queryForm">
                    <textarea id="queryInput" placeholder="e.g., What are the contraindications for bronchoscopy?"></textarea><br>
                    <label><input type="checkbox" id="useReranker" checked> Use Reranker</label><br>
                    <label>Results: <input type="number" id="topK" value="5" min="1" max="10"></label><br>
                    <button type="submit">🔍 Submit Query</button>
                </form>
            </div>
            <div id="queryResults" class="results" style="display: none;"></div>
        </div>
        
        <div id="cpt" class="tab-content">
            <div class="query-section">
                <h3>Search CPT Code:</h3>
                <form id="cptForm">
                    <input type="text" id="cptInput" placeholder="e.g., 31622" maxlength="5"><br>
                    <button type="submit">Search CPT</button>
                </form>
            </div>
            <div id="cptResults" class="results" style="display: none;"></div>
        </div>
        
        <div id="stats" class="tab-content">
            <div class="query-section">
                <button onclick="loadStats()">📊 Load Statistics</button>
            </div>
            <div id="statsResults" class="results" style="display: none;"></div>
        </div>
    </div>
    
    <script>
        function showTab(tabName) {
            // Hide all tabs
            document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
            
            // Show selected tab
            document.getElementById(tabName).classList.add('active');
            event.target.classList.add('active');
        }
        
        document.getElementById('queryForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const query = document.getElementById('queryInput').value;
            const useReranker = document.getElementById('useReranker').checked;
            const topK = document.getElementById('topK').value;
            
            if (!query.trim()) return;
            
            const resultsDiv = document.getElementById('queryResults');
            resultsDiv.style.display = 'block';
            resultsDiv.innerHTML = '<p>Processing query...</p>';
            
            try {
                const response = await fetch('/query', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                    body: new URLSearchParams({
                        query: query,
                        use_reranker: useReranker,
                        top_k: topK
                    })
                });
                
                const data = await response.json();
                resultsDiv.innerHTML = `
                    <h4>Response:</h4>
                    <div>${data.html}</div>
                    <h4>Status:</h4>
                    <p class="success">${data.status}</p>
                    <h4>Metadata:</h4>
                    <pre>${JSON.stringify(data.metadata, null, 2)}</pre>
                `;
            } catch (error) {
                resultsDiv.innerHTML = `<p class="error">Error: ${error.message}</p>`;
            }
        });
        
        document.getElementById('cptForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const cpt = document.getElementById('cptInput').value;
            
            if (!cpt.trim()) return;
            
            const resultsDiv = document.getElementById('cptResults');
            resultsDiv.style.display = 'block';
            resultsDiv.innerHTML = '<p>Searching CPT code...</p>';
            
            try {
                const response = await fetch('/cpt', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                    body: new URLSearchParams({cpt_code: cpt})
                });
                
                const data = await response.json();
                resultsDiv.innerHTML = `
                    <h4>CPT Results:</h4>
                    <div>${data.result}</div>
                `;
            } catch (error) {
                resultsDiv.innerHTML = `<p class="error">Error: ${error.message}</p>`;
            }
        });
        
        async function loadStats() {
            const resultsDiv = document.getElementById('statsResults');
            resultsDiv.style.display = 'block';
            resultsDiv.innerHTML = '<p>Loading statistics...</p>';
            
            try {
                const response = await fetch('/stats');
                const data = await response.json();
                resultsDiv.innerHTML = `
                    <h4>System Statistics:</h4>
                    <div>${data.stats}</div>
                `;
            } catch (error) {
                resultsDiv.innerHTML = `<p class="error">Error: ${error.message}</p>`;
            }
        }
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def root():
    return HTML_TEMPLATE

@app.post("/query")
async def query_endpoint(
    query: str = Form(...),
    use_reranker: bool = Form(False),
    top_k: int = Form(5)
):
    try:
        html, status, metadata = process_query(query, use_reranker, top_k)
        return JSONResponse({
            "html": html,
            "status": status,
            "metadata": json.loads(metadata)
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/cpt")
async def cpt_endpoint(cpt_code: str = Form(...)):
    try:
        result = search_cpt(cpt_code)
        return JSONResponse({"result": result})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/stats")
async def stats_endpoint():
    try:
        stats = get_system_stats()
        return JSONResponse({"stats": stats})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

if __name__ == "__main__":
    print("🚀 Starting FastAPI alternative UI...")
    print("📱 Access at: http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
'''
    
    with open("fastapi_ui.py", "w") as f:
        f.write(fastapi_ui)
    
    print("✅ Created FastAPI alternative UI: fastapi_ui.py")
    
    # Solution 2: Streamlit interface
    streamlit_ui = '''#!/usr/bin/env python3
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

from ui.gradio_app import get_orchestrator, process_query, search_cpt, get_system_stats

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
'''
    
    with open("streamlit_ui.py", "w") as f:
        f.write(streamlit_ui)
    
    print("✅ Created Streamlit alternative UI: streamlit_ui.py")
    
    # Solution 3: Simple CLI interface
    cli_ui = '''#!/usr/bin/env python3
"""
Simple CLI interface for IP Assist Lite
Use this when web UIs fail
"""

import sys
import os
from pathlib import Path
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ui.gradio_app import get_orchestrator, process_query, search_cpt, get_system_stats

def main():
    print("🏥 IP Assist Lite - CLI Interface")
    print("=" * 50)
    
    # Initialize orchestrator
    print("🔄 Initializing orchestrator...")
    try:
        orch = get_orchestrator()
        print("✅ Orchestrator ready")
    except Exception as e:
        print(f"❌ Failed to initialize orchestrator: {e}")
        return
    
    while True:
        print("\\nOptions:")
        print("1. Query Assistant")
        print("2. CPT Code Search")
        print("3. System Statistics")
        print("4. Exit")
        
        choice = input("\\nEnter your choice (1-4): ").strip()
        
        if choice == "1":
            query = input("\\nEnter your medical query: ").strip()
            if query:
                print("\\n🔄 Processing query...")
                try:
                    html, status, metadata = process_query(query, True, 5)
                    print(f"\\n✅ Status: {status}")
                    print(f"\\n📄 Response:")
                    print("-" * 50)
                    # Simple text extraction from HTML
                    import re
                    text_response = re.sub(r'<[^>]+>', '', html)
                    print(text_response)
                    print("-" * 50)
                except Exception as e:
                    print(f"❌ Error: {e}")
        
        elif choice == "2":
            cpt = input("\\nEnter CPT code: ").strip()
            if cpt:
                print("\\n🔄 Searching CPT code...")
                try:
                    result = search_cpt(cpt)
                    print(f"\\n📄 CPT Results:")
                    print("-" * 50)
                    import re
                    text_result = re.sub(r'<[^>]+>', '', result)
                    print(text_result)
                    print("-" * 50)
                except Exception as e:
                    print(f"❌ Error: {e}")
        
        elif choice == "3":
            print("\\n🔄 Loading statistics...")
            try:
                stats = get_system_stats()
                print(f"\\n📊 System Statistics:")
                print("-" * 50)
                import re
                text_stats = re.sub(r'<[^>]+>', '', stats)
                print(text_stats)
                print("-" * 50)
            except Exception as e:
                print(f"❌ Error: {e}")
        
        elif choice == "4":
            print("\\n👋 Goodbye!")
            break
        
        else:
            print("\\n❌ Invalid choice. Please enter 1-4.")

if __name__ == "__main__":
    main()
'''
    
    with open("cli_ui.py", "w") as f:
        f.write(cli_ui)
    
    print("✅ Created CLI alternative UI: cli_ui.py")

def main():
    """Main function to run the comprehensive fix."""
    print("🔧 Comprehensive Gradio Fix Solution")
    print("=" * 50)
    
    # Check current installation
    if check_gradio_installation():
        print("\\n✅ Gradio installation appears to be working correctly!")
        return True
    
    # Try to fix the installation
    if fix_gradio_installation():
        print("\\n✅ Gradio installation fixed successfully!")
        return True
    
    # Create alternative UIs
    create_alternative_ui()
    
    print("\\n🎯 Solutions Available:")
    print("1. Try running: python src/ui/gradio_app.py")
    print("2. Use FastAPI UI: python fastapi_ui.py")
    print("3. Use Streamlit UI: streamlit run streamlit_ui.py")
    print("4. Use CLI UI: python cli_ui.py")
    
    return False

if __name__ == "__main__":
    main()
