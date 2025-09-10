# Local Gradio App Setup Guide

## Quick Start

### 1. Environment Setup

First, ensure you have the correct conda environment activated:
```bash
conda activate ipass2
```

### 2. Configure API Key

Create or update your `.env` file with a valid OpenAI API key:
```bash
# .env file
OPENAI_API_KEY=sk-proj-your-actual-api-key-here
IP_GPT5_MODEL=gpt-4o-mini  # Start with GPT-4 for reliability
```

### 3. Start Qdrant (if not running)

```bash
./scripts/start_qdrant_local.sh
```

### 4. Run the Gradio App

```bash
# Basic run
python src/ui/gradio_app.py

# With debug logging
LOG_LEVEL=DEBUG python src/ui/gradio_app.py

# With specific model
IP_GPT5_MODEL=gpt-4o-mini python src/ui/gradio_app.py
```

The app will start on: http://localhost:7860

## Model Selection

The app now supports both GPT-5 and GPT-4 models:

- **GPT-5 Models** (if you have access):
  - `gpt-5`
  - `gpt-5-mini`
  - `gpt-5-nano`

- **GPT-4 Models** (more reliable fallbacks):
  - `gpt-4o-mini` (recommended default)
  - `gpt-4o`

## Troubleshooting

### 1. API Key Issues

If you see "401 Unauthorized" errors:
- Check your API key is correct in `.env`
- Ensure the key has access to the models you're trying to use
- Try using `gpt-4o-mini` which most keys have access to

### 2. Empty Responses

If the model returns empty responses:
- Switch to `gpt-4o-mini` in the dropdown
- Check the terminal for detailed error messages
- Enable debug logging: `LOG_LEVEL=DEBUG python src/ui/gradio_app.py`

### 3. Model Not Found

If GPT-5 models aren't accessible:
- The app will automatically fall back to GPT-4
- You can manually select GPT-4 models in the dropdown
- Check terminal output for fallback messages

### 4. MedCPT Warning

The warning "No sentence-transformers model found with name ncbi/MedCPT-Query-Encoder" is normal - it creates a model with mean pooling automatically.

## Features

### Query Processing
- Enter medical queries in natural language
- System automatically detects emergency queries
- Provides citations from medical literature
- Shows confidence scores and query classification

### Advanced Options
- **Use Reranker**: Improves result quality (slower)
- **Top K**: Number of results to return (1-10)
- **Model Selection**: Choose between GPT-5 and GPT-4 models

### Special Features
- **CPT Code Search**: Direct lookup of 5-digit CPT codes
- **System Stats**: View index statistics and configuration
- **Caching**: Results are cached for 10 minutes for faster repeated queries

## Debug Mode

To see detailed information about what's happening:

```bash
export LOG_LEVEL=DEBUG
python src/ui/gradio_app.py
```

Look for these indicators in the terminal:
- 🔵 Blue: Responses API calls
- 📝 Document: Text extraction status
- ⚠️ Warning: Fallback attempts
- ✅ Success: Successful operations
- ❌ Error: Failed operations

## Example Queries

Try these to test the system:

1. **Clinical**: "What are the indications for bronchoscopy?"
2. **Procedure**: "How do you perform EBUS-TBNA?"
3. **Emergency**: "Management of massive hemoptysis"
4. **CPT Code**: "What is CPT code 31628?"
5. **Complications**: "What are the complications of transbronchial biopsy?"

## Performance Tips

1. Start with `gpt-4o-mini` for best reliability
2. Disable reranker for faster responses
3. Use lower top_k values (3-5) for quicker results
4. Enable caching by keeping queries consistent

## Next Steps

Once the local version is working:
1. Test different models to find the best balance
2. Adjust retrieval parameters in the Advanced tab
3. Review the citations to ensure quality
4. Monitor the terminal for any warnings or errors