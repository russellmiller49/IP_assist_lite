# Creating a Minimal Branch Guide

This guide helps you create a minimal branch (< 100 MB) that retains all code but removes large data files that can be regenerated.

## Quick Start

1. **Make sure you're on the branch you want to create a minimal version of:**
   ```bash
   git branch --show-current
   ```

2. **Run the script:**
   ```bash
   python3 create_minimal_branch.py [branch-name]
   ```
   
   If you don't specify a branch name, it will use `{current-branch}-minimal`

3. **Follow the prompts** - the script will:
   - Show you large files it found
   - List files it plans to remove
   - Ask for confirmation before removing
   - Stage and commit the changes

4. **Push to GitHub:**
   ```bash
   git push origin <branch-name>
   ```

## What Gets Removed

The script removes files that are **not essential** for understanding the codebase but can be regenerated:

### Removed:
- **PDF files** (`data/Input pdfs/*.pdf`, `data/seed/*.pdf`) - Can be re-ingested
- **Processed data** (`data/processed/*.json`) - Can be regenerated via pipeline
- **Vector embeddings** (`data/vectors/*.npy`) - Can be regenerated
- **Chunk files** (`data/chunks/*.jsonl`) - Can be regenerated
- **Binary files** (`bin/qdrant`) - Should be installed separately
- **Model files** (`models/*.joblib`) - Can be downloaded
- **Test artifacts** (`.hypothesis/`, `out/*.json`)
- **Conversation transcripts** (`2025-*.txt`, `Claude_chat_transcripts/`)
- **Large data files** (> 500KB in `data/` that aren't essential)

### Kept:
- ✅ All Python source code (`src/`, `medparse/`, `scripts/`, `tests/`)
- ✅ Configuration files (`configs/`, `*.yaml`, `*.toml`, `*.ini`)
- ✅ Documentation (`documentation/`, `docs/`, `*.md`)
- ✅ Essential data (`data/schema/`, `data/templates/`, `data/fixtures/`)
- ✅ Essential JSON files (`data/ip_coding_billing.json`, `data/ip_templates.json`)
- ✅ Docker configs, Makefiles, requirements files
- ✅ Small test PDFs (if needed for tests)

## Manual Process (Alternative)

If you prefer to do it manually:

1. **Create and switch to new branch:**
   ```bash
   git checkout -b minimal-branch
   ```

2. **Remove large files:**
   ```bash
   # Remove PDFs
   rm -rf "data/Input pdfs"/*.pdf
   rm -rf data/seed/*.pdf
   
   # Remove processed data
   rm -rf data/processed/*.json
   rm -rf data/chunks/*.jsonl
   rm -rf data/vectors/*.npy
   rm -rf data/structured_knowledge/*.json
   rm -rf data/term_index/*.jsonl
   rm -f data/registry.jsonl
   
   # Remove binaries
   rm -f bin/qdrant
   
   # Remove models
   rm -rf models/*.joblib
   
   # Remove test artifacts
   rm -rf .hypothesis
   rm -rf out/*.json
   rm -rf anomaly_reports
   
   # Remove transcripts
   rm -f 2025-*.txt
   rm -rf Claude_chat_transcripts
   rm -rf cursor_exported_coversations
   ```

3. **Stage and commit:**
   ```bash
   git add -A
   git commit -m "Create minimal branch: Remove large non-essential files"
   ```

4. **Push:**
   ```bash
   git push origin minimal-branch
   ```

## Verifying Size

Check the repository size:
```bash
du -sh .
```

Or check specific directories:
```bash
du -sh data/ src/ medparse/ scripts/
```

## Switching Between Branches

- **Switch to minimal branch:**
  ```bash
  git checkout minimal-branch
  ```

- **Switch back to full branch:**
  ```bash
  git checkout main  # or your original branch name
  ```

All your files will be restored when you switch back - nothing is lost!

## Important Notes

1. **Other branches are unaffected** - This only modifies the new minimal branch
2. **Files are preserved** - When you switch branches, all files come back
3. **Code is intact** - All source code, configs, and documentation remain
4. **Data can be regenerated** - Removed files can be recreated via the ingestion pipeline

## Troubleshooting

### Script fails with "Not a git repository"
- Make sure you're in the repository root: `/home/rjm/projects/IP_assist_lite`

### Branch already exists
- The script will ask if you want to delete and recreate it
- Or manually delete: `git branch -D <branch-name>`

### Want to keep specific files
- Edit `create_minimal_branch.py` and add patterns to `KEEP_PATTERNS`
- Or manually restore files after running the script:
  ```bash
  git checkout <original-branch> -- path/to/file
  ```

### Size still too large
- Check what's taking space: `du -sh * | sort -hr`
- Consider removing more test data or large JSON files
- Check for Git LFS files that might need special handling

## Git LFS Files

If you have Git LFS files (`.npy`, `.jsonl`), they're tracked separately. The script removes them from the working directory, but you may need to:

```bash
# Remove LFS files from history (if needed, be careful!)
git lfs untrack "*.npy"
git lfs untrack "*.jsonl"
```

However, for a new branch, simply removing the files from the working directory should be sufficient.
