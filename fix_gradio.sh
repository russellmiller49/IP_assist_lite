#!/bin/bash
# Quick Gradio Fix Script
# Addresses the jinja2.exceptions.TemplateNotFound: 'frontend/index.html' error

echo "🔧 Quick Gradio Fix Script"
echo "========================="

# Activate conda environment
source /Users/russellmiller/miniconda3/etc/profile.d/conda.sh
conda activate ipass

echo "🔄 Current Gradio version:"
pip show gradio | grep Version

echo ""
echo "🔄 Attempting fixes..."

# Method 1: Reinstall with specific version
echo "📦 Method 1: Installing Gradio 4.44.0 (stable version)..."
pip uninstall gradio -y
pip install gradio==4.44.0

# Check if it worked
python -c "
import gradio as gr
import os
gradio_path = os.path.dirname(gr.__file__)
frontend_path = os.path.join(gradio_path, 'frontend')
index_file = os.path.join(frontend_path, 'index.html')
if os.path.exists(index_file):
    print('✅ Frontend templates found!')
    exit(0)
else:
    print('❌ Frontend templates still missing')
    exit(1)
"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ SUCCESS! Gradio frontend templates are now available."
    echo "🚀 You can now run: python src/ui/gradio_app.py"
    exit 0
fi

# Method 2: Try downgrading further
echo ""
echo "📦 Method 2: Installing Gradio 4.20.0 (older stable version)..."
pip uninstall gradio -y
pip install gradio==4.20.0

# Check again
python -c "
import gradio as gr
import os
gradio_path = os.path.dirname(gr.__file__)
frontend_path = os.path.join(gradio_path, 'frontend')
index_file = os.path.join(frontend_path, 'index.html')
if os.path.exists(index_file):
    print('✅ Frontend templates found!')
    exit(0)
else:
    print('❌ Frontend templates still missing')
    exit(1)
"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ SUCCESS! Gradio frontend templates are now available."
    echo "🚀 You can now run: python src/ui/gradio_app.py"
    exit 0
fi

# Method 3: Install from source
echo ""
echo "📦 Method 3: Installing from GitHub source..."
pip uninstall gradio -y
pip install git+https://github.com/gradio-app/gradio.git

# Check again
python -c "
import gradio as gr
import os
gradio_path = os.path.dirname(gr.__file__)
frontend_path = os.path.join(gradio_path, 'frontend')
index_file = os.path.join(frontend_path, 'index.html')
if os.path.exists(index_file):
    print('✅ Frontend templates found!')
    exit(0)
else:
    print('❌ Frontend templates still missing')
    exit(1)
"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ SUCCESS! Gradio frontend templates are now available."
    echo "🚀 You can now run: python src/ui/gradio_app.py"
    exit 0
fi

echo ""
echo "❌ All methods failed. Creating alternative solutions..."
echo ""
echo "🎯 Alternative Solutions:"
echo "1. Use FastAPI UI: python fastapi_ui.py"
echo "2. Use Streamlit UI: streamlit run streamlit_ui.py" 
echo "3. Use CLI UI: python cli_ui.py"
echo "4. Use the comprehensive fix: python fix_gradio_comprehensive.py"