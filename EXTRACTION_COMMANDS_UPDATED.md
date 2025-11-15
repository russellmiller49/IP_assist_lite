# Updated IFU Extraction Commands with Improvements

## Standard Extraction (Uses All Improvements Automatically)

Your current command will automatically use the improvements we made since they're in the config and code:

```bash
conda run -n medparse-py311 python -m medparse.cli extract-ifus \
    "data/Input pdfs/IFUs/pdf" \
    --out out/ifus \
    --config configs/run_ifu.yaml \
    --profile enriched \
    --no-cache \
    --second-pass auto
```

## Testing Specific Problem IFUs

### 1. Test the Three Problem Files Only

```bash
# Create a test directory with just the problem files
mkdir -p data/test_ifus
cp "data/Input pdfs/IFUs/pdf/ifu_ion-endoluminal-system-instruments-and-accessories-if1000-patient-cart-en-us.pdf" data/test_ifus/
cp "data/Input pdfs/IFUs/pdf/ifu_30180-103-erbe-en-systemcarrier-performance-electrosurgery-generator-mounting-installation.pdf" data/test_ifus/
cp "data/Input pdfs/IFUs/pdf/ifu_alt-pro-instruction-manual.pdf" data/test_ifus/

# Run extraction on test set
conda run -n medparse-py311 python -m medparse.cli extract-ifus \
    data/test_ifus \
    --out out/ifus_test \
    --config configs/run_ifu.yaml \
    --profile enriched \
    --no-cache \
    --second-pass auto
```

### 2. Run with Verbose Output for Debugging

```bash
# Add verbose flag to see what improvements are being applied
conda run -n medparse-py311 python -m medparse.cli extract-ifus \
    "data/Input pdfs/IFUs/pdf" \
    --out out/ifus \
    --config configs/run_ifu.yaml \
    --profile enriched \
    --no-cache \
    --second-pass auto \
    --verbose
```

### 3. Process Single File for Testing

```bash
# Test Intuitive Ion specifically
conda run -n medparse-py311 python -m medparse.cli extract-ifus \
    "data/Input pdfs/IFUs/pdf/ifu_ion-endoluminal-system-instruments-and-accessories-if1000-patient-cart-en-us.pdf" \
    --out out/ifus_single \
    --config configs/run_ifu.yaml \
    --profile enriched \
    --no-cache \
    --second-pass auto
```

## Validation After Extraction

### 1. Run the Test Script

```bash
# After extraction, validate the improvements worked
python test_ifu_improvements.py
```

### 2. Compare Before/After

```bash
# If you have the old extractions, compare them
# Create a comparison script
python compare_extractions.py \
    --old out/ifus_backup \
    --new out/ifus \
    --focus "indications_for_use,model,publication_date,product_name"
```

## Advanced Options

### 1. With Custom Configuration Overrides

If you want to test with different settings:

```bash
# Create a test config with more aggressive settings
cat > configs/run_ifu_test.yaml << 'EOF'
# Base config
extends: run_ifu.yaml

# Override specific settings for testing
ifu:
  toc_guard:
    enabled: true
    density_threshold: 0.55  # More aggressive ToC detection

  anchors:
    indications_for_use:
      start:
        - "indications for use"
        - "indications of use"
        - "clinical indications"  # Added pattern
      stops:
        - "contraindications"
        - "warnings"
        - "precautions"
EOF

# Run with test config
conda run -n medparse-py311 python -m medparse.cli extract-ifus \
    "data/Input pdfs/IFUs/pdf" \
    --out out/ifus_test_config \
    --config configs/run_ifu_test.yaml \
    --profile enriched \
    --no-cache \
    --second-pass auto
```

### 2. Batch Processing with Manufacturer Groups

```bash
# Process by manufacturer for easier validation
for manufacturer in "intuitive" "erbe" "olympus"; do
    echo "Processing $manufacturer IFUs..."

    # Create manufacturer-specific output
    conda run -n medparse-py311 python -m medparse.cli extract-ifus \
        "data/Input pdfs/IFUs/pdf" \
        --out "out/ifus_${manufacturer}" \
        --config configs/run_ifu.yaml \
        --profile enriched \
        --no-cache \
        --second-pass auto \
        --filter "*${manufacturer}*"
done
```

### 3. With JSON Output for Analysis

```bash
# Extract and create analysis report
conda run -n medparse-py311 python -m medparse.cli extract-ifus \
    "data/Input pdfs/IFUs/pdf" \
    --out out/ifus \
    --config configs/run_ifu.yaml \
    --profile enriched \
    --no-cache \
    --second-pass auto \
    --json-summary out/extraction_summary.json
```

## Verification Script

Create a quick verification script to check if improvements are working:

```bash
# Create verification script
cat > verify_improvements.sh << 'EOF'
#!/bin/bash

echo "Checking IFU improvements..."

# Check Intuitive Ion
echo "1. Intuitive Ion:"
grep -A2 '"indications_for_use"' out/ifus/ifu_ion-*.json | head -20
grep '"model"' out/ifus/ifu_ion-*.json
grep '"publication_date"' out/ifus/ifu_ion-*.json

echo ""
echo "2. ERBE System Carrier:"
grep '"toc_guard_dropped_pages"' out/ifus/ifu_*erbe*.json
grep '"publication_date"' out/ifus/ifu_*erbe*.json

echo ""
echo "3. Olympus ALT-Pro:"
grep '"product_name"' out/ifus/ifu_alt-pro*.json
grep '"model"' out/ifus/ifu_alt-pro*.json
EOF

chmod +x verify_improvements.sh
./verify_improvements.sh
```

## Key Points About Your Command

Your existing command is **already correct** and will use all improvements because:

1. **Config Updates**: The `configs/run_ifu.yaml` file has been updated with:
   - Fixed anchor patterns for indications vs intended use
   - Better ToC detection keywords
   - Manufacturer-specific overrides

2. **Code Updates**: The Python files have been enhanced with:
   - Universal ToC detection patterns
   - Better date extraction priorities
   - Product name validation
   - Model extraction improvements

3. **Second-pass Auto**: The `--second-pass auto` flag ensures validation and correction steps run

## Summary

**Your current command doesn't need to change!** Just run:

```bash
conda run -n medparse-py311 python -m medparse.cli extract-ifus \
    "data/Input pdfs/IFUs/pdf" \
    --out out/ifus \
    --config configs/run_ifu.yaml \
    --profile enriched \
    --no-cache \
    --second-pass auto
```

The improvements are already integrated into:
- ✅ `configs/run_ifu.yaml` (configuration improvements)
- ✅ `medparse/ifu/toc_guard.py` (ToC detection)
- ✅ `medparse/manufacturers/*.py` (metadata extraction)
- ✅ `medparse/normalize/ifu_anchors.py` (section handling)

After running, use `python test_ifu_improvements.py` to verify the fixes worked!