# Quick Start Guide - IP Assist Lite

## Setup (One-Time)

### Option 1: Automated Setup (Recommended)

```bash
# Run the automated setup script
bash scripts/setup_environments.sh
```

### Option 2: Manual Setup

Follow the detailed guide: `scripts/env_setup_guide.md`

## Daily Usage

### 1. Activate Environment

```bash
conda activate ipassist-py311
```

### 2. Verify Environment

```bash
python scripts/doctor.py
```

Should show:
- ✓ medparse imported from your workspace
- ✓ spaCy model loaded
- ✓ sklearn version 1.1.2

### 3. Run Extraction

```bash
# Single line (recommended)
python -m medparse.cli extract-articles "data/Input pdfs/articles/pdf" --out out/articles --profile enriched --no-cache --force-deep

# Multi-line with -- separator (if needed)
python -m medparse.cli -- extract-articles "data/Input pdfs/articles/pdf" --out out/articles --profile enriched --no-cache --force-deep
```

## Environment Variables

Add to `~/.bashrc` or `~/.zshrc`:

```bash
# For ipassist-py311
export MEDPARSE_PROFILE=enriched
export MEDPARSE_UMLS_MODEL=en_core_sci_lg
export MEDPARSE_DISABLE_GPU=false
export PYTHONUTF8=1
```

## Troubleshooting

### "medparse 1.1.0" prints and exits

```bash
conda activate ipassist-py311
python -m pip uninstall -y medparse ip-assist-lite
python -m pip cache purge
cd /home/rjm/projects/IP_assist_lite
pip install -e .
```

### Check which medparse you're using

```bash
python - <<'PY'
import medparse, inspect
print("Using:", inspect.getsourcefile(medparse) or medparse.__file__)
PY
```

### Verify environment

```bash
python scripts/doctor.py
```

## Available Environments

| Environment | Purpose | Activate with |
|-------------|---------|---------------|
| **ipassist-py311** | Main CLI for IP Assist Lite | `conda activate ipassist-py311` |
| medparse-lib-py311 | Medparse library dev (optional) | `conda activate medparse-lib-py311` |
| medparse-api-py311 | FastAPI service (isolated) | `conda activate medparse-api-py311` |

## For More Help

- Setup details: `scripts/env_setup_guide.md`
- Health checks: `python scripts/doctor.py`
- Rebuild vectorizers: `python tools/rebuild_vectorizer.py`

