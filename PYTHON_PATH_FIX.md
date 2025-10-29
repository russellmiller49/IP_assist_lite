# Python Path Resolution Fix

## Problem Summary
The medparse CLI was resolving to the wrong installation (docling version) and immediately exiting with just the version number, preventing any PDF extraction from running.

## Root Causes Identified

1. **Conflicting Package Installation**: `medparse-api` from `/home/rjm/projects/ip_knowledge/medparse/medparse-docling` was installed in the environment
2. **String/Boolean Type Issue**: The `_show_version` function was receiving string "False" instead of boolean False from typer, causing `if value:` to evaluate as True

## Fixes Applied

### 1. Removed Conflicting Package
```bash
conda run -n medparse-py311 pip uninstall -y medparse-api
```

### 2. Fixed CLI Version Callback
**File**: `medparse/cli.py`

**Before**:
```python
def _show_version(value: bool) -> None:
    if value:
        typer.echo(f"medparse {__version__}")
        raise typer.Exit()
```

**After**:
```python
def _show_version(value: bool) -> None:
    # Typer sometimes passes string "False" instead of boolean
    if value and str(value).lower() != "false":
        typer.echo(f"medparse {__version__}")
        raise typer.Exit()
```

### 3. Fixed scikit-learn Version Constraint
**File**: `pyproject.toml`
- Changed `scikit-learn==1.1.2` to `scikit-learn>=1.1.2,<1.8` to match installed version 1.7.2

### 4. Reinstalled Package
```bash
conda run -n medparse-py311 pip install --no-deps -e .
```

## Verification

The CLI now:
1. ✅ Resolves to the correct medparse package in `/home/rjm/projects/IP_assist_lite`
2. ✅ Does not exit immediately with version number
3. ✅ Shows debug output: `[medparse.cli] argv=...`
4. ✅ Attempts to run the actual extraction command

## Remaining Issue

There's a TyperArgument compatibility issue that needs separate resolution:
```
TypeError: TyperArgument.make_metavar() takes 1 positional argument but 2 were given
```

This appears to be a version compatibility issue between typer and click, but is separate from the original Python path resolution problem which is now fixed.

## Running Extractions

Until the TyperArgument issue is resolved, use the batch scripts directly:
```bash
conda run -n medparse-py311 python scripts/batch_extract_articles.py
```

Or use the pipeline directly:
```python
from medparse.pipeline.run_extract import run_extract
result = run_extract(pdf_path, config_path, use_cache=False, profile_override="enriched")
```