# Cursor WSL Remote-SSH Extension Fix

## The Issue
When Cursor is opened from WSL, some extensions (especially Remote-SSH) may not appear in the marketplace because Cursor is already IN a remote context (WSL).

## Solutions

### Solution 1: Install from Cursor Windows Side First (Recommended)

1. **Close Cursor in WSL**

2. **Open Cursor on Windows** (not from WSL):
   - Windows Start Menu → Cursor
   - Or Windows Terminal: `cursor` (in PowerShell, not WSL)

3. **Install Remote-SSH Extension**:
   - Extensions → Search "Remote-SSH"
   - Install "Remote - SSH" by Microsoft
   - Also install "Remote - SSH: Editing Configuration Files"
   - Install "Remote Explorer"

4. **Now reopen Cursor from WSL**:
   ```bash
   # In WSL terminal
   cd /home/rjm/projects/IP_assist_lite
   cursor .
   ```

5. **The extension should now be available** in the Remote menu

### Solution 2: Use Command Line Installation

In your WSL terminal, install the extension directly:

```bash
# Install Remote-SSH extension via CLI
cursor --install-extension ms-vscode-remote.remote-ssh
cursor --install-extension ms-vscode-remote.remote-ssh-edit
cursor --install-extension ms-vscode.remote-explorer

# Or if 'cursor' command doesn't work, try:
code --install-extension ms-vscode-remote.remote-ssh
```

### Solution 3: Manual VSIX Installation

1. **Download the extension manually**:
   - Go to: https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh
   - Click "Download Extension" (downloads .vsix file)

2. **Install in Cursor**:
   - In Cursor: Ctrl+Shift+P
   - Type: "Extensions: Install from VSIX"
   - Browse to downloaded .vsix file

### Solution 4: Use Native WSL SSH Instead

Since you're already in WSL, you can connect directly without the extension:

```bash
# 1. Enable dev mode on your HF Space first

# 2. Add SSH config in WSL
nano ~/.ssh/config

# Add:
Host hf-space
    HostName hf.space
    User YOUR_HF_USERNAME-spaces-ip-assist-lite
    Port 22
    IdentityFile ~/.ssh/id_rsa

# 3. Test connection from WSL terminal
ssh hf-space

# 4. Use SSHFS to mount the space locally
sudo apt-get install sshfs
mkdir ~/hf-space-mount
sshfs hf-space:/home/user/app ~/hf-space-mount

# 5. Open the mounted directory in Cursor
cursor ~/hf-space-mount
```

### Solution 5: Alternative - Use VS Code Insiders

Since you mentioned VS Code Insiders works:

1. **Use VS Code Insiders for HF Space connection**:
   - It has the Remote-SSH extension working
   - Connect to your HF Space from there

2. **Use Cursor for local WSL development**:
   - Keep using Cursor for your local project
   - Use VS Code Insiders just for the remote connection

### Solution 6: Port Forwarding Approach

Instead of Remote-SSH, use port forwarding:

```bash
# 1. SSH to your space with port forwarding
ssh -L 7860:localhost:7860 YOUR_HF_USERNAME-spaces-ip-assist-lite@hf.space

# 2. Your space is now accessible at http://localhost:7860

# 3. Edit files via direct SSH
ssh YOUR_HF_USERNAME-spaces-ip-assist-lite@hf.space
nano app.py  # or vim, etc.
```

## Recommended Workflow Without Remote-SSH

### Use Two-Terminal Approach:

**Terminal 1 - Local Development (WSL)**:
```bash
cd /home/rjm/projects/IP_assist_lite
cursor .  # Edit locally
```

**Terminal 2 - Direct SSH to HF Space**:
```bash
# Connect to space
ssh YOUR_HF_USERNAME-spaces-ip-assist-lite@hf.space

# Navigate to app directory
cd /home/user/app

# Use rsync to sync files from WSL
# (from WSL terminal, not SSH)
rsync -avz /home/rjm/projects/IP_assist_lite/ YOUR_HF_USERNAME-spaces-ip-assist-lite@hf.space:/home/user/app/
```

### Quick Deployment Script (No Extension Needed)

Create `deploy_direct.sh`:

```bash
#!/bin/bash
# Direct deployment without Remote-SSH extension

HF_USER="YOUR_HF_USERNAME"
SPACE_NAME="ip-assist-lite"
SPACE_HOST="${HF_USER}-spaces-${SPACE_NAME}@hf.space"

echo "🚀 Direct deployment to HF Spaces"

# Prepare files
cp app_hf_spaces_zerogpu.py app_temp.py
cp requirements_zerogpu.txt requirements_temp.txt

# Upload main files
echo "📤 Uploading files..."
scp app_temp.py ${SPACE_HOST}:/home/user/app/app.py
scp requirements_temp.txt ${SPACE_HOST}:/home/user/app/requirements.txt

# Upload data if exists
if [ -d "data/chunks" ]; then
    echo "📊 Uploading data..."
    scp -r data ${SPACE_HOST}:/home/user/app/
fi

# Clean up
rm app_temp.py requirements_temp.txt

echo "✅ Deployment complete!"
echo "🌐 View at: https://huggingface.co/spaces/${HF_USER}/${SPACE_NAME}"
```

## Why This Happens

- **Cursor in WSL mode** is already running in a "remote" context
- **Remote-SSH** extension is designed to work from a "local" context
- **Extension marketplace** filtering may hide incompatible extensions
- **VS Code Insiders** has different extension handling

## Best Practice Recommendation

Since you have VS Code Insiders working with Remote-SSH:

1. **Use VS Code Insiders** for HF Space remote connection
2. **Use Cursor** for local WSL development  
3. **Use rsync/scp** to sync files between them

Or simply:

```bash
# Quick sync command (run from WSL)
alias hf-sync="rsync -avz --exclude '.git' --exclude '__pycache__' ./ YOUR_HF_USERNAME-spaces-ip-assist-lite@hf.space:/home/user/app/"

# Then just run:
hf-sync
```

This way you get Cursor's AI features locally and can still deploy easily!