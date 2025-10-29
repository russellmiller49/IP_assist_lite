# Terminal Output Tips - Viewing Long Output

## Problem
Terminal output gets cut off at the top when output is longer than your scrollback buffer.

## Solutions

### 1. Redirect Output to a File (Recommended)

```bash
# Run command and save to file
./run_extractions.sh 2>&1 | tee extraction_log.txt

# Then view the file
cat extraction_log.txt
# or
less extraction_log.txt
```

**With timestamps:**
```bash
./run_extractions.sh 2>&1 | tee extraction_log_$(date +%Y%m%d_%H%M%S).txt
```

### 2. Pipe Through `less` or `more`

```bash
# Pause after each screen
./run_extractions.sh 2>&1 | less

# Use arrow keys to scroll, 'q' to quit
```

### 3. Increase Terminal Scrollback Buffer

**For most terminals:**
- **GNOME Terminal**: Edit → Preferences → Scrolling → Unlimited
- **VS Code Terminal**: Settings → Terminal Scrollback → Increase (e.g., 10000 lines)
- **WSL/Windows Terminal**: Settings → Profiles → Scrollback → Increase

### 4. Use `script` Command (Records Everything)

```bash
# Start recording
script extraction_session.txt

# Run your commands
./run_extractions.sh

# Stop recording (type exit)
exit

# View everything
cat extraction_session.txt
```

### 5. Append to Log File

```bash
# Run and append to log
./run_extractions.sh >> extraction.log 2>&1

# View recent output
tail -100 extraction.log

# Follow in real-time while running
./run_extractions.sh 2>&1 | tee -a extraction.log &
tail -f extraction.log
```

### 6. Split Terminal Output

```bash
# Send output to both terminal AND file
./run_extractions.sh 2>&1 | tee extraction.log | less
```

## Quick Commands for Your Workflow

### For Batch Extractions

```bash
# Run and save to timestamped log
./run_extractions.sh 2>&1 | tee logs/extraction_$(date +%Y%m%d_%H%M%S).log

# Or just append to one log
./run_extractions.sh >> logs/extractions.log 2>&1
```

### View Partial Output While Running

```bash
# In one terminal: run extraction
./run_extractions.sh 2>&1 | tee extraction.log

# In another terminal: watch the log
watch -n 1 'tail -20 extraction.log'
```

### Search Output

```bash
# Save output then search
./run_extractions.sh 2>&1 | tee extraction.log
grep -i "error" extraction.log
grep -i "wrote" extraction.log
```

## VS Code Terminal Specific

If using VS Code:
1. Right-click terminal → "Move to Editor"
2. Opens terminal in editor (full scrollback)
3. Or: Settings → `terminal.integrated.scrollback` → set to 10000+

## WSL/Windows Terminal Specific

```bash
# In Windows Terminal settings, set scrollback to:
# "History Size": 10000 or higher
```

## Recommended Setup

Create a `logs/` directory and always log:

```bash
mkdir -p logs

# Modify run_extractions.sh to auto-log:
./run_extractions.sh 2>&1 | tee logs/extraction_$(date +%Y%m%d_%H%M%S).log
```

## Quick Reference

| Method | Command | Use Case |
|--------|---------|----------|
| **Save to file** | `command > output.txt 2>&1` | Save output |
| **Save + display** | `command \| tee output.txt` | See and save |
| **Pause/scroll** | `command \| less` | Scroll through output |
| **Record session** | `script session.txt` | Record everything |
| **Append to log** | `command >> log.txt 2>&1` | Continuous logging |

