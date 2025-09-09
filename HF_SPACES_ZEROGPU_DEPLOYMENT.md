# Hugging Face Spaces ZeroGPU Deployment Guide

## Overview
This guide provides step-by-step instructions for deploying IP Assist Lite to Hugging Face Spaces with ZeroGPU support for optimal performance.

## Files Created

1. **app_hf_spaces_zerogpu.py** - Full-featured Gradio app with GPU acceleration
2. **requirements_zerogpu.txt** - Optimized dependencies for HF Spaces
3. **README_HF.md** - README for the HF Space (below)

## Deployment Steps

### 1. Create a New Hugging Face Space

1. Go to [Hugging Face Spaces](https://huggingface.co/spaces)
2. Click "Create new Space"
3. Configure:
   - **Space name**: `ip-assist-lite`
   - **License**: Apache 2.0 or MIT
   - **SDK**: Gradio
   - **Hardware**: ZeroGPU (A10G/A100)
   - **Visibility**: Public or Private

### 2. Set Up Environment Variables

In your Space settings, add these secrets:
```
OPENAI_API_KEY=your_openai_api_key_here
IP_GPT5_MODEL=gpt-5-mini
HF_USERNAME=admin
HF_PASSWORD=your_secure_password_here
EMBEDDING_MODEL=chrisjay/MedCPT-Query-Encoder
RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
```

### 3. Upload Files

Upload these files to your Space:

#### a. Rename and upload the main app:
```bash
# In your local project
cp app_hf_spaces_zerogpu.py app.py
```

#### b. Upload requirements:
```bash
cp requirements_zerogpu.txt requirements.txt
```

#### c. Create and upload README.md:
```markdown
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

This is a medical AI assistant specialized in Interventional Pulmonology, providing:

- 🔍 Evidence-based medical information retrieval
- 📊 Hierarchy-aware ranking (Authority & Evidence levels)
- 🚨 Emergency detection and routing
- ⚠️ Safety checks for critical information
- 💊 CPT code search and billing information
- 🧠 Powered by GPT-5 family models

### Features

- **Hybrid Search**: Combines BM25 keyword search with MedCPT semantic embeddings
- **Authority Tiers**: A1 (Guidelines 2025) > A2 (Practical 2022) > A3 (Reviews) > A4 (Articles)
- **Evidence Levels**: H1 (Guidelines/SR) > H2 (RCT) > H3 (Cohort) > H4 (Case)
- **Safety First**: Automatic detection of emergencies, pediatric cases, and dosage concerns
- **Cross-Encoder Reranking**: Improves precision for complex queries
- **GPU Acceleration**: ZeroGPU support for fast embeddings and reranking

### Usage

1. Enter your medical query in the main tab
2. Select the AI model (GPT-5 family recommended)
3. Choose whether to use reranking (recommended for precision)
4. Review the response with evidence sources
5. Check safety flags and confidence scores

### Important Disclaimer

⚠️ This system is for informational purposes only. Always:
- Verify information with official medical guidelines
- Consult qualified healthcare professionals
- Consider patient-specific factors
- Follow institutional protocols

### Technical Details

- **Embedding Model**: MedCPT (Medical-specialized BERT)
- **Reranker**: Cross-encoder trained on MS MARCO
- **LLM**: GPT-5 family with medical fine-tuning
- **Hardware**: ZeroGPU for acceleration
- **Framework**: Gradio 4.44+

### Citations

Based on authoritative sources including:
- Principles and Practice of Interventional Pulmonology (2025)
- Practical Guide to Interventional Pulmonology (2022)
- BACADA Bronchoscopy Guidelines (2012)
- Recent peer-reviewed articles

### Support

For issues or questions, please contact the development team.

---
*Version 1.0.0 | Last Updated: 2025*
```

### 4. Upload Data Files (Optional)

If you have preprocessed data, create a data directory structure:

```
data/
├── chunks/
│   └── chunks.jsonl
├── vectors/
│   └── embeddings.npy
└── term_index/
    ├── cpt.jsonl
    └── aliases.jsonl
```

You can upload these using:
```bash
# Via Git LFS for large files
git lfs track "*.npy"
git lfs track "*.jsonl"
git add .gitattributes
git add data/
git commit -m "Add preprocessed data"
git push
```

### 5. Test Locally First

Before deploying, test the app locally:

```bash
# In your conda environment
conda activate ipass2

# Install requirements
pip install -r requirements_zerogpu.txt

# Run the app
python app_hf_spaces_zerogpu.py
```

Visit http://localhost:7860 to test.

### 6. Deploy to Hugging Face

#### Option A: Via Git

```bash
# Clone your space
git clone https://huggingface.co/spaces/YOUR_USERNAME/ip-assist-lite
cd ip-assist-lite

# Copy files
cp /path/to/app_hf_spaces_zerogpu.py app.py
cp /path/to/requirements_zerogpu.txt requirements.txt

# Create README
cat > README.md << 'EOF'
[paste the README content from above]
EOF

# Commit and push
git add .
git commit -m "Initial deployment of IP Assist Lite"
git push
```

#### Option B: Via Web UI

1. Go to your Space's Files tab
2. Upload `app.py` (renamed from app_hf_spaces_zerogpu.py)
3. Upload `requirements.txt` (renamed from requirements_zerogpu.txt)
4. Create README.md with the content above
5. Click "Commit changes"

### 7. Monitor Deployment

1. Check the Build logs for any errors
2. Once built, test the Space with example queries
3. Monitor the Logs tab for runtime issues

## Optimization Tips

### For Faster Startup
- Pre-cache embeddings in the Space's persistent storage
- Use smaller models initially (gpt-5-nano)
- Enable gradio queue with `demo.queue(max_size=10)`

### For Better Performance
- Use ZeroGPU decorators on compute-heavy functions
- Batch embedding computations
- Implement result caching with TTL
- Use async where possible

### For Cost Management
- Set rate limits in the Space settings
- Use authentication to control access
- Monitor API usage in OpenAI dashboard
- Consider using gpt-5-nano for non-critical queries

## Troubleshooting

### Common Issues

1. **Import errors**: Ensure all dependencies are in requirements.txt
2. **GPU not available**: Check ZeroGPU is enabled in Space settings
3. **OpenAI API errors**: Verify API key is set correctly
4. **Memory issues**: Reduce batch sizes or use smaller models
5. **Timeout errors**: Increase duration in @spaces.GPU decorator

### Debug Mode

Add this to your app.py for debugging:
```python
import os
os.environ["GRADIO_DEBUG"] = "1"
logging.basicConfig(level=logging.DEBUG)
```

## Security Considerations

1. **API Keys**: Always use HF Secrets, never hardcode
2. **Authentication**: Enable for production deployments
3. **Rate Limiting**: Implement to prevent abuse
4. **Input Validation**: Sanitize all user inputs
5. **Medical Disclaimer**: Always display prominently

## Maintenance

### Regular Updates
- Update medical knowledge base quarterly
- Refresh embeddings when new documents added
- Monitor and update deprecated dependencies
- Review and update safety checks

### Monitoring
- Check Space analytics for usage patterns
- Monitor error logs weekly
- Track query types and improve common ones
- Gather user feedback for improvements

## Advanced Features

### Adding Custom Data

1. Prepare your medical documents in JSON format
2. Process with the chunking pipeline
3. Generate embeddings using MedCPT
4. Upload to Space's data directory
5. Update chunk loading logic

### Multi-language Support

```python
# Add to app.py
from transformers import pipeline
translator = pipeline("translation", model="Helsinki-NLP/opus-mt-en-mul")
```

### Voice Interface

```python
# Add audio input
audio_input = gr.Audio(source="microphone", type="filepath")
# Use speech-to-text model
```

## Support and Contributions

- **Issues**: Report via GitHub Issues
- **Contributions**: PRs welcome with tests
- **Documentation**: Help improve guides
- **Community**: Join discussions on HF Forums

## License

Apache 2.0 - See LICENSE file for details

---

**Last Updated**: January 2025
**Version**: 1.0.0
**Author**: IP Assist Team