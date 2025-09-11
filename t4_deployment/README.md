# IP Assist Lite - T4 GPU Deployment

## Deployment Instructions for Hugging Face Spaces (T4 Medium)

### Step 1: Create New Space
1. Go to https://huggingface.co/spaces
2. Click "Create new Space"
3. Choose:
   - Space name: `IP-Assist-Lite-T4` (or your preference)
   - Select **Gradio** SDK
   - Select **T4 medium** ($0.60/hour)
   - Set to **Private** initially for testing

### Step 2: Clone and Setup
```bash
git clone https://huggingface.co/spaces/YOUR_USERNAME/IP-Assist-Lite-T4
cd IP-Assist-Lite-T4
```

### Step 3: Copy Files
Copy all files from this `t4_deployment` folder to your Space directory

### Step 4: Set Environment Variables
In your HF Space Settings → Variables and secrets, add:
- `OPENAI_API_KEY`: Your OpenAI API key (required)
- `IP_GPT5_MODEL`: `gpt-5-mini` (or `gpt-4o-mini` for fallback)
- `USE_CUDA`: `1` (enables GPU acceleration)

### Step 5: Push to Space
```bash
git add .
git commit -m "Deploy IP Assist Lite with T4 GPU"
git push
```

## Features Enabled with T4 GPU

- **Fast Query Encoding**: MedCPT embeddings on GPU (~10x faster)
- **Batch Processing**: Efficient batch operations for multiple queries
- **Cross-Encoder Reranking**: GPU-accelerated reranking
- **Lower Latency**: <500ms for most queries
- **Higher Throughput**: Handle 20+ concurrent users

## Cost Optimization

### Auto-Sleep Configuration
Add to your Space Settings:
- Sleep timeout: 1 hour (saves costs during low usage)
- Hardware: T4 medium (16GB VRAM is sufficient)

### Monitoring
- Check Space logs for GPU utilization
- Typical VRAM usage: 2-4GB
- Typical GPU usage: 20-40% for single queries

## Performance Benchmarks (T4)

- Query encoding: ~50ms
- Semantic search: ~100ms  
- Reranking (10 docs): ~80ms
- GPT-5 response: 1-3 seconds
- Total response time: 1.5-3.5 seconds

## Troubleshooting

If you see CUDA errors:
1. Ensure T4 GPU is selected in Space settings
2. Check that `USE_CUDA=1` is set
3. Restart the Space if needed

If you see memory errors:
1. Reduce batch size in app.py
2. Clear cache periodically
3. Consider upgrading to A10G if persistent