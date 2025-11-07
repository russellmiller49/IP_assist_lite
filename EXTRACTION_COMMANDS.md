# Medparse Extraction Commands

## Quick Reference

All commands assume you're in the project root directory: `/home/rjm/projects/IP_assist_lite`
### First run this
UMLS_API_KEY=$(grep UMLS_API_KEY .env | cut -d '=' -f2) \
QUICKUMLS_PATH=$(grep QUICKUMLS_PATH .env | cut -d '=' -f2) \
---

## Articles (Guidelines & Research Papers)

### Using conda run (Recommended)
```bash
conda run -n medparse-py311 python -m medparse.cli extract-articles \
    "data/Input pdfs/articles/pdf" \
    --out out/articles \
    --config configs/run_article.yaml \
    --profile enriched \
    --no-cache \
    --second-pass auto
```

### Using conda run with zotero (Recommended)
```bash
conda run -n medparse-py311 python -m medparse.cli extract-articles \
  "data/Input pdfs/articles/pdf" \
  --out out/articles \
  --config configs/run_article.yaml \
  --profile enriched \
  --no-cache \
  --second-pass auto \
  --zotero-json data/zotero/my_library.json \
  --evidence-policy compact
```

### Using wrapper script
```bash
./scripts/run_extraction.sh
```

### Expected output
- Output directory: `out/articles/`
- Files: `article_*.json`
- UMLS entities: 1000-3000 per document
- File size: 200KB-15MB

---

## IFUs (Instructions for Use / Device Manuals)

### Using conda run (Recommended)
```bash
conda run -n medparse-py311 python -m medparse.cli extract-ifus \
    "data/Input pdfs/IFUs/pdf" \
    --out out/ifus \
    --config configs/run_ifu.yaml \
    --profile enriched \
    --no-cache \
    --second-pass auto
```

### Using wrapper script
```bash
./scripts/run_extraction_ifus.sh
```

### Expected output
- Output directory: `out/ifus/`
- Files: `ifu_*.json`
- Extracts: contraindications, indications, adverse events, device metadata
- File size: 100KB-5MB

---

## Textbooks

### Using conda run
```bash
conda run -n medparse-py311 python -m medparse.cli extract-textbook \
    "data/Input pdfs/textbooks/pdf/YOUR_TEXTBOOK.pdf" \
    --out out/textbooks \
    --config configs/run_textbook.yaml \
    --profile enriched \
    --no-cache
```

### Expected output
- Output directory: `out/textbooks/`
- Files: `textbook_*.json`
- Includes book metadata and chapter structure

---

## Batch Processing Scripts (Alternative)

If you prefer the batch scripts:

### Articles
```bash
conda run -n medparse-py311 python scripts/batch_extract_articles.py
```

### IFUs
```bash
conda run -n medparse-py311 python scripts/batch_extract_ifus.py
```

---

## Common Options

| Option | Description | Default |
|--------|-------------|---------|
| `--out` / `-o` | Output directory | `out/articles` or `out/ifus` |
| `--config` | Path to config YAML | Auto-detected |
| `--profile` | `enriched` or `fast_raw` | `enriched` |
| `--no-cache` | Skip pipeline cache | Off (uses cache) |
| `--force-deep` | Force full extraction | Off |
| `--max-pages N` | Limit pages processed | No limit |
| `--second-pass` | Second-pass remediation stage | `auto` |

---

## Profiles

### enriched (Recommended for production)
- ✅ UMLS entity linking (2000+ entities)
- ✅ Evidence bank deduplication
- ✅ Full validation
- ✅ Recommendation extraction with grades
- ✅ Diagnostic yield extraction
- ⏱️ Slower: ~10-60 seconds per document

### fast_raw
- ❌ No UMLS entities
- ❌ Minimal validation
- ⏱️ Faster: ~2-5 seconds per document
- 📁 Smaller output files (10-50KB)

---

## Second-Pass Remediation

The second-pass stage applies targeted fixes and improvements after initial extraction.

### Modes

- `auto` (default): Runs second-pass when validation issues are detected
- `always`: Always runs second-pass regardless of validation status
- `off`: Disables second-pass remediation

### What Second-Pass Does

Second-pass includes patchers for:

- **Articles/Guidelines**:
  - ATS (diagnostic yield) extraction fixes
  - Section salvage for missing content
  - Guideline backfill
  - Article affiliation extraction

- **IFUs**:
  - Front-matter enrichment (manufacturer, PN, revision, publication date, model)
  - TOC guard + anchor hygiene (drops TOC pages and reseeks anchors safely)
  - Safety density booster for sparse warnings/cautions
  - Indications/intended-use salvage for small leaflets
  - References anchor backfill for trailing bibliographies

### IFU Second-Pass Helpers

- **TOC guard & anchors** – the IFU pipeline runs TOC guard before anchor discovery and records dropped pages in `_metrics.toc_pages_dropped`. Anchors that start on TOC pages are automatically re-searched on the next content page.
- **Front-matter pattern bundle** – regex bundles live in `configs/_shared/ifu_frontmatter.yaml` under `pattern_bundle`. Add vendor-specific patterns there to teach the extractor how to recognize new manufacturers, product names, part numbers, models, revisions, or publication dates.
- **Safety density overrides** – centralized in `configs/_shared/second_pass.yaml` (`second_pass.ifu.safety_density_min`). Defaults are 20 blocks (8 for ≤4-page leaflets) with vendor overrides: Intuitive=20, ERBE=15, Olympus=8. Validator severities follow the same table automatically.
- **Metrics & traceability** – every extraction now emits `second_pass.applied`, `second_pass.reasons`, and `_metrics.second_pass_modifications` so downstream QA can assert which patchers ran.

### Usage Examples

```bash
# Enable second-pass (auto mode - default)
conda run -n medparse-py311 python -m medparse.cli extract-ifus \
    "data/Input pdfs/IFUs/pdf" \
    --out out/ifus \
    --profile enriched \
    --second-pass auto

# Always run second-pass
conda run -n medparse-py311 python -m medparse.cli extract-articles \
    "data/Input pdfs/articles/pdf" \
    --out out/articles \
    --profile enriched \
    --second-pass always

# Disable second-pass
conda run -n medparse-py311 python -m medparse.cli extract-ifus \
    "data/Input pdfs/IFUs/pdf" \
    --out out/ifus \
    --profile enriched \
    --second-pass off
```

---

## Troubleshooting

### "UMLS linking disabled: no scispaCy models found"
**Solution**: You're not using the medparse-py311 environment properly. Use `conda run -n medparse-py311`.

### "TypeError: TyperArgument.make_metavar()"
**Solution**: Check click version. Should be 8.0.x not 8.3.x:
```bash
conda run -n medparse-py311 pip install "click>=8.0.0,<8.1.0"
```

### "medparse 1.1.0" then exits
**Solution**: This was fixed. Update your code and ensure you have the latest cli.py.

### Check installed models
```bash
conda run -n medparse-py311 python -c "import spacy; print(spacy.util.get_installed_models())"
# Should show: ['en_core_web_sm', 'en_core_sci_lg']
```

---

## Verification

Successful extraction shows:
```
[medparse.cli] argv=[...]
INFO Starting extraction: doc_type=article engine=pymupdf profile=enriched
INFO Loaded scispaCy model: en_core_sci_lg (version 0.5.4)
INFO Evidence deduplication: total=X deduplicated=Y bank_size=Z
INFO Completed extraction: duration=Xs chars=Y coverage=1.00
Wrote out/articles/article_*.json
```

---

## Regenerating Golden Files

After running extractions, you may want to update the golden test fixtures to reflect the new outputs.

### Update Goldens from Extraction Outputs

The `scripts/update_goldens_from_outputs.py` script converts extraction outputs into canonical golden files for testing.

#### For IFUs
```bash
python3 scripts/update_goldens_from_outputs.py --doc-type ifu --output-dir out/ifus --verbose
```

#### For Articles
```bash
python3 scripts/update_goldens_from_outputs.py --doc-type article --output-dir out/articles --verbose
```

#### For Textbooks
```bash
python3 scripts/update_goldens_from_outputs.py --doc-type textbook --output-dir out/textbooks --verbose
```

#### Update All Types
```bash
python3 scripts/update_goldens_from_outputs.py --doc-type ifu --verbose
python3 scripts/update_goldens_from_outputs.py --doc-type article --verbose
python3 scripts/update_goldens_from_outputs.py --doc-type textbook --verbose
```

### What the Script Does

1. Reads JSON files from `out/ifus/`, `out/articles/`, or `out/textbooks/`
2. Extracts the PDF filename from the `source_file` field
3. Canonicalizes the payload (removes timestamps, IDs, and non-deterministic fields)
4. Writes golden files to `tests/golden/current/`

### Committing Updated Goldens

After regenerating goldens, review and commit them:

```bash
# Review changes
git status tests/golden/current/

# Add and commit
git add tests/golden/current/
git commit -m "Update golden files from GPU-accelerated extractions

- Regenerated IFU/Article/Textbook goldens from latest outputs
- Updated canonical snapshots with latest extraction results"
```

### Verify Goldens

Test that the updated goldens work correctly:

```bash
pytest tests/integration/test_ifu_ion.py -v
pytest tests/integration/test_ifu_frontmatter_integration.py -v
```

---

## File Locations

```
IP_assist_lite/
├── data/
│   └── Input pdfs/
│       ├── articles/pdf/          ← Article PDFs here
│       ├── IFUs/pdf/              ← IFU PDFs here
│       └── textbooks/pdf/         ← Textbook PDFs here
├── out/
│   ├── articles/                  ← Article JSON outputs
│   ├── ifus/                      ← IFU JSON outputs
│   └── textbooks/                 ← Textbook JSON outputs
├── configs/
│   ├── run_article.yaml           ← Article config
│   ├── run_ifu.yaml               ← IFU config
│   └── run_textbook.yaml          ← Textbook config
└── scripts/
    ├── run_extraction.sh          ← Article wrapper
    └── run_extraction_ifus.sh     ← IFU wrapper
```
