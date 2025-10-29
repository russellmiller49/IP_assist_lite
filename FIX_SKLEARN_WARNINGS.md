# Fixing sklearn Version Warnings

## Problem

You're seeing warnings like:
```
InconsistentVersionWarning: Trying to unpickle estimator TfidfTransformer from version 1.1.2 when using version 1.7.2
InconsistentVersionWarning: Trying to unpickle estimator TfidfVectorizer from version 1.1.2 when using version 1.7.2
```

## Root Cause

The medparse-docling cache directory contains 2,828+ pickle files that were created with sklearn 1.1.2, but you're now using sklearn 1.7.2.

## Solution: Clear the Cache ✅

The cache files are regenerated automatically, so clearing them is safe:

```bash
cd /home/rjm/projects/ip_knowledge/medparse/medparse-docling
rm -f cache/*.pkl
```

Or use the helper script:
```bash
bash /home/rjm/projects/IP_assist_lite/scripts/clear_cache.sh
```

## What Was Done

1. ✅ **Updated cache_manager.py** - Added warning suppression when loading cached pickle files
2. ✅ **Created clear_cache.sh** - Helper script to safely clear the cache
3. ✅ **Updated pyproject.toml** - Pinned to sklearn 1.7.2
4. ✅ **Updated requirements.txt** - Pinned to sklearn 1.7.2

## After Clearing Cache

1. Run your extractions - cache will regenerate automatically
2. New cache files will use sklearn 1.7.2
3. Warnings will disappear

## Why Not Downgrade to 1.1.2?

- Attempted installation failed with Cython compilation errors
- sklearn 1.7.2 is working fine
- Clearing cache is faster than fighting with compilation

## Quick Fix

```bash
# Clear the cache
cd /home/rjm/projects/ip_knowledge/medparse/medparse-docling
rm -f cache/*.pkl

# Run extraction - cache will regenerate with sklearn 1.7.2
conda run -n medparse-py311 python -m medparse.cli extract-articles ...
```

## Verification

After clearing cache, warnings should be gone. If you still see them, check:
1. Are there other cache directories?
2. Are models loaded from other locations?

The cache_manager.py now suppresses these warnings when loading cached objects.

