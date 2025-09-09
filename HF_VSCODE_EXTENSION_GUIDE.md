# Hugging Face VS Code Extension Guide

## Finding and Installing the HF Extension

### Option 1: Official Hugging Face Extension (If Available)

1. **Open VS Code**
2. **Open Extensions** (Ctrl+Shift+X or Cmd+Shift+X on Mac)
3. **Search for:**
   - "Hugging Face"
   - "HF Spaces"
   - "Hugging Face Spaces"

### Option 2: Remote Development Extensions (Most Common Approach)

Since there may not be an official HF Spaces extension, you'll typically use:

#### **Remote - SSH Extension** (Recommended)
1. **Install Remote - SSH**:
   - Extension ID: `ms-vscode-remote.remote-ssh`
   - Publisher: Microsoft
   - Search: "Remote - SSH"
   - Description: "Open any folder on a remote machine using SSH"

2. **Install Remote Explorer**:
   - Extension ID: `ms-vscode.remote-explorer`
   - Publisher: Microsoft
   - Usually installs automatically with Remote-SSH

### Step-by-Step Installation

#### Installing Remote-SSH Extension:

1. **Open VS Code**

2. **Go to Extensions** (Left sidebar icon or Ctrl+Shift+X)

3. **Search for "Remote SSH"**

4. **Look for the official Microsoft extension:**
   ```
   Remote - SSH
   by Microsoft
   ⭐ 4.5+ stars | 10M+ downloads
   ```

5. **Click Install**

6. **After installation, you'll see:**
   - New icon in Activity Bar (left sidebar)
   - Remote Explorer panel
   - Status bar shows connection status (bottom left)

### Connecting to HF Space via SSH

#### Step 1: Get Your Space's SSH Details

1. **Go to your HF Space**: `https://huggingface.co/spaces/YOUR_USERNAME/ip-assist-lite`
2. **Click Settings** (gear icon)
3. **Scroll to "Development environment"**
4. **Enable "Development mode"** toggle
5. **Copy the SSH command** that appears:
   ```bash
   ssh USERNAME-spaces-ip-assist-lite@hf.space
   ```

#### Step 2: Configure SSH in VS Code

1. **Open Command Palette** (Ctrl+Shift+P or Cmd+Shift+P)

2. **Type and select**: "Remote-SSH: Open SSH Configuration File"

3. **Choose your config file** (usually `~/.ssh/config`)

4. **Add this configuration**:
   ```
   Host hf-ip-assist
       HostName hf.space
       User YOUR_USERNAME-spaces-ip-assist-lite
       Port 22
       IdentityFile ~/.ssh/id_rsa
   ```

   Replace `YOUR_USERNAME` with your actual HF username.

#### Step 3: Set Up SSH Key (If Needed)

If you haven't set up SSH keys with Hugging Face:

1. **Generate SSH key** (if you don't have one):
   ```bash
   ssh-keygen -t rsa -b 4096 -C "your_email@example.com"
   ```

2. **Copy your public key**:
   ```bash
   # On Linux/Mac:
   cat ~/.ssh/id_rsa.pub
   
   # On Windows:
   type %USERPROFILE%\.ssh\id_rsa.pub
   ```

3. **Add to Hugging Face**:
   - Go to https://huggingface.co/settings/keys
   - Click "Add SSH key"
   - Paste your public key
   - Give it a name (e.g., "VS Code Dev")

#### Step 4: Connect to Your Space

1. **Open Command Palette** (Ctrl+Shift+P)

2. **Type**: "Remote-SSH: Connect to Host"

3. **Select**: `hf-ip-assist` (or whatever you named your host)

4. **VS Code will**:
   - Open a new window
   - Connect to your Space
   - Install VS Code Server remotely
   - Show your Space's file system

5. **You're connected!** You should see:
   - Bottom left shows: "SSH: hf-ip-assist"
   - File explorer shows Space files
   - Terminal opens in Space environment

### Alternative: Using HF CLI + VS Code

If SSH doesn't work, you can use the Hugging Face CLI:

1. **Install HF CLI locally**:
   ```bash
   pip install huggingface-hub
   ```

2. **Login to HF**:
   ```bash
   huggingface-cli login
   # Enter your token when prompted
   ```

3. **Clone your Space locally**:
   ```bash
   git clone https://huggingface.co/spaces/YOUR_USERNAME/ip-assist-lite
   cd ip-assist-lite
   ```

4. **Open in VS Code**:
   ```bash
   code .
   ```

5. **Make changes and push**:
   ```bash
   git add .
   git commit -m "Update"
   git push
   ```

### Recommended Extensions for HF Development

Once connected, install these in your remote VS Code:

1. **Python** (ms-python.python)
2. **Pylance** (ms-python.vscode-pylance)
3. **GitLens** (eamodio.gitlens)
4. **Python Docstring Generator** (njpwerner.autodocstring)
5. **Error Lens** (usernamehw.errorlens)

### Quick Connection Commands

After setup, you can quickly connect:

```bash
# Command Palette (Ctrl+Shift+P)
> Remote-SSH: Connect to Host
> Select: hf-ip-assist

# Or use the Remote Explorer
# Click the Remote Explorer icon in sidebar
# Right-click your host > Connect
```

### Troubleshooting Connection Issues

#### "Permission denied (publickey)"
- Ensure SSH key is added to HF account
- Check key path in SSH config is correct
- Try: `ssh-add ~/.ssh/id_rsa`

#### "Connection refused"
- Check Space is running (not paused)
- Verify Development mode is enabled
- Wait 30 seconds after enabling dev mode

#### "Could not establish connection"
- Check your internet connection
- Verify Space URL is correct
- Try refreshing your HF token

### VS Code Settings for HF Spaces

Add to your VS Code settings.json:

```json
{
  "remote.SSH.defaultExtensions": [
    "ms-python.python",
    "ms-python.vscode-pylance"
  ],
  "remote.SSH.connectTimeout": 30,
  "remote.SSH.showLoginTerminal": true,
  "files.watcherExclude": {
    "**/__pycache__/**": true,
    "**/*.pyc": true,
    "**/cache/**": true
  }
}
```

### File Upload via VS Code

Once connected:

1. **Drag and drop** files from your local Explorer to VS Code
2. **Use integrated terminal**:
   ```bash
   # You're now IN your Space
   pwd  # Shows: /home/user/app
   
   # Create directories
   mkdir -p data/chunks data/vectors
   
   # Files auto-sync when saved
   ```

3. **Use VS Code's Upload**:
   - Right-click in Explorer
   - Select "Upload..."
   - Choose files/folders

### Pro Tips

1. **Keep two VS Code windows**:
   - One connected to Space (remote)
   - One with local project
   - Easy to compare and copy

2. **Use `.gitignore` in Space**:
   ```
   __pycache__/
   *.pyc
   cache/
   .env
   ```

3. **Auto-save in Space**:
   - Files > Auto Save > After Delay
   - Space rebuilds automatically

4. **Monitor logs**:
   - Keep HF Space page open
   - Watch "Logs" tab for errors
   - Use VS Code terminal for debugging

---

## Summary

**For HF Spaces, you need:**
1. **Remote - SSH** extension by Microsoft
2. SSH key configured with HF
3. Development mode enabled in Space
4. SSH config entry for easy connection

This gives you full VS Code functionality directly in your Space!