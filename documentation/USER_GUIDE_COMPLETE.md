# IP Assist Lite - Complete Setup & Usage Guide

## ⚡ QUICK START (If Already Set Up)

```bash
# 1. Activate conda environment (ALWAYS DO THIS FIRST!)
conda activate ipass2

# 2. Start Qdrant database
make docker-up

# 3. Choose your interface:
make ui                    # Web interface (recommended)
# OR
python cli_interface.py    # Command-line interface
```

**Web UI**: Open http://localhost:7860 in your browser

---

## 🚨 COMPLETE SETUP FROM SCRATCH

### Prerequisites Checklist

- [ ] **Conda/Miniconda installed** ([Download here](https://docs.conda.io/en/latest/miniconda.html))
- [ ] **Docker installed** ([Download here](https://www.docker.com/products/docker-desktop))
- [ ] **Python 3.11**
- [ ] **16GB+ RAM**
- [ ] **10GB+ free disk space**
- [ ] **GPU (optional)**: NVIDIA with CUDA support for faster embedding generation
- [ ] **OpenAI API Key** (for GPT integration)

---

## 📦 STEP 1: Environment Setup

### 1.1 Clone Repository
```bash
cd ~/projects
git clone <repository-url> IP_assist_lite
cd IP_assist_lite
```

### 1.2 Create Conda Environment
```bash
# Create environment with Python 3.11
conda create -n ipass2 python=3.11 -y

# IMPORTANT: Always activate this environment!
conda activate ipass2
```

### 1.3 Install All Dependencies
```bash
# Install core dependencies
pip install -r requirements.txt

# If requirements.txt doesn't exist, install manually:
pip install torch torchvision transformers
pip install sentence-transformers qdrant-client
pip install openai tiktoken
pip install langgraph langchain-core
pip install fastapi uvicorn gradio
pip install rank-bm25 spacy nltk blingfire
pip install pandas numpy scikit-learn
pip install rich python-dotenv pyyaml

# Download spaCy model for sentence segmentation
python -m spacy download en_core_web_sm
```

### 1.4 Verify Installation
```bash
# Check Python packages
python -c "import torch, transformers, qdrant_client, openai, gradio; print('✅ All packages installed')"

# Check GPU (optional)
python -c "import torch; print(f'GPU Available: {torch.cuda.is_available()}')"
```

---

## 🔑 STEP 2: Configure API Keys

### 2.1 Edit Environment File
```bash
# Open .env file
nano .env
# OR
vim .env
```

### 2.2 Add Your Keys
```env
# OpenAI Configuration (REQUIRED - add your actual key)
OPENAI_API_KEY=sk-proj-YOUR-ACTUAL-API-KEY-HERE

# Model Configuration
IP_GPT5_MODEL=gpt-4         # Use gpt-4 or gpt-3.5-turbo for now
USE_RESPONSES_API=0          # Set to 0 for Chat Completions API
REASONING_EFFORT=medium      # low, medium, or high

# System Settings (keep defaults)
RETRIEVE_M=30
RERANK_N=10
RESULT_TTL_SEC=600
RESULT_CACHE_MAX=256
```

### 2.3 Test API Key
```bash
python -c "
import os
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()
client = OpenAI()
print('✅ OpenAI API key is valid')
"
```

---

## 🐳 STEP 3: Start Qdrant Database

### 3.1 Create Docker Directory
```bash
mkdir -p docker/qdrant_storage
```

### 3.2 Create Docker Compose File
```bash
cat > docker/docker-compose.yml << 'EOF'
version: '3.8'
services:
  qdrant:
    image: qdrant/qdrant:v1.7.4
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - ./qdrant_storage:/qdrant/storage:z
    restart: unless-stopped
EOF
```

### 3.3 Start Qdrant
```bash
# Start Qdrant
make docker-up
# OR manually:
cd docker && docker-compose up -d && cd ..

# Verify it's running (should return "ok")
curl http://localhost:6333/health
```

---

## 📄 STEP 4: Prepare Your Documents

### 4.1 Create Data Directories
```bash
mkdir -p data/raw data/processed data/chunks data/vectors data/term_index
```

### 4.2 Add Your Documents
Place your medical JSON documents in `data/raw/`:

```bash
# Copy your documents
cp /path/to/your/documents/*.json data/raw/

# Check files
ls -la data/raw/*.json | head -5
```

### 4.3 Expected JSON Format
Each document should have this structure:
```json
{
  "doc_id": "unique_id_here",
  "title": "Document Title",
  "text": "Full document text content...",
  "year": 2024,
  "authority_tier": "A1",    // A1, A2, A3, or A4
  "evidence_level": "H1",    // H1, H2, H3, or H4
  "doc_type": "textbook"     // or "journal_article", "guideline", etc.
}
```

---

## 🔨 STEP 5: Build the System Components

### 5.1 Process Documents
```bash
# Process all documents (~10 minutes)
make prep

# For testing with first 10 files only:
make dev-prep

# Verify results
echo "Processed files: $(ls data/processed/*.json 2>/dev/null | wc -l)"
```

### 5.2 Create Chunks
```bash
# Create chunks with quality validation (~5 minutes)
make chunk

# For testing with first 5 documents:
make dev-chunk

# Check quality metrics (should show PASS)
python -m src.index.chunk_quality_gate data/chunks/chunks.qa.csv

# Verify results
echo "Chunks created: $(wc -l < data/chunks/chunks.jsonl 2>/dev/null || echo 0)"
```

### 5.3 Generate Embeddings (GPU Recommended)
```bash
# This step takes 30-60 minutes!
make embed

# Verify results
ls -lh data/vectors/*.npy
```

### 5.4 Build Search Index
```bash
# Create Qdrant index (~2 minutes)
make index

# Verify index
curl http://localhost:6333/collections/ip_medcpt | python -m json.tool | grep vectors_count
```

---

## 🎯 STEP 6: Run the System

### Option A: Web Interface (Recommended)
```bash
# Start Gradio UI
make ui

# Open browser to:
# http://localhost:7860
```

### Option B: Command-Line Interface
```bash
python cli_interface.py

# Commands:
# - Type any medical query
# - 'rerank on/off' - Toggle reranker
# - 'topk 5' - Set result count
# - 'stats' - Show statistics
# - 'quit' - Exit
```

### Option C: API Server
```bash
# Start FastAPI
make api

# API available at:
# http://localhost:8000
# Docs: http://localhost:8000/docs
```

---

## ✅ STEP 7: Verify Everything Works

### 7.1 Test Query in Web UI
1. Open http://localhost:7860
2. Type: "What are the contraindications for bronchoscopy?"
3. Click "Submit Query"
4. You should see:
   - Response with medical information
   - Citations from sources
   - Confidence score
   - Query type classification

### 7.2 Test Emergency Detection
Type: "Management of massive hemoptysis"
- Should show red emergency banner
- Results prioritized for urgency

### 7.3 Check System Statistics
```bash
make stats
```
Should show:
- Number of processed files
- Number of chunks
- Embeddings status
- Index status

---

## 🔧 TROUBLESHOOTING

### Problem: "conda: command not found"
```bash
# Install Miniconda first:
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh
source ~/.bashrc
```

### Problem: "docker: command not found"
```bash
# Install Docker:
# Ubuntu/Debian:
sudo apt update && sudo apt install docker.io docker-compose

# macOS:
# Download Docker Desktop from docker.com
```

### Problem: "ModuleNotFoundError"
```bash
# Make sure conda environment is activated!
conda activate ipass2

# Reinstall dependencies
pip install -r requirements.txt
```

### Problem: "Qdrant connection refused"
```bash
# Restart Qdrant
make docker-down
make docker-up
sleep 10
curl http://localhost:6333/health
```

### Problem: "No chunks created"
```bash
# Check if documents exist
ls data/raw/*.json

# If no files, add documents first
# Then rerun:
make prep
make chunk
```

### Problem: "CUDA out of memory" (GPU error)
```bash
# Edit batch size in src/index/embed_medcpt.py
# Change: batch_size = 256
# To: batch_size = 128
```

### Problem: "OpenAI API error"
```bash
# Check your API key
grep OPENAI_API_KEY .env

# Test the key
python -c "
from openai import OpenAI
import os
from dotenv import load_dotenv
load_dotenv()
client = OpenAI()
response = client.chat.completions.create(
    model='gpt-3.5-turbo',
    messages=[{'role': 'user', 'content': 'test'}],
    max_tokens=10
)
print('✅ API key works')
"
```

---

## 📊 COMPLETE BUILD COMMANDS (Copy & Paste)

### Full Setup Script
```bash
# Run this entire block to set up everything:

# 1. Environment
conda activate ipass2

# 2. Start database
make docker-up
sleep 5

# 3. Build pipeline (will take ~60 minutes total)
make prep     # Process documents
make chunk    # Create chunks
make embed    # Generate embeddings (slow!)
make index    # Build search index

# 4. Verify
make stats

# 5. Start UI
make ui
```

---

## 🎮 USAGE EXAMPLES

### Example Queries to Try

#### Clinical Queries
- "What are the contraindications for bronchoscopy?"
- "Complications of EBUS-TBNA"
- "Indications for rigid bronchoscopy"

#### Emergency Queries
- "Management of massive hemoptysis"
- "Foreign body removal bronchoscopy"
- "Tension pneumothorax treatment"

#### Procedure Queries
- "How to perform EBUS-TBNA?"
- "Steps for fiducial marker placement"
- "Technique for bronchial thermoplasty"

#### Coding Queries
- "CPT code for bronchoscopy with biopsy"
- "Billing for EBUS with needle aspiration"
- "wRVU for navigational bronchoscopy"

#### Safety Queries
- "Pediatric dosing for lidocaine in bronchoscopy"
- "Pregnancy considerations for bronchoscopy"
- "Anticoagulation management for EBUS"

---

## 🔄 DAILY WORKFLOW

### Starting the System Each Day
```bash
# 1. Always activate environment first!
conda activate ipass2

# 2. Start database
make docker-up

# 3. Start interface
make ui
```

### Shutting Down
```bash
# 1. Stop UI: Press Ctrl+C in terminal

# 2. Stop database (optional)
make docker-down
```

### Adding New Documents
```bash
# 1. Add documents to data/raw/
cp new_docs/*.json data/raw/

# 2. Rebuild system
make clean  # Clear old data
make all    # Rebuild everything

# 3. Restart UI
make ui
```

---

## 📈 MONITORING & MAINTENANCE

### Check System Health
```bash
# View all statistics
make stats

# Check specific components
curl http://localhost:6333/health                    # Qdrant
curl http://localhost:8000/health                    # API
python -m src.index.chunk_quality_gate data/chunks/chunks.qa.csv  # Chunks
```

### View Logs
```bash
# Qdrant logs
docker logs qdrant

# Python logs (shown in terminal where service is running)
```

### Clear Cache/Restart Fresh
```bash
# Full reset
make clean
make docker-down
make docker-up
make all
```

---

## ⚡ QUICK REFERENCE

### Most Important Commands
```bash
conda activate ipass2      # ALWAYS RUN FIRST!
make docker-up            # Start database
make ui                   # Start web interface
make stats                # Check system status
```

### URLs to Remember
- **Web UI**: http://localhost:7860
- **API Docs**: http://localhost:8000/docs
- **Qdrant**: http://localhost:6333/dashboard

### File Locations
- **Documents**: `data/raw/*.json`
- **Chunks**: `data/chunks/chunks.jsonl`
- **Config**: `.env` and `configs/chunking.yaml`
- **Logs**: Terminal output

---

## 🆘 STILL STUCK?

If you're still having issues:

1. **Check Prerequisites**: Ensure conda, docker, and Python 3.11 are installed
2. **Verify Environment**: Make sure `conda activate ipass2` was run
3. **Check Logs**: Look for error messages in terminal
4. **Test Components**: Run `make stats` to see what's working
5. **Start Fresh**: Try `make clean` then `make all`

Remember: The most common issue is forgetting to activate the conda environment!

```bash
# This should ALWAYS be your first command:
conda activate ipass2
```

---

## ✅ SUCCESS CHECKLIST

You know the system is working when:

- [ ] `curl http://localhost:6333/health` returns "ok"
- [ ] `make stats` shows chunks and embeddings
- [ ] Web UI opens at http://localhost:7860
- [ ] Test query returns results with citations
- [ ] Emergency queries show red banner
- [ ] Confidence scores appear with results

---

**Ready to go!** Your IP Assist Lite system should now be fully operational. Start with the Web UI at http://localhost:7860 and try some example queries!