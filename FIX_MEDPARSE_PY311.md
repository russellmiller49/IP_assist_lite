# Fix Your medparse-py311 Environment

## Issues Found

Your `medparse-py311` environment has:
- ✓ medparse installed
- ✓ medparse-api installed
- ✓ spacy, scispacy installed
- ✓ fastapi installed
- ✗ **spaCy model missing**: `en_core_sci_lg` not installed
- ⚠️ **sklearn version**: 1.7.2 (should be 1.1.2 to avoid pickle warnings)

## Quick Fix

Option 1: Fix the existing environment (Recommended)

```bash
# Activate medparse-py311
conda activate medparse-py311

# Downgrade sklearn to avoid pickle warnings
pip install "scikit-learn==1.1.2"

# Install the spaCy model (this was the 404 error)
pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/en_core_sci_lg-0.5.4.tar.gz

# Verify
python - <<'PY'
import spacy
nlp = spacy.load("en_core_sci_lg")
print("✓ Model loaded:", nlp.meta.get("name"))
import sklearn
print(f"✓ sklearn version: {sklearn.__version__}")
PY
```

Option 2: Create separate environments (Best Practice)

The `medparse-py311` seems to combine both library and API work. The recommended setup has them separate:

```bash
# Keep your existing medparse-py311 as-is for now

# Create new separate environments
bash scripts/setup_environments.sh
```

This will create:
- `medparse-lib-py311` - for library development
- `medparse-api-py311` - for FastAPI service

You can then decide:
- Keep `medparse-py311` for quick work
- Use separate environments for proper isolation
- Remove `medparse-py311` once the new ones are working

## What You Should Do RIGHT NOW

Since you're asking about `medparse-py311`, here's the immediate action:

### If you want to use medparse-py311 for CLI work:

```bash
# Fix the missing model and sklearn version
conda activate medparse-py311
pip install "scikit-learn==1.1.2"
pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/en_core_sci_lg-0.5.4.tar.gz

# Test it
python -m medparse.cli --version
```

### If you want to use the proper 3-environment setup:

Use `ipassist-py311` for CLI work (it's already set up correctly), and only create the medparse environments if you need them:

```bash
# Option A: Don't create them at all if you're only doing CLI work
# Just use ipassist-py311

# Option B: If you need medparse library/API work, run:
bash scripts/setup_environments.sh
```

## Summary of Your Environments

| Environment | Status | What to Do |
|-------------|--------|------------|
| **ipassist-py311** | ✓ Exists | ✅ Use this for IP Assist Lite CLI |
| **medparse-py311** | ⚠️ Needs fixes | Fix sklearn + install spaCy model (see above) |
| medparse-lib-py311 | Not created | Optional - only if doing library dev |
| medparse-api-py311 | Not created | Optional - only if running FastAPI |

## My Recommendation

**For your question "Is there anything I need to do regarding the medparse-py311 environment?"**

**Answer: Yes, fix two things:**

1. **Install the missing spaCy model** (this causes the 404 error):
   ```bash
   pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/en_core_sci_lg-0.5.4.tar.gz
   ```

2. **Downgrade sklearn** to avoid pickle warnings:
   ```bash
   pip install "scikit-learn==1.1.2"
   ```

After these two commands, your `medparse-py311` will work correctly.

### Optional: Create separate environments

If you want to follow best practices and have strict version isolation, create the two new environments:

```bash
# This creates medparse-lib-py311 and medparse-api-py311
bash scripts/setup_environments.sh
```

But this is optional - you can keep using `medparse-py311` after fixing it.

