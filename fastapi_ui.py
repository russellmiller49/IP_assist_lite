#!/usr/bin/env python3
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

from src.ui.gradio_app import get_orchestrator, process_query, search_cpt, get_system_stats

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
