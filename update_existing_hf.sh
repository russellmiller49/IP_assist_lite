#!/bin/bash

# Update script for existing bronchmonkey2 Hugging Face Space
# This updates your already cloned HF Space in the bronchmonkey2 folder

echo "🚀 IP Assist Lite - Hugging Face Update (Existing Clone)"
echo "========================================================"
echo ""

# Check if the bronchmonkey2 directory exists
if [ ! -d "bronchmonkey2" ]; then
    echo "❌ Error: bronchmonkey2 directory not found!"
    echo "   Expected location: /home/rjm/projects/IP_assist_lite/bronchmonkey2"
    exit 1
fi

echo "📁 Using existing bronchmonkey2 directory"
cd bronchmonkey2

# Pull latest changes from HF
echo ""
echo "📥 Pulling latest changes from Hugging Face..."
git pull

echo ""
echo "📋 Updating files from huggingface_deploy..."

# Copy source files
echo "  - Copying Python source files..."
cp -r ../huggingface_deploy/src/* src/ 2>/dev/null || mkdir -p src && cp -r ../huggingface_deploy/src/* src/

# Copy configs
echo "  - Copying configuration files..."
cp -r ../huggingface_deploy/configs/* configs/ 2>/dev/null || mkdir -p configs && cp -r ../huggingface_deploy/configs/* configs/

# Copy data files
echo "  - Copying data files (citation index)..."
cp -r ../huggingface_deploy/data/* data/ 2>/dev/null || mkdir -p data && cp -r ../huggingface_deploy/data/* data/

# Copy scripts
echo "  - Copying utility scripts..."
cp -r ../huggingface_deploy/scripts/* scripts/ 2>/dev/null || mkdir -p scripts && cp -r ../huggingface_deploy/scripts/* scripts/

echo ""
echo "📝 Updating requirements.txt..."

# Check if rapidfuzz is in requirements
if ! grep -q "rapidfuzz" requirements.txt 2>/dev/null; then
    echo "rapidfuzz>=3.0.0" >> requirements.txt
    echo "  ✓ Added rapidfuzz"
else
    echo "  ✓ rapidfuzz already present"
fi

if ! grep -q "pyyaml" requirements.txt 2>/dev/null; then
    echo "pyyaml>=6.0" >> requirements.txt
    echo "  ✓ Added pyyaml"
else
    echo "  ✓ pyyaml already present"
fi

echo ""
echo "📊 Showing changes..."
git status --short

echo ""
echo "🔍 Key improvements added:"
echo "  ✓ Smart citation system (smart_citations.py)"
echo "  ✓ Query normalizer (fixes typos and abbreviations)"
echo "  ✓ Citation index (proper author names)"
echo "  ✓ Citation policy (hides textbooks)"
echo "  ✓ Balanced retrieval (better article finding)"
echo "  ✓ 4000 token output (no cutoffs)"

echo ""
echo "📌 Next steps:"
echo "  1. Review the changes: git diff"
echo "  2. Stage all changes: git add ."
echo "  3. Commit: git commit -m 'Major update: Smart citations, query normalization, better retrieval'"
echo "  4. Push to HF: git push"
echo ""
echo "💡 Tip: You can also push from VS Code if you prefer!"
echo ""
echo "⚠️  Remember to verify these are set in your HF Space settings:"
echo "  - OPENAI_API_KEY"
echo "  - IP_GPT5_MODEL=gpt-5-mini"
echo "  - USE_RESPONSES_API=1"
echo ""
echo "✅ Update complete! You're now in the bronchmonkey2 directory."
echo "   Current path: $(pwd)"