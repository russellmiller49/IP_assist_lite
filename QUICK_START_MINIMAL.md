# Quick Start: Create Minimal Branch

## One Command Solution

Simply run:

```bash
cd /home/rjm/projects/IP_assist_lite
python3 create_minimal_branch.py
```

The script will:
1. ✅ Detect your current branch
2. ✅ Create a new `{branch}-minimal` branch
3. ✅ Identify and show you large files
4. ✅ Remove non-essential large files (keeps all code!)
5. ✅ Stage and commit changes
6. ✅ Show you the new repository size

## What Happens

- **Your current branch**: Unchanged, all files preserved
- **New minimal branch**: Code intact, large data files removed
- **Other branches**: Completely unaffected

## After Running

Push to GitHub:
```bash
git push origin <branch-name>-minimal
```

Switch back to full branch anytime:
```bash
git checkout <original-branch-name>
```

## Files Removed (Safe to Remove)

- PDFs in `data/` (can re-ingest)
- Processed JSON files (can regenerate)
- Vector embeddings `.npy` (can regenerate)
- Binary `bin/qdrant` (install separately)
- Model files (download when needed)
- Test artifacts and transcripts

## Files Kept (Essential)

- ✅ All Python code (`src/`, `medparse/`, `scripts/`)
- ✅ All configs (`configs/`, `*.yaml`, `*.toml`)
- ✅ All documentation
- ✅ Essential data schemas and templates
- ✅ Test code (just not large test data)

See `MINIMAL_BRANCH_GUIDE.md` for detailed information.
