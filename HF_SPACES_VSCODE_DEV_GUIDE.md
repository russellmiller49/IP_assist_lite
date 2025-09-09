# Hugging Face Spaces - VS Code Dev Mode Guide

## 🚀 Much Easier Deployment with VS Code Dev Mode!

VS Code dev mode allows you to directly edit and sync files with your HF Space, making deployment significantly easier.

## Prerequisites

1. **VS Code** installed locally
2. **Hugging Face account** with a Space created
3. **HF Token** with write permissions
4. Your local project files ready

## Step 1: Create Your HF Space

1. Go to [Hugging Face Spaces](https://huggingface.co/spaces)
2. Click "Create new Space"
3. Configure:
   - **Space name**: `ip-assist-lite`
   - **SDK**: Gradio
   - **Hardware**: ZeroGPU (select GPU tier)
   - **Space type**: Public or Private

## Step 2: Enable Dev Mode in VS Code

### Method A: Using HF Spaces VS Code Extension (Recommended)

1. **Install the Extension**:
   - Open VS Code
   - Go to Extensions (Ctrl+Shift+X)
   - Search for "Hugging Face Spaces"
   - Install the official extension

2. **Connect to Your Space**:
   ```bash
   # In VS Code Command Palette (Ctrl+Shift+P)
   > Hugging Face: Connect to Space
   
   # Enter your space URL:
   https://huggingface.co/spaces/YOUR_USERNAME/ip-assist-lite
   ```

3. **Authenticate**:
   - You'll be prompted for your HF token
   - Or set it in settings: `"huggingface.token": "hf_..."`

### Method B: Using Remote SSH

1. **Get SSH Connection Details**:
   - Go to your Space settings
   - Enable "Development mode"
   - Copy the SSH command provided

2. **Configure SSH in VS Code**:
   ```bash
   # Add to ~/.ssh/config
   Host hf-space-ip-assist
       HostName hf.space
       User YOUR_USERNAME-spaces-ip-assist-lite
       Port 2222
       IdentityFile ~/.ssh/id_rsa
   ```

3. **Connect via Remote-SSH**:
   - Install "Remote - SSH" extension
   - Command Palette > "Remote-SSH: Connect to Host"
   - Select your configured host

## Step 3: Direct File Sync Workflow

Once connected, you can directly work in the Space:

### 1. Open Terminal in VS Code
```bash
# You're now in your Space's environment
pwd  # Should show /home/user/app
```

### 2. Upload Files Directly

**Option 1: Drag and Drop in VS Code**
- Simply drag files from your local machine to the VS Code explorer
- Files sync automatically

**Option 2: Use VS Code Terminal**
```bash
# Create directory structure
mkdir -p data/chunks data/vectors data/term_index cache src/utils

# You can now drag and drop or copy files directly
```

**Option 3: Use rsync from Local Terminal**
```bash
# From your local machine
rsync -avz --progress \
  /home/rjm/projects/IP_assist_lite/app_hf_spaces_zerogpu.py \
  YOUR_USERNAME@hf.space:/home/user/app/app.py

rsync -avz --progress \
  /home/rjm/projects/IP_assist_lite/data/ \
  YOUR_USERNAME@hf.space:/home/user/app/data/
```

## Step 4: Quick Deployment with Script

Run the provided deployment script:
```bash
# From your local project directory
./vscode_deploy.sh
```

This script will:
1. Create a deployment package with proper structure
2. Rename files appropriately (app.py, requirements.txt)
3. Copy all data files if present
4. Provide instructions for VS Code deployment

## Step 5: VS Code Workspace Setup

Once connected to your Space, create `.vscode/settings.json`:

```json
{
  "files.watcherExclude": {
    "**/cache/**": true,
    "**/__pycache__/**": true,
    "**/*.pyc": true
  },
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": false,
  "python.linting.flake8Enabled": true,
  "python.formatting.provider": "black",
  "editor.formatOnSave": true,
  "files.autoSave": "afterDelay",
  "files.autoSaveDelay": 1000
}
```

## Step 6: Live Development Workflow

### Real-time Editing:
1. **Edit files directly** in VS Code - changes auto-sync
2. **Space auto-rebuilds** when files change
3. **Monitor logs** in HF Space UI for errors

### Best Practices:
1. **Test locally first** with `python app.py`
2. **Use dev branch** in your Space for testing
3. **Keep data files in Git LFS** for large embeddings
4. **Monitor GPU usage** in Space metrics

## Advantages of VS Code Dev Mode

✅ **Direct file editing** - No need for git commits
✅ **Live preview** - See changes immediately
✅ **Integrated terminal** - Run commands directly in Space
✅ **Drag-and-drop** - Easy file uploads
✅ **IntelliSense** - Code completion works
✅ **Debugging** - Can set breakpoints (limited)

## File Structure After Deployment

Your Space should look like:
```
/home/user/app/
├── app.py                    # Main application
├── requirements.txt          # Dependencies
├── README.md                 # With YAML frontmatter
├── data/
│   ├── chunks/
│   │   └── chunks.jsonl     # Your knowledge base
│   ├── vectors/
│   │   └── embeddings.npy   # Precomputed embeddings
│   └── term_index/
│       └── cpt.jsonl        # CPT code index
├── cache/                   # Runtime cache (auto-created)
└── src/                     # Optional modules
    └── utils/
        └── serialization.py
```

## Environment Variables

Set these in HF Space Settings > Variables and secrets:
- `OPENAI_API_KEY` (required)
- `IP_GPT5_MODEL` (default: gpt-5-mini)
- `HF_USERNAME` (for auth, optional)
- `HF_PASSWORD` (for auth, optional)

## Troubleshooting

### VS Code can't connect:
- Check your HF token has write permissions
- Ensure Space is running (not paused)
- Try refreshing the connection

### Files not syncing:
- Check file size limits (100MB without LFS)
- Ensure proper directory structure
- Verify no permission issues

### Space not rebuilding:
- Check logs for syntax errors
- Verify requirements.txt is valid
- Ensure README.md has proper YAML frontmatter

## Quick Commands Reference

```bash
# In VS Code terminal (connected to Space)

# Check current directory
pwd

# View file structure
ls -la

# Monitor app logs
tail -f logs.txt

# Test app locally
python app.py

# Install additional packages
pip install package_name
# Then add to requirements.txt

# Check GPU availability
python -c "import torch; print(torch.cuda.is_available())"

# Clear cache
rm -rf cache/*
```

## Tips for Smooth Development

1. **Start with minimal setup** - Get basic app working first
2. **Add data incrementally** - Upload chunks.jsonl, then embeddings
3. **Use mock data** - App works without full data for testing
4. **Monitor resources** - Check GPU/memory usage in Space metrics
5. **Version control** - Still commit important changes to git

---

**Pro Tip**: You can have multiple VS Code windows - one connected to your Space, one with your local project. This makes it easy to compare and copy files!