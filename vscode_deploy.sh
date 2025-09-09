#!/bin/bash
# VS Code Dev Mode Deployment Script for HF Spaces
# Run this script from your local project directory while connected to HF Space via VS Code

echo "🚀 HF Spaces VS Code Deployment Script"
echo "======================================="

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if we're in the right directory
if [ ! -f "app_hf_spaces_zerogpu.py" ]; then
    echo -e "${RED}❌ Error: app_hf_spaces_zerogpu.py not found!${NC}"
    echo "Please run this script from your IP_assist_lite project directory"
    exit 1
fi

# Configuration
REMOTE_HOST="${HF_SPACE_HOST:-hf-space-ip-assist}"
REMOTE_PATH="/home/user/app"

echo -e "${YELLOW}📦 Starting deployment...${NC}"

# Function to copy files via VS Code terminal
deploy_via_vscode() {
    echo -e "${GREEN}Using VS Code integrated terminal deployment${NC}"
    
    # Create a deployment package
    echo "Creating deployment package..."
    
    # Create temporary deployment directory
    DEPLOY_DIR="hf_deploy_temp"
    rm -rf $DEPLOY_DIR
    mkdir -p $DEPLOY_DIR
    
    # Copy main files
    cp app_hf_spaces_zerogpu.py $DEPLOY_DIR/app.py
    cp requirements_zerogpu.txt $DEPLOY_DIR/requirements.txt
    
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
    
    if [ -d "data/term_index" ]; then
        mkdir -p $DEPLOY_DIR/data/term_index
        cp data/term_index/cpt.jsonl $DEPLOY_DIR/data/term_index/ 2>/dev/null || true
    fi
    
    # Copy utils if needed
    if [ -f "src/utils/serialization.py" ]; then
        mkdir -p $DEPLOY_DIR/src/utils
        cp src/utils/serialization.py $DEPLOY_DIR/src/utils/
        touch $DEPLOY_DIR/src/__init__.py
        touch $DEPLOY_DIR/src/utils/__init__.py
    fi
    
    # Create README with frontmatter
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

Interventional Pulmonology Information Retrieval System with GPT-5 and ZeroGPU.

## Features
- 🔍 Hybrid search with MedCPT embeddings
- 📊 Hierarchy-aware ranking
- 🚨 Emergency detection
- ⚠️ Safety checks
- 💊 CPT code search

## Disclaimer
For informational purposes only. Always consult qualified healthcare professionals.
EOF
    
    echo -e "${GREEN}✅ Deployment package created${NC}"
    echo ""
    echo -e "${YELLOW}📤 Now in VS Code with your Space connected:${NC}"
    echo ""
    echo "1. In VS Code Explorer, delete old files if updating"
    echo "2. Drag and drop all files from $DEPLOY_DIR/ to your Space"
    echo "3. Or use VS Code terminal:"
    echo "   cp -r $DEPLOY_DIR/* ."
    echo ""
    echo "4. The Space will auto-rebuild when files change"
}

# Function to deploy via SSH
deploy_via_ssh() {
    echo -e "${GREEN}Using SSH deployment${NC}"
    
    # Test SSH connection
    echo "Testing SSH connection..."
    if ssh -o ConnectTimeout=5 $REMOTE_HOST "echo 'SSH connection successful'" 2>/dev/null; then
        echo -e "${GREEN}✅ SSH connection established${NC}"
        
        # Create remote directories
        ssh $REMOTE_HOST "mkdir -p $REMOTE_PATH/data/chunks $REMOTE_PATH/data/vectors $REMOTE_PATH/data/term_index $REMOTE_PATH/cache"
        
        # Copy files
        echo "Copying application files..."
        scp app_hf_spaces_zerogpu.py $REMOTE_HOST:$REMOTE_PATH/app.py
        scp requirements_zerogpu.txt $REMOTE_HOST:$REMOTE_PATH/requirements.txt
        
        # Copy data files if they exist
        if [ -f "data/chunks/chunks.jsonl" ]; then
            echo "Copying chunks data..."
            scp data/chunks/chunks.jsonl $REMOTE_HOST:$REMOTE_PATH/data/chunks/
        fi
        
        if [ -f "data/vectors/embeddings.npy" ]; then
            echo "Copying embeddings (this may take a while)..."
            scp data/vectors/embeddings.npy $REMOTE_HOST:$REMOTE_PATH/data/vectors/
        fi
        
        echo -e "${GREEN}✅ Deployment complete via SSH${NC}"
    else
        echo -e "${RED}❌ SSH connection failed${NC}"
        echo "Falling back to manual deployment instructions..."
        deploy_via_vscode
    fi
}

# Main deployment logic
echo -e "${YELLOW}Select deployment method:${NC}"
echo "1) VS Code drag-and-drop (recommended if VS Code is connected)"
echo "2) SSH deployment (if SSH is configured)"
echo "3) Generate files only (manual upload)"

read -p "Enter choice [1-3]: " choice

case $choice in
    1)
        deploy_via_vscode
        ;;
    2)
        deploy_via_ssh
        ;;
    3)
        deploy_via_vscode
        echo -e "${YELLOW}Files prepared in $DEPLOY_DIR/${NC}"
        echo "Upload these manually to your HF Space"
        ;;
    *)
        echo -e "${RED}Invalid choice${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${YELLOW}⚠️ Don't forget to set these secrets in your HF Space settings:${NC}"
echo "  • OPENAI_API_KEY=sk-..."
echo "  • IP_GPT5_MODEL=gpt-5-mini"
echo "  • HF_USERNAME=admin (optional)"
echo "  • HF_PASSWORD=<secure_password> (optional)"
echo ""
echo -e "${GREEN}🎉 Deployment preparation complete!${NC}"
echo "Your Space URL: https://huggingface.co/spaces/YOUR_USERNAME/ip-assist-lite"