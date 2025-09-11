#!/bin/bash

# Update script for bronchmonkey2 Hugging Face Space
# This script helps update your HF Space with all recent improvements

echo "🚀 IP Assist Lite - Hugging Face Update Script"
echo "=============================================="
echo ""

# Check if HF Space directory exists or clone it
if [ ! -d "bronchmonkey2_space" ]; then
    echo "📥 Cloning your Hugging Face Space..."
    git clone https://huggingface.co/spaces/russellmiller49/Bronchmonkey2 bronchmonkey2_space
    if [ $? -ne 0 ]; then
        echo "❌ Failed to clone. Please check your HF credentials."
        echo "   You may need to run: huggingface-cli login"
        exit 1
    fi
else
    echo "📁 Using existing bronchmonkey2_space directory"
fi

cd bronchmonkey2_space

echo ""
echo "📋 Updating files..."

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
fi

if ! grep -q "pyyaml" requirements.txt 2>/dev/null; then
    echo "pyyaml>=6.0" >> requirements.txt
    echo "  ✓ Added pyyaml"
fi

echo ""
echo "🔍 Verification checklist:"
echo "  ✓ Smart citation system (smart_citations.py)"
echo "  ✓ Query normalizer (query_normalizer.py)"
echo "  ✓ Citation index (data/citation_index.json)"
echo "  ✓ Citation policy (configs/citation_policy.yaml)"
echo "  ✓ Balanced retrieval scoring"
echo "  ✓ 4000 token output limit"

echo ""
echo "📌 Next steps:"
echo "  1. cd bronchmonkey2_space"
echo "  2. Review the changes: git diff"
echo "  3. Commit: git add . && git commit -m 'Major update: Smart citations and query normalization'"
echo "  4. Push to HF: git push"
echo ""
echo "⚠️  Remember to set these in your HF Space settings:"
echo "  - OPENAI_API_KEY"
echo "  - IP_GPT5_MODEL=gpt-5-mini"
echo "  - USE_RESPONSES_API=1"
echo ""
echo "✅ Update preparation complete!"