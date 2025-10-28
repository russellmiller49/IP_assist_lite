# Environment Setup Summary

## ✅ What Has Been Completed

### 1. Updated Core Configuration Files
- ✅ `pyproject.toml`: Changed `scikit-learn` from `1.7.2` → `1.1.2` (avoids pickle warnings)
- ✅ `requirements.txt`: Updated to match `scikit-learn==1.1.2`

### 2. Created Essential Scripts

| File | Purpose | Status |
|------|---------|--------|
| `scripts/setup_environments.sh` | Automated setup for all 3 environments | ✅ Ready |
| `scripts/doctor.py` | Health check and diagnostics | ✅ Ready |
| `scripts/env_setup_guide.md` | Comprehensive setup documentation | ✅ Ready |
| `tools/rebuild_vectorizer.py` | Migrate models to newer sklearn | ✅ Ready |
| `QUICK_START.md` | Daily usage quick reference | ✅ Ready |

### 3. Created Documentation

- **QUICK_START.md**: Quick daily usage reference
- **ENVIRONMENT_SETUP_COMPLETE.md**: Detailed setup completion status
- **scripts/env_setup_guide.md**: Step-by-step setup instructions

All scripts verified for Python syntax ✓

---

## 🚀 Next Steps for You

### Step 1: Run the Setup Script (Required)

```bash
cd /home/rjm/projects/IP_assist_lite
bash scripts/setup_environments.sh
```

This will create three conda environments:
- **ipassist-py311** (main CLI environment)
- **medparse-lib-py311** (optional library dev)
- **medparse-api-py311** (FastAPI service)

### Step 2: Add Environment Variables (Required)

Add to `~/.bashrc` or `~/.zshrc`:

```bash
export MEDPARSE_PROFILE=enriched
export MEDPARSE_UMLS_MODEL=en_core_sci_lg
export MEDPARSE_DISABLE_GPU=false
export PYTHONUTF8=1
```

Then reload: `source ~/.bashrc`

### Step 3: Verify Your Setup

```bash
conda activate ipassist-py311
python scripts/doctor.py
```

Look for:
- ✓ medparse imported from your workspace
- ✓ spaCy model loaded
- ✓ sklearn version: 1.1.2

### Step 4: Test the CLI

```bash
conda activate ipassist-py311
cd /home/rjm/projects/IP_assist_lite

python -m medparse.cli extract-articles "data/Input pdfs/articles/pdf" --out out/articles --profile enriched --no-cache --force-deep
```

---

## 📝 Key Changes Made

### scikit-learn Version Strategy

**Problem**: InconsistentVersionWarning when using 1.7.2 to unpickle models trained with 1.1.2

**Solution Implemented**: 
- Pinned to `scikit-learn==1.1.2` in pyproject.toml and requirements.txt
- All three environments will use 1.1.2
- Future migration tool created (`tools/rebuild_vectorizer.py`)

**For Future Upgrade** (if needed):
```bash
# 1. Upgrade sklearn
pip install scikit-learn==1.7.2

# 2. Retrain models
python tools/rebuild_vectorizer.py --corpus-dir training/articles

# 3. Update code to load new models
```

### spaCy Model Installation

**Problem**: `spacy download en_core_sci_lg` returns 404

**Solution**: Always use the AI2 tarball:
```bash
pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/en_core_sci_lg-0.5.4.tar.gz
```

This is now baked into the setup script.

### Environment Isolation

**Why Three Environments?**
- Prevents Typer/Gradio conflicts
- Avoids scikit-learn pickle incompatibilities
- Keeps spaCy model availability stable
- Makes version pinning obvious per codebase

---

## 🔧 Troubleshooting Commands

### Check Current Environment

```bash
python - <<'PY'
import sys, medparse, inspect
print("Python:", sys.executable)
print("medparse:", inspect.getsourcefile(medparse))
PY
```

### If "medparse 1.1.0" Keeps Showing

```bash
conda activate ipassist-py311
python -m pip uninstall -y medparse ip-assist-lite
python -m pip cache purge
cd /home/rjm/projects/IP_assist_lite
pip install -e .
```

### Check Package Conflicts

```bash
pip check
```

### Freeze Requirements for Reproduction

```bash
pip freeze > requirements.freeze.txt
```

---

## 📚 Available Documentation

| Document | Purpose | When to Use |
|----------|---------|-------------|
| `QUICK_START.md` | Daily quick reference | Daily usage |
| `scripts/env_setup_guide.md` | Detailed setup | First-time setup |
| `python scripts/doctor.py` | Health diagnostics | Troubleshooting |
| `tools/rebuild_vectorizer.py` | Model migration | Future sklearn upgrades |
| `ENVIRONMENT_SETUP_COMPLETE.md` | Setup status | Reference |

---

## ✅ Verification Checklist

After running the setup script, verify:

- [ ] All three environments created
  ```bash
  conda env list | grep py311
  ```

- [ ] ipassist-py311 has correct packages
  ```bash
  conda activate ipassist-py311
  python scripts/doctor.py
  ```

- [ ] medparse imports from workspace (not site-packages)
  ```bash
  python - <<'PY'
  import medparse, inspect
  print(inspect.getsourcefile(medparse))
  PY
  ```

- [ ] spaCy model loads correctly
  ```bash
  python - <<'PY'
  import spacy
  nlp = spacy.load("en_core_sci_lg")
  print("✓ Model:", nlp.meta.get("name"))
  PY
  ```

- [ ] scikit-learn is 1.1.2
  ```bash
  python -c "import sklearn; print(sklearn.__version__)"
  ```

---

## 🎯 Ready to Go!

Everything is set up and ready. Just run:

```bash
bash scripts/setup_environments.sh
```

Then follow the verification steps above.

For questions or issues, check:
1. `python scripts/doctor.py` (run diagnostics)
2. `QUICK_START.md` (quick reference)
3. `scripts/env_setup_guide.md` (detailed troubleshooting)

