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
    --no-cache
```

### Using conda run with zotero (Recommended)
```bash
conda run -n medparse-py311 python -m medparse.cli extract-articles \
  "data/Input pdfs/articles/pdf" \
  --out out/articles \
  --config configs/run_article.yaml \
  --profile enriched \
  --no-cache \
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
    --no-cache
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