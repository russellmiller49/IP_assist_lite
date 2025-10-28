# Workaround for medparse-py311 Issues

You're encountering two problems:
1. ✗ **scikit-learn 1.1.2 won't compile** - Cython build errors
2. ✗ **en_core_sci_lg model 404** - The AI2 URL appears broken

## Immediate Workarounds

### Option 1: Keep sklearn 1.7.2 and Skip the Model (Simplest)

If you don't actually need UMLS enrichment right now:

```bash
conda activate medparse-py311

# Keep sklearn 1.7.2 (already installed)
# Just work without en_core_sci_lg model for now

# Test if it works
python - <<'PY'
import medparse
print("✓ medparse works")
import sklearn
print(f"✓ sklearn: {sklearn.__version__}")
PY
```

### Option 2: Use Your ipassist-py311 Instead (Recommended)

Since you already have `ipassist-py311` set up correctly, just use that:

```bash
conda activate ipassist-py311
python scripts/doctor.py
```

This environment should already have everything configured correctly.

### Option 3: Install Pre-built scikit-learn 1.1.2 Wheel

Try installing a pre-built wheel to avoid compilation:

```bash
conda activate medparse-py311

# First, uninstall the broken version
pip uninstall scikit-learn -y

# Try installing from a specific source with pre-built wheels
pip install --no-build-isolation "scikit-learn==1.1.2"
```

### Option 4: Try Alternative spaCy Model Installation

The AI2 S3 URL might have changed. Try these alternatives:

```bash
conda activate medparse-py311

# Option A: Try with https:// 
pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/en_core_sci_lg-0.5.4.tar.gz

# Option B: Try downloading from GitHub releases
# Check: https://github.com/allenai/scispacy/releases

# Option C: Use a different model that's available
pip install en_core_sci_sm  # Smaller alternative

# Option D: Download manually and install
# 1. Download from: https://github.com/allenai/scispacy
# 2. Or check their docs: https://github.com/allenai/scispacy
```

### Option 5: Recreate medparse-py311 with Proper Versions

Start fresh and avoid the compilation issues:

```bash
# Remove the problematic environment
conda env remove -n medparse-py311

# Create new one with specific Python version that has wheels
conda create -n medparse-py311 python=3.11 -y
conda activate medparse-py311

# Install pre-built packages only (no compilation)
pip install --upgrade pip setuptools wheel
pip install "torch==2.9.0"
pip install "PyMuPDF==1.24.9" "pdfplumber==0.11.7"
pip install "spacy==3.7.4" "scispacy==0.5.4"
pip install "nmslib==2.1.2" "typer>=0.12,<1.0" "tqdm" "rich" "pandas>=2.0" "numpy>=1.26"

# Try to install sklearn from conda-forge (usually has pre-built wheels)
conda install -c conda-forge scikit-learn=1.1.2 -y

# Or install newer version if that doesn't work
pip install scikit-learn==1.3.2  # Later version that might have wheels

# Install medparse
cd /home/rjm/projects/ip_knowledge/medparse/medparse-docling
pip install -e .
```

## My Strong Recommendation

**Just use `ipassist-py311` - it's already working!**

The whole point of having separate environments is to avoid these issues. You don't need to fix `medparse-py311` if `ipassist-py311` works for your needs.

```bash
# Use the working environment
conda activate ipassist-py311

# Verify it works
python scripts/doctor.py

# Use it for your work
python -m medparse.cli --version
```

## Quick Decision Tree

- **Need to use medparse-py311?** → Fix it (Option 5 above)
- **Just need to do CLI work?** → Use ipassist-py311 (recommended)
- **Having pickle warnings?** → Either:
  - Use sklearn 1.7.2 and retrain models later
  - Or use sklearn 1.1.2 runtime (already in ipassist-py311)

## About the Pickle Warnings

If you get sklearn version warnings but things still work, you can:
1. Ignore them for now
2. Or use the environment that has the right version (ipassist-py311)

The pickle warnings won't break your code - they're just compatibility notices.

