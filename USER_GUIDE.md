# IP Assist Lite - User Guide

## 📚 Table of Contents
1. [System Overview](#system-overview)
2. [Installation](#installation)
3. [Starting the System](#starting-the-system)
4. [Using the Web Interface](#using-the-web-interface)
5. [Using the API](#using-the-api)
6. [Understanding Results](#understanding-results)
7. [Safety Features](#safety-features)
8. [Troubleshooting](#troubleshooting)

## System Overview

IP Assist Lite is a medical information retrieval system designed for Interventional Pulmonology professionals. It provides:

- **Intelligent Search**: Combines semantic understanding, keyword matching, and exact CPT code lookup
- **Medical Authority Ranking**: Prioritizes information from authoritative sources (PAPOIP 2025, etc.)
- **Emergency Detection**: Automatically identifies and prioritizes emergency queries
- **Safety Guards**: Flags pediatric, dosage, and contraindication information
- **Source Citations**: Every response includes verifiable sources with confidence scores

## Installation

### Prerequisites
- Python 3.9+ with conda/miniconda
- Docker Desktop (for Qdrant database)
- NVIDIA GPU with 8GB+ VRAM (optional but recommended)
- 50GB free disk space

### Step 1: Clone and Setup Environment
```bash
# Clone the repository
git clone <repository-url>
cd IP_assist_lite

# Create conda environment
conda create -n ipass2 python=3.11
conda activate ipass2

# Install dependencies
pip install torch transformers sentence-transformers
pip install qdrant-client rank-bm25 tiktoken
pip install langgraph langchain-core
pip install fastapi uvicorn gradio python-multipart
```

### Step 2: Setup Qdrant Database
```bash
# Start Qdrant container
docker run -d -p 6333:6333 -p 6334:6334 \
  -v ./qdrant_storage:/qdrant/storage:z \
  --name ip-assistant-qdrant \
  qdrant/qdrant:v1.7.4

# Verify it's running
curl http://localhost:6333/health
```

### Step 3: Process Data (First Time Only)
```bash
# This will take 30-60 minutes total
make all

# Or step by step:
make prep    # Process documents (10 min)
make chunk   # Create chunks (5 min)
make embed   # Generate embeddings (20-30 min with GPU)
make index   # Build Qdrant index (2 min)
```

## Starting the System

### Quick Start
```bash
# Make sure Qdrant is running
docker start ip-assistant-qdrant

# Launch all services
./launch.sh

# System will be available at:
# - Web UI: http://localhost:7860
# - API Docs: http://localhost:8000/docs
```

### Manual Start
```bash
# Terminal 1: Start FastAPI
cd src/api
python fastapi_app.py

# Terminal 2: Start Gradio UI
cd src/ui
python gradio_app.py
```

## Using the Web Interface

### Access the UI
Open your browser and navigate to: **http://localhost:7860**

### Query Assistant Tab

#### Entering Queries
1. Type your medical question in the text box
2. Use natural language - the system understands medical terminology
3. Click "Submit Query" or press Enter

#### Example Queries
- "What are the contraindications for bronchoscopy?"
- "Massive hemoptysis management protocol"
- "CPT code for EBUS-TBNA with needle aspiration"
- "Pediatric bronchoscopy dosing for lidocaine"
- "How to place fiducial markers for SBRT?"

#### Understanding the Response
- **Emergency Banner** (Red): Appears for urgent medical situations
- **Query Type**: Shows how the system classified your query
- **Confidence Score**: Higher scores indicate more reliable results
- **Safety Warnings** (Orange): Important safety considerations
- **Main Response**: Synthesized information from multiple sources
- **Sources**: Clickable citations with authority/evidence levels

### CPT Code Search Tab
1. Enter a 5-digit CPT code (e.g., 31622)
2. Click "Search CPT"
3. View all documents containing that code
4. See relevant context and year of publication

### System Statistics Tab
- View total chunks and documents indexed
- See distribution by authority tier (A1-A4)
- Check evidence level distribution (H1-H4)
- Monitor document types in the system

## Using the API

### API Documentation
Interactive documentation available at: **http://localhost:8000/docs**

### Main Endpoints

#### 1. Process Query (Recommended)
```python
import requests

response = requests.post(
    "http://localhost:8000/query",
    json={
        "query": "What are contraindications for bronchoscopy?",
        "top_k": 5,
        "use_reranker": True
    }
)

result = response.json()
print(result["response"])
print(f"Confidence: {result['confidence_score']}")
print(f"Emergency: {result['is_emergency']}")
```

#### 2. Direct Search
```python
# Search with specific method
response = requests.post(
    "http://localhost:8000/search",
    json={
        "query": "fiducial markers",
        "search_type": "hybrid",  # or "semantic", "bm25", "exact"
        "top_k": 10,
        "authority_filter": "A1"  # Optional: A1, A2, A3, A4
    }
)
```

#### 3. CPT Code Lookup
```python
response = requests.get("http://localhost:8000/cpt/31622")
cpt_info = response.json()
```

#### 4. Emergency Check
```python
response = requests.post(
    "http://localhost:8000/emergency",
    json="massive hemoptysis with respiratory failure"
)
is_emergency = response.json()["is_emergency"]
```

#### 5. System Health
```python
response = requests.get("http://localhost:8000/health")
health = response.json()
print(f"Status: {health['status']}")
print(f"Qdrant: {health['qdrant_connected']}")
```

## Understanding Results

### Authority Tiers
- **A1**: PAPOIP 2025 (Highest authority - comprehensive textbook)
- **A2**: Practical Guide 2022 (High authority - practical handbook)
- **A3**: BACADA 2012 (Medium authority - older textbook)
- **A4**: Journal Articles (Variable authority - recent research)

### Evidence Levels
- **H1**: Guidelines, Systematic Reviews (Strongest evidence)
- **H2**: RCTs, Prospective Cohorts (Strong evidence)
- **H3**: Narrative Reviews, Book Chapters (Moderate evidence)
- **H4**: Case Series, Case Reports (Limited evidence)

### Confidence Scoring
- **90-100%**: Very high confidence, multiple authoritative sources agree
- **70-89%**: High confidence, good source alignment
- **50-69%**: Moderate confidence, some uncertainty
- **Below 50%**: Low confidence, limited or conflicting information

### Query Types
- **Emergency**: Urgent medical situations requiring immediate action
- **Clinical**: General medical information queries
- **Procedure**: How-to queries about techniques
- **Coding**: CPT codes and billing information
- **Safety**: Contraindications and safety concerns

## Safety Features

### Automatic Detection
The system automatically detects and flags:
- **Emergency Situations**: Massive hemoptysis, foreign body aspiration, tension pneumothorax
- **Pediatric Queries**: Age-specific dosing and techniques
- **Contraindications**: Absolute and relative contraindications
- **Dosage Information**: Medication doses requiring verification

### Safety Warnings
When safety concerns are detected:
1. Orange warning banners appear
2. Specific safety notes are added to responses
3. System may flag response for review
4. Sources are prioritized from highest authority

### Best Practices
- **Always verify critical information** with official guidelines
- **Check publication years** for time-sensitive information (especially coding)
- **Review multiple sources** for controversial topics
- **Consult specialists** for complex cases
- **Document source citations** when using information clinically

## Troubleshooting

### Common Issues and Solutions

#### 1. System Won't Start
```bash
# Check if Qdrant is running
docker ps | grep qdrant
docker start ip-assistant-qdrant

# Check if ports are available
lsof -i :7860  # Gradio
lsof -i :8000  # FastAPI
lsof -i :6333  # Qdrant
```

#### 2. Import Errors
```bash
# Ensure you're in the right environment
conda activate ipass2

# Reinstall dependencies
pip install -r requirements.txt
```

#### 3. Slow Performance
- Enable GPU if available
- Reduce batch size in settings
- Ensure reranking is enabled
- Check system resources (RAM, CPU)

#### 4. No Results Found
- Try rephrasing the query
- Use medical terminology
- Check if data is properly indexed:
  ```bash
  make stats
  ```

#### 5. GPU Memory Errors
Edit `src/index/embed_medcpt.py`:
```python
# Reduce batch size
batch_size = 128  # Instead of 256
```

### Getting Help

#### Check System Status
```bash
# View statistics
make stats

# Check logs
docker logs ip-assistant-qdrant

# Test individual components
python src/retrieval/hybrid_retriever.py
python src/orchestration/langgraph_agent.py
```

#### Error Messages
- **"Qdrant not connected"**: Start Docker and Qdrant container
- **"No chunks found"**: Run `make chunk` to generate chunks
- **"Embeddings not found"**: Run `make embed` to generate embeddings
- **"CUDA out of memory"**: Reduce batch size or use CPU

## Advanced Usage

### Custom Filters
```python
# Filter by authority and year
response = requests.post(
    "http://localhost:8000/search",
    json={
        "query": "bronchoscopy complications",
        "filters": {
            "authority_tier": "A1",
            "year": {"$gte": 2020},
            "has_table": True
        }
    }
)
```

### Batch Processing
```python
queries = [
    "CPT 31622",
    "CPT 31628",
    "CPT 31633"
]

results = []
for query in queries:
    response = requests.post(
        "http://localhost:8000/query",
        json={"query": query}
    )
    results.append(response.json())
```

### Export Results
```python
import json
import pandas as pd

# Get results
response = requests.get("http://localhost:8000/statistics")
stats = response.json()

# Export to CSV
df = pd.DataFrame(stats["authority_distribution"].items(), 
                  columns=["Authority", "Count"])
df.to_csv("statistics.csv", index=False)
```

## Tips for Best Results

### Query Formulation
- **Be specific**: "EBUS-TBNA complications" vs "complications"
- **Use medical terms**: "hemoptysis" vs "coughing blood"
- **Include context**: "pediatric bronchoscopy" vs "bronchoscopy"
- **Specify procedures**: "rigid bronchoscopy" vs "bronchoscopy"

### Understanding Limitations
- System returns retrieved chunks, not generated text (pending LLM integration)
- Recency matters: Coding information older than 3 years may be outdated
- Always verify emergency protocols with current institutional guidelines
- Cross-check pediatric dosing with weight-based calculations

### Optimizing Performance
- Use reranking for better accuracy (slight speed trade-off)
- Filter by authority tier when you know the source type
- Use exact match for CPT codes
- Enable GPU acceleration if available

## Maintenance

### Regular Updates
```bash
# Update embeddings after adding new documents
make embed
make index

# Check system health
make stats

# Clean temporary files
make clean
```

### Backup Data
```bash
# Backup processed data
tar -czf backup.tar.gz data/processed data/chunks data/vectors

# Backup Qdrant
docker exec ip-assistant-qdrant qdrant-backup /qdrant/storage /backup
```

---

## Quick Reference Card

### Essential Commands
```bash
./launch.sh              # Start everything
make stats               # View statistics
docker logs ip-assistant-qdrant  # Check database logs
```

### Key URLs
- Web Interface: http://localhost:7860
- API Docs: http://localhost:8000/docs
- API Health: http://localhost:8000/health
- Qdrant UI: http://localhost:6333/dashboard

### Emergency Queries Format
- "Massive hemoptysis [management/protocol/algorithm]"
- "Foreign body [removal/extraction] bronchoscopy"
- "Tension pneumothorax [management/treatment]"
- "Airway obstruction [emergency/urgent]"

### Support
For issues or questions:
1. Check the troubleshooting section
2. Review PROJECT_STATUS.md for technical details
3. Consult CLAUDE.md for project philosophy

---

**Remember**: This system is for informational purposes only. Always verify medical information with official guidelines and consult qualified healthcare professionals before making clinical decisions.