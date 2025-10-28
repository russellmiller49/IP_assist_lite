# Environment Cleanup and Setup

You currently have these environments:
- ✓ `ipassist-py311` - for IP_assist_lite CLI (already exists)
- ✓ `medparse-py311` - older/unclear purpose (needs review)

## Recommended: Three Separate Environments

According to the setup instructions, you should have:

1. **ipassist-py311** ✓ (already exists)
2. **medparse-lib-py311** - for Medparse library development (optional)
3. **medparse-api-py311** - for FastAPI service

**NOT** "medparse-py311" (the one you currently have)

## What to Do with medparse-py311

### Option 1: Keep and Use It

If `medparse-py311` already has the right packages installed, you can keep using it. Check what's in it:

```bash
conda activate medparse-py311
python - <<'PY'
import sys
print("Python:", sys.executable)
import pkg_resources
installed = [p.project_name for p in pkg_resources.working_set]
print("Key packages:")
for pkg in ['medparse', 'typer', 'fastapi', 'spacy', 'sklearn']:
    if pkg in installed:
        try:
            ver = pkg_resources.get_distribution(pkg).version
            print(f"  ✓ {pkg}: {ver}")
        except:
            print(f"  ? {pkg}: (version unknown)")
PY
```

### Option 2: Replace It with the New Environments

If you want to follow the recommended 3-environment setup:

```bash
# Remove the old environment
conda env remove -n medparse-py311

# Then create the new ones
bash scripts/setup_environments.sh
```

This will create:
- **ipassist-py311** (already exists, won't recreate)
- **medparse-lib-py311** (new)
- **medparse-api-py311** (new)

### Option 3: Use It As-Is (Quick Start)

If the existing `medparse-py311` has everything you need, you can just use it. To check if it works:

```bash
conda activate medparse-py311
python - <<'PY'
# Check if medparse imports
try:
    import medparse
    print(f"✓ medparse imported")
except ImportError as e:
    print(f"✗ medparse import failed: {e}")

# Check sklearn version
import sklearn
print(f"scikit-learn version: {sklearn.__version__}")

# Check spaCy model
try:
    import spacy
    nlp = spacy.load("en_core_sci_lg")
    print(f"✓ spaCy model: {nlp.meta.get('name')}")
except Exception as e:
    print(f"✗ spaCy model issue: {e}")
PY
```

## Quick Decision Guide

**Use existing `medparse-py311` if:**
- It already has the packages you need
- You don't need strict version separation
- It's working fine for your workflow

**Replace with new environments if:**
- You're experiencing version conflicts
- You want to follow the recommended 3-environment setup
- You need clearer separation between CLI, library, and API

## My Recommendation

Since you already have `ipassist-py311` working, I'd suggest:

1. **For IP Assist Lite CLI**: Use `ipassist-py311` (already exists)
2. **For Medparse library/API**: You have two options:

   **Quick option**: Use existing `medparse-py311` if it works
   
   **Best practice**: Create `medparse-lib-py311` and `medparse-api-py311` for better isolation

The key question: **Are you having any issues with version conflicts or package dependencies?** 

- **No issues** → Keep using what you have
- **Yes, issues** → Follow the 3-environment setup

## Check Your Current Setup

Run this to see what you have:

```bash
# Check ipassist-py311
conda activate ipassist-py311
python scripts/doctor.py
conda deactivate

# Check medparse-py311
conda activate medparse-py311
python - <<'PY'
import sys
print("Python:", sys.prefix)
try:
    import medparse
    print("✓ medparse available")
except:
    print("✗ medparse not available")
PY
conda deactivate
```

Based on the results, you'll know if you need to rebuild anything.

