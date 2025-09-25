#!/bin/bash

# Knowledge Base Builder Script
# This script helps build a fresh knowledge base from your documents

set -e

echo "🏥 IP Assist Lite - Knowledge Base Builder"
echo "=========================================="

# Check if we're in the right directory
if [ ! -f "requirements.txt" ]; then
    echo "❌ Error: Please run this script from the IP_assist_lite root directory"
    exit 1
fi

# Create necessary directories
echo "📁 Creating directory structure..."
mkdir -p data/raw_pdfs
mkdir -p data/raw_text
mkdir -p data/processed
mkdir -p data/chunks
mkdir -p data/embeddings

# Check if medparse is running
echo "🔍 Checking medparse API..."
if curl -s http://127.0.0.1:8099/healthz > /dev/null; then
    echo "✅ Medparse API is running"
else
    echo "⚠️  Medparse API is not running. Please start it first:"
    echo "   cd ../ip_knowledge/medparse/medparse-docling"
    echo "   uvicorn api.main:app --reload --port 8099"
    echo ""
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check if Qdrant is running
echo "🔍 Checking Qdrant..."
if curl -s http://localhost:6333/collections > /dev/null; then
    echo "✅ Qdrant is running"
else
    echo "❌ Qdrant is not running. Please start it first:"
    echo "   docker run -p 6333:6333 qdrant/qdrant"
    exit 1
fi

# Check for documents
echo "📄 Checking for documents..."
pdf_count=$(find data/raw_pdfs -name "*.pdf" 2>/dev/null | wc -l)
text_count=$(find data/raw_text -name "*.txt" 2>/dev/null | wc -l)

if [ $pdf_count -eq 0 ] && [ $text_count -eq 0 ]; then
    echo "⚠️  No documents found in data/raw_pdfs/ or data/raw_text/"
    echo "   Please add your PDF and text documents to these directories"
    echo "   Then run this script again."
    exit 1
fi

echo "📊 Found $pdf_count PDF files and $text_count text files"

# Process documents
echo "🔄 Processing documents..."

if [ $pdf_count -gt 0 ]; then
    echo "📄 Processing PDFs through medparse..."
    python scripts/process_pdfs.py
fi

if [ $text_count -gt 0 ]; then
    echo "📝 Processing text files..."
    python scripts/process_text.py
fi

# Extract and chunk text
echo "✂️  Extracting and chunking text..."
python scripts/extract_text.py

# Build knowledge base
echo "🏗️  Building knowledge base..."
python scripts/build_knowledge_base.py

# Test the knowledge base
echo "🧪 Testing knowledge base..."
python scripts/test_retrieval.py

echo ""
echo "✅ Knowledge base built successfully!"
echo ""
echo "🚀 To start using your knowledge base:"
echo "   ./run.sh"
echo ""
echo "📊 To view statistics:"
echo "   python scripts/knowledge_base_stats.py"
