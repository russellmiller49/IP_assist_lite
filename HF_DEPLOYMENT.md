# HF Spaces Deployment Instructions

## Files Created for HF Spaces:

1. **`app.py`** - Main application file with authentication
2. **`requirements.txt`** - Dependencies optimized for HF Spaces
3. **`README.md`** - Space description and documentation

## Authentication Setup:

The app includes simple username/password authentication. Set these in HF Spaces secrets:

- `HF_USERNAME` - Username for access (default: "admin")
- `HF_PASSWORD` - Password for access (default: "ipassist2024")

## Required Environment Variables:

In HF Spaces settings, add these secrets:

1. **`OPENAI_API_KEY`** - Your OpenAI API key for GPT-5 access
2. **`HF_USERNAME`** - Authentication username
3. **`HF_PASSWORD`** - Authentication password

## Deployment Steps:

1. **Upload files to your HF Space:**
   - Upload `app.py` as the main file
   - Upload `requirements.txt`
   - Upload `README.md`

2. **Set environment variables:**
   - Go to Space Settings → Secrets
   - Add `OPENAI_API_KEY` with your API key
   - Add `HF_USERNAME` and `HF_PASSWORD` for authentication

3. **Configure Space settings:**
   - Hardware: ZeroGPU (as you selected)
   - Visibility: Public (or Private if you prefer)
   - SDK: Gradio

## Features Included:

✅ **Authentication** - Username/password protection
✅ **Medical AI** - Full IP Assist Lite functionality
✅ **Emergency Detection** - Automatic urgent query routing
✅ **Safety Checks** - Contraindication and pediatric warnings
✅ **CPT Code Search** - Direct billing code lookup
✅ **System Statistics** - Database overview
✅ **Caching** - Performance optimization
✅ **Error Handling** - Robust error management

## Testing:

Once deployed, users will need to authenticate with the username/password you set in the secrets.

The app will automatically:
- Initialize the orchestrator
- Load medical models
- Connect to the vector database
- Provide full medical query capabilities




