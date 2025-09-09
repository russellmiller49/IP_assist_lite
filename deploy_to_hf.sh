#!/bin/bash
# Deployment script for Hugging Face Spaces

echo "🚀 IP Assist Lite - HF Spaces Deployment Script"
echo "=============================================="

# Check if HF_TOKEN is set
if [ -z "$HF_TOKEN" ]; then
    echo "❌ Error: HF_TOKEN environment variable not set"
    echo "Please run: export HF_TOKEN=your_huggingface_token"
    exit 1
fi

# Configuration
HF_USERNAME=${HF_USERNAME:-"your_username"}
SPACE_NAME="ip-assist-lite"
REPO_URL="https://huggingface.co/spaces/$HF_USERNAME/$SPACE_NAME"

echo "📦 Preparing deployment files..."

# Create deployment directory
DEPLOY_DIR="hf_deployment"
rm -rf $DEPLOY_DIR
mkdir -p $DEPLOY_DIR

# Copy main application
echo "📄 Copying application files..."
cp app_hf_spaces_zerogpu.py $DEPLOY_DIR/app.py
cp requirements_zerogpu.txt $DEPLOY_DIR/requirements.txt

# Create README for HF Space
cat > $DEPLOY_DIR/README.md << 'EOF'
---
title: IP Assist Lite Medical AI
emoji: 🏥
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: 4.44.0
app_file: app.py
pinned: false
license: apache-2.0
models:
  - chrisjay/MedCPT-Query-Encoder
  - cross-encoder/ms-marco-MiniLM-L-6-v2
---

# IP Assist Lite - Medical AI Assistant

## 🏥 Interventional Pulmonology Information Retrieval System

Evidence-based medical information retrieval with GPT-5 and ZeroGPU acceleration.

### Features
- 🔍 Hybrid search with MedCPT embeddings
- 📊 Hierarchy-aware ranking
- 🚨 Emergency detection
- ⚠️ Safety checks
- 💊 CPT code search

### Disclaimer
For informational purposes only. Always consult qualified healthcare professionals.
EOF

# Copy data files if they exist
if [ -d "data/chunks" ]; then
    echo "📊 Copying data files..."
    mkdir -p $DEPLOY_DIR/data/chunks
    cp data/chunks/chunks.jsonl $DEPLOY_DIR/data/chunks/ 2>/dev/null || true
fi

if [ -d "data/vectors" ]; then
    mkdir -p $DEPLOY_DIR/data/vectors
    cp data/vectors/embeddings.npy $DEPLOY_DIR/data/vectors/ 2>/dev/null || true
fi

# Create .gitignore
cat > $DEPLOY_DIR/.gitignore << 'EOF'
__pycache__/
*.pyc
.env
*.log
cache/
EOF

# Initialize git repository
cd $DEPLOY_DIR
git init
git lfs track "*.npy" 2>/dev/null || true
git lfs track "*.pkl" 2>/dev/null || true
git lfs track "*.jsonl" 2>/dev/null || true

# Add files
git add -A
git commit -m "Initial deployment of IP Assist Lite"

# Check if space exists
echo "🔍 Checking if Space exists..."
if git ls-remote $REPO_URL.git HEAD &>/dev/null; then
    echo "✅ Space exists, updating..."
    git remote add origin $REPO_URL.git
    git pull origin main --allow-unrelated-histories --no-edit
    git push origin main --force
else
    echo "📝 Creating new Space..."
    echo "Please create the Space manually at https://huggingface.co/spaces"
    echo "Then run this script again"
    exit 1
fi

echo "✅ Deployment complete!"
echo "🌐 Visit your Space at: $REPO_URL"
echo ""
echo "⚠️ Don't forget to set these secrets in your Space settings:"
echo "  - OPENAI_API_KEY"
echo "  - IP_GPT5_MODEL (default: gpt-5-mini)"
echo "  - HF_USERNAME (for auth)"
echo "  - HF_PASSWORD (for auth)"