# Cursor + WSL + HF Spaces Guide

## ✅ Yes, Cursor Works with WSL and HF Spaces!

Cursor (the AI-powered VS Code fork) fully supports both WSL and Remote-SSH connections.

## Setting Up Cursor with WSL for HF Spaces

### Step 1: Verify Your Current Setup

Since you're already using WSL (as shown in your environment), Cursor should work seamlessly:

```bash
# In your WSL terminal
pwd
# Shows: /home/rjm/projects/IP_assist_lite

# Check WSL version
wsl --version
```

### Step 2: Install Remote Extensions in Cursor

1. **Open Cursor**
2. **Go to Extensions** (Ctrl+Shift+X)
3. **Install these extensions:**

   a. **Remote - SSH**
   - Publisher: Microsoft
   - Allows SSH connections to HF Spaces
   
   b. **Remote - WSL** (likely already installed)
   - Publisher: Microsoft
   - For WSL integration
   
   c. **Remote Explorer**
   - Publisher: Microsoft
   - Manages remote connections

### Step 3: Configure SSH in WSL for HF Spaces

Since you're in WSL, your SSH config is at `~/.ssh/config` in your WSL home:

```bash
# In WSL terminal
nano ~/.ssh/config

# Add this configuration:
Host hf-ip-assist
    HostName hf.space
    User YOUR_HF_USERNAME-spaces-ip-assist-lite
    Port 22
    IdentityFile ~/.ssh/id_rsa
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
```

### Step 4: Set Up SSH Keys in WSL

```bash
# Check if you have SSH keys
ls ~/.ssh/

# If no id_rsa exists, generate one:
ssh-keygen -t rsa -b 4096 -C "your_email@example.com"

# Copy your public key
cat ~/.ssh/id_rsa.pub
```

Then add this public key to your Hugging Face account:
1. Go to https://huggingface.co/settings/keys
2. Click "Add SSH key"
3. Paste the key from WSL

### Step 5: Connect to HF Space from Cursor

#### Method A: Direct from Cursor in WSL

1. **Open Cursor in WSL**:
   ```bash
   # From your WSL terminal
   cd /home/rjm/projects/IP_assist_lite
   cursor .
   ```

2. **Connect to HF Space**:
   - Press `Ctrl+Shift+P`
   - Type: "Remote-SSH: Connect to Host"
   - Select: `hf-ip-assist`

#### Method B: Using Cursor's Remote Explorer

1. Click the **Remote Explorer** icon in left sidebar
2. Select **SSH Targets** from dropdown
3. Your `hf-ip-assist` should appear
4. Right-click → Connect

### Step 6: Deployment Workflow from WSL

Create this deployment script specifically for Cursor+WSL:

```bash
#!/bin/bash
# cursor_wsl_deploy.sh - Deploy to HF Spaces from Cursor+WSL

echo "🚀 Cursor + WSL → HF Spaces Deployment"
echo "======================================"

# Your project directory in WSL
PROJECT_DIR="/home/rjm/projects/IP_assist_lite"
cd $PROJECT_DIR

# Create deployment package
DEPLOY_DIR="cursor_hf_deploy"
rm -rf $DEPLOY_DIR
mkdir -p $DEPLOY_DIR

# Copy and rename files
cp app_hf_spaces_zerogpu.py $DEPLOY_DIR/app.py
cp requirements_zerogpu.txt $DEPLOY_DIR/requirements.txt

# Copy data if exists
if [ -d "data/chunks" ]; then
    cp -r data $DEPLOY_DIR/
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
---

# IP Assist Lite
Medical AI Assistant for Interventional Pulmonology
EOF

echo "✅ Package ready in $DEPLOY_DIR/"
echo ""
echo "Now in Cursor (connected to HF Space):"
echo "1. Open terminal: Ctrl+\`"
echo "2. Run: cd /home/user/app"
echo "3. Drag files from $DEPLOY_DIR to Cursor file explorer"
```

### Cursor-Specific Features for HF Development

#### 1. AI-Assisted Deployment
Use Cursor's AI to help with deployment:
```
# In Cursor chat (Cmd+K):
"Help me deploy this Gradio app to HF Spaces with ZeroGPU"
```

#### 2. WSL Path Handling
Cursor handles WSL paths automatically:
- WSL path: `/home/rjm/projects/IP_assist_lite`
- Windows sees: `\\wsl$\Ubuntu\home\rjm\projects\IP_assist_lite`

#### 3. Integrated Terminal
- Cursor terminal in WSL: Full Linux commands
- Cursor terminal in HF Space: Direct Space access

### Advantages of Cursor + WSL for HF Spaces

✅ **Native Linux environment** - Same as HF Spaces
✅ **AI code assistance** - Cursor's AI helps with deployment
✅ **Path compatibility** - WSL paths work seamlessly
✅ **Git integration** - Use WSL git directly
✅ **Performance** - WSL2 is fast with Cursor

### Quick Commands for Cursor+WSL

```bash
# In WSL terminal
cd /home/rjm/projects/IP_assist_lite

# Open in Cursor
cursor .

# Connect to HF Space via SSH
ssh hf-ip-assist

# Copy files to HF Space
scp -r data/chunks/chunks.jsonl hf-ip-assist:/home/user/app/data/chunks/

# Sync entire directory
rsync -avz --exclude 'cache' --exclude '__pycache__' \
  ./ hf-ip-assist:/home/user/app/
```

### Troubleshooting Cursor+WSL+HF

#### Issue: SSH connection fails from Cursor
```bash
# Fix in WSL:
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_rsa
chmod 644 ~/.ssh/id_rsa.pub
```

#### Issue: Cursor can't find WSL
1. Ensure WSL extension is installed in Cursor
2. Restart Cursor
3. Open from WSL: `cursor .`

#### Issue: File permissions in HF Space
```bash
# In HF Space terminal (via Cursor):
chmod +x app.py
```

### Pro Workflow: Three-Window Setup

1. **Window 1**: Cursor in WSL (local project)
   ```bash
   cd /home/rjm/projects/IP_assist_lite
   cursor .
   ```

2. **Window 2**: Cursor connected to HF Space
   - Ctrl+Shift+P → "Remote-SSH: Connect"
   - Select HF Space

3. **Window 3**: Browser with HF Space
   - Monitor logs
   - Test the app

### File Sync Script for Cursor

```bash
#!/bin/bash
# sync_to_hf.sh - Quick sync from WSL to HF Space

# Run from WSL while Cursor is connected to HF Space
rsync -avz --progress \
  --exclude '.git' \
  --exclude '__pycache__' \
  --exclude 'cache' \
  --exclude '*.pyc' \
  --exclude '.env' \
  /home/rjm/projects/IP_assist_lite/ \
  hf-ip-assist:/home/user/app/

echo "✅ Files synced to HF Space"
```

## Summary

**Yes, Cursor works perfectly with WSL for HF Spaces!**

Key points:
- Install Remote-SSH extension in Cursor
- Configure SSH in your WSL environment
- Use Cursor's AI to help with deployment
- Leverage WSL's Linux environment (same as HF Spaces)

The combination of Cursor + WSL + HF Spaces gives you:
- AI-powered coding assistance
- Native Linux development
- Direct Space access
- Seamless file management