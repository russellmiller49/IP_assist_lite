# CLI Working Solution

## ✅ Problem Solved

The medparse CLI is now fully functional. The issues were:

1. **Python Path Resolution** - medparse-api from docling was conflicting
2. **Version Callback Bug** - String "False" was being treated as truthy
3. **Typer/Click Compatibility** - Typer 0.9.4 needed Click 8.0.x not 8.3.x

## Fixes Applied

### 1. Removed Conflicting Package
```bash
conda run -n medparse-py311 pip uninstall -y medparse-api
```

### 2. Fixed Version Callback
In `medparse/cli.py`:
```python
def _show_version(value: bool) -> None:
    # Typer sometimes passes string "False" instead of boolean
    if value and str(value).lower() != "false":
        typer.echo(f"medparse {__version__}")
        raise typer.Exit()
```

### 3. Fixed Click Compatibility
```bash
conda run -n medparse-py311 pip install "click>=8.0.0,<8.1.0"
```

### 4. Updated pyproject.toml
Changed `scikit-learn==1.1.2` to `scikit-learn>=1.1.2,<1.8`

## Running the CLI

### Method 1: Using conda run (Recommended)
```bash
conda run -n medparse-py311 python -m medparse.cli extract-articles \
    "data/Input pdfs/articles/pdf" \
    --out out/articles \
    --config configs/run_article.yaml \
    --profile enriched \
    --no-cache
```

### Method 2: Using the wrapper script
```bash
./scripts/run_extraction.sh
```

### Method 3: Direct in activated environment
```bash
# First ensure proper activation
conda activate medparse-py311

# Verify you have the right Python
which python  # Should show /home/rjm/miniconda3/envs/medparse-py311/bin/python

# Run extraction
python -m medparse.cli extract-articles \
    "data/Input pdfs/articles/pdf" \
    --out out/articles \
    --config configs/run_article.yaml \
    --profile enriched \
    --no-cache
```

## UMLS Entity Extraction

For UMLS to work, ensure:
1. Use `conda run -n medparse-py311` or properly activated environment
2. The scispaCy model is installed:
   ```bash
   conda run -n medparse-py311 python -c "import spacy; print(spacy.util.get_installed_models())"
   # Should show: ['en_core_web_sm', 'en_core_sci_lg']
   ```

3. Use the enriched profile:
   ```bash
   --profile enriched
   ```

## Known Issue: Shell Environment

Even if your prompt shows `(medparse-py311)`, the `python` command might still point to base conda Python. This happens when conda isn't properly initialized in the shell.

**Solution**: Always use `conda run -n medparse-py311 python` or the provided scripts.

## Verification

The CLI is working correctly when you see:
```
[medparse.cli] argv=[...]
[INFO] Starting extraction: doc_type=article engine=pymupdf profile=enriched
[INFO] Loaded scispaCy model: en_core_sci_lg (version 0.5.4)
[INFO] Evidence deduplication: total=X deduplicated=Y
[INFO] Completed extraction: duration=Xs chars=Y
Wrote out/articles/article_*.json
```

## Output Files

Successfully extracted files will be in:
- `out/articles/` - Article JSONs with UMLS entities and evidence banks
- File sizes: 200KB-15MB depending on enrichment
- UMLS entities: 1000-3000 per document when working

## Summary

✅ CLI no longer exits with version
✅ Proper error messages displayed
✅ Extraction runs successfully
✅ UMLS works when using proper environment
✅ Evidence bank deduplication active
✅ All quality fixes applied