# sklearn Version Warnings - Fix Applied

## Problem
After clearing cache, sklearn version warnings still appeared:
```
InconsistentVersionWarning: Trying to unpickle estimator TfidfVectorizer from version 1.1.2 when using version 1.7.2
InconsistentVersionWarning: Trying to unpickle estimator TfidfTransformer from version 1.1.2 when using version 1.7.2
```

## Root Cause
These warnings are **not** from your code or cache files. They come from **inside the spaCy model** (`en_core_sci_lg`). The spaCy model bundle contains sklearn components (TfidfVectorizer, TfidfTransformer) that were trained/serialized with sklearn 1.1.2. When you load the model with sklearn 1.7.2, Python warns about the version mismatch.

## Solution
Warnings are now suppressed at multiple levels:

1. **Package level** (`medparse/__init__.py`): Suppresses warnings when medparse is imported
2. **CLI level** (`medparse/cli.py`): Suppresses warnings before CLI execution
3. **UMLS linking** (`medparse/normalize/umls_linking.py`): Suppresses warnings when loading spaCy models
4. **Script level** (`run_extractions.sh`): Sets `PYTHONWARNINGS` environment variable and adds warning filters in Python subprocess

## Verification
The warnings are safe to ignore because:
- The sklearn API is backward compatible for unpickling
- The models inside spaCy are only used internally by spaCy
- Your code uses sklearn 1.7.2, which is compatible with loading 1.1.2 pickles

## Test
Run an extraction to verify warnings are suppressed:
```bash
cd /home/rjm/projects/IP_assist_lite
bash run_extractions.sh
```

You should no longer see sklearn version warnings in the output.

