# Environment Setup Complete ✅

## What Was Done

### 1. Updated Dependencies
- **pyproject.toml**: Changed `scikit-learn` from 1.7.2 → 1.1.2 (to avoid pickle warnings)
- **requirements.txt**: Updated to match (scikit-learn==1.1.2)

### 2. Created Setup Scripts

#### `scripts/setup_environments.sh`
- Automated setup for all three environments
- Handles:
  - ipassist-py311 (main CLI)
  - medparse-lib-py311 (library development)
  - medparse-api-py311 (FastAPI service)
- Installs correct versions of all packages
- Sets up spaCy model correctly (using AI2 tarball)
- Verifies installation after setup

#### `scripts/doctor.py`
- Health check script for environments
- Checks:
  - Python version and executable path
  - medparse import source (workspace vs installed)
  - spaCy and en_core_sci_lg model availability
  - scikit-learn version consistency
  - Key package versions
  - Package conflicts (pip check)
  - Environment variables
- Usage: `python scripts/doctor.py`

#### `scripts/env_setup_guide.md`
- Comprehensive documentation
- Step-by-step manual setup instructions
- Troubleshooting section
- GPU setup instructions
- Common issues and fixes

#### `QUICK_START.md`
- Quick reference for daily usage
- One-line commands for common tasks
- Environment switching guide

#### `tools/rebuild_vectorizer.py`
- Utility for retraining sklearn vectorizers under new versions
- For future migration from sklearn 1.1.2 → 1.7.2
- Usage: `python tools/rebuild_vectorizer.py --corpus-dir training/articles`

## Next Steps

### 1. Run the Setup Script

```bash
cd /home/rjm/projects/IP_assist_lite
bash scripts/setup_environments.sh
```

This will:
- Create three conda environments
- Install all dependencies with correct versions
- Install spaCy model from AI2
- Install IP Assist Lite in editable mode
- Verify the installation

### 2. Add Environment Variables

Add to `~/.bashrc` or `~/.zshrc`:

```bash
# IP Assist Lite environment variables
export MEDPARSE_PROFILE=enriched
export MEDPARSE_UMLS_MODEL=en_core_sci_lg
export MEDPARSE_DISABLE_GPU=false
export PYTHONUTF8=1
```

Then reload:
```bash
source ~/.bashrc  # or source ~/.zshrc
```

### 3. Verify Setup

```bash
conda activate ipassist-py311
python scripts/doctor.py
```

Expected output:
```
✓ medparse imported from: /home/rjm/projects/IP_assist_lite/medparse/__init__.py
✓ spaCy model loaded
✓ sklearn version: 1.1.2
```

### 4. Test the CLI

```bash
conda activate ipassist-py311
cd /home/rjm/projects/IP_assist_lite

# Test with a sample PDF
python -m medparse.cli extract-articles "data/Input pdfs/articles/pdf" --out out/articles --profile enriched --no-cache --force-deep
```

## Important Notes

### scikit-learn Version
- **Current**: 1.1.2 (pinned to avoid pickle warnings)
- **Training**: Use 1.1.2 for now
- **Future**: To upgrade to 1.7.2, retrain models using `tools/rebuild_vectorizer.py`

### spaCy Model
- **Never** use `python -m spacy download en_core_sci_lg` (404 error)
- **Always** use: `pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/en_core_sci_lg-0.5.4.tar.gz`

### Typer/Gradio Conflicts
- ipassist-py311: Typer >=0.12,<1.0 (kept separate from Gradio)
- Gradio is in separate deployment (t4_deployment) to avoid conflicts

### Environment Isolation
Three separate environments prevent:
- Typer/Gradio version conflicts
- scikit-learn pickle incompatibilities
- spaCy model availability issues
- Version pin fights

## File Structure

```
IP_assist_lite/
├── scripts/
│   ├── setup_environments.sh      # Automated setup script
│   ├── doctor.py                   # Health check script
│   └── env_setup_guide.md         # Detailed setup guide
├── tools/
│   └── rebuild_vectorizer.py      # Vectorizer migration tool
├── QUICK_START.md                 # Quick reference
├── ENVIRONMENT_SETUP_COMPLETE.md  # This file
├── pyproject.toml                 # Updated (sklearn 1.1.2)
└── requirements.txt                # Updated (sklearn 1.1.2)
```

## Quick Commands

```bash
# Setup (first time)
bash scripts/setup_environments.sh

# Activate environment
conda activate ipassist-py311

# Health check
python scripts/doctor.py

# Run extraction
python -m medparse.cli extract-articles "data/..." --out out/...

# Check current environment
python - <<'PY'
import sys, medparse, inspect
print("Python:", sys.executable)
print("medparse:", inspect.getsourcefile(medparse))
PY

# Troubleshoot (if medparse 1.1.0 keeps showing)
conda activate ipassist-py311
python -m pip uninstall -y medparse ip-assist-lite
python -m pip cache purge
cd /home/rjm/projects/IP_assist_lite && pip install -e .
```

## Reference Documents

- **Quick Start**: `QUICK_START.md`
- **Setup Guide**: `scripts/env_setup_guide.md`
- **Health Check**: `python scripts/doctor.py`
- **Vectorizer Migration**: `tools/rebuild_vectorizer.py`

## Questions?

If you run into issues:
1. Run `python scripts/doctor.py` to diagnose
2. Check `scripts/env_setup_guide.md` for common issues
3. Verify which environment is active: `which python`
4. Check medparse import path: see Quick Commands above

