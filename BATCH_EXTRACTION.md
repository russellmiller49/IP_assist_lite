# Batch Extraction Guide

How to run batch extractions for Articles, IFUs, and Textbooks.

## Quick Start

```bash
cd /home/rjm/projects/IP_assist_lite
./run_extractions.sh
```

That's it! The script handles everything.

## What It Does

The `run_extractions.sh` script:
1. Loads environment variables from `.env`
2. Activates `medparse-py311` environment
3. Runs three extraction tasks sequentially
4. Shows progress and results

## Extraction Tasks

### 1. Articles (Guidelines + Research)

```bash
python -m medparse.cli extract-articles \
  "data/Input pdfs/articles/pdf" \
  --out out/articles \
  --config configs/run_article.yaml \
  --profile enriched \
  --no-cache
```

**Output:** `out/articles/`

### 2. IFUs (Instruction for Use)

```bash
python -m medparse.cli extract-ifus \
  "data/Input pdfs/IFUs/pdf" \
  --out out/ifus \
  --config configs/run_ifu.yaml \
  --profile enriched \
  --no-cache
```

**Output:** `out/ifus/`

### 3. Textbooks

```bash
python -m medparse.cli extract-textbook \
  "data/Input pdfs/Texbooks" \
  --out out/textbooks \
  --config configs/run_textbook.yaml \
  --profile enriched \
  --no-cache
```

**Output:** `out/textbooks/`

## Running Individual Tasks

If one task fails, you can run them individually:

```bash
# Activate environment
conda activate medparse-py311

# Load environment variables
source scripts/load_env.sh

# Run specific extraction
cd /home/rjm/projects/IP_assist_lite
python -m medparse.cli extract-articles "data/Input pdfs/articles/pdf" --out out/articles --config configs/run_article.yaml --profile enriched --no-cache
```

## Output Format

Each extraction produces JSON files:
```
out/
├── articles/
│   ├── article_001.json
│   ├── article_002.json
│   └── ...
├── ifus/
│   ├── ifu_001.json
│   ├── ifu_002.json
│   └── ...
└── textbooks/
    ├── textbook_ch01.json
    ├── textbook_ch02.json
    └── ...
```

## Troubleshooting

### Task Fails Mid-Run

The script continues with the next task automatically. Check the logs for the failed task.

### No Output Produced

1. Check input directories exist:
   ```bash
   ls "data/Input pdfs/articles/pdf"
   ls "data/Input pdfs/IFUs/pdf"
   ls "data/Input pdfs/Texbooks"
   ```

2. Verify environment variables are loaded:
   ```bash
   echo $UMLS_API_KEY
   echo $QUICKUMLS_PATH
   ```

3. Check the environment is active:
   ```bash
   conda activate medparse-py311
   which python
   ```

### CLI Shows "medparse 1.1.0"

This means environment variables aren't loaded. Run:
```bash
source scripts/load_env.sh
```

## Configuration

Profiles available:
- `enriched` - Full enrichment with UMLS linking
- `fast_raw` - Basic extraction only

YAML configs in `configs/`:
- `run_article.yaml` - Article extraction
- `run_ifu.yaml` - IFU extraction
- `run_textbook.yaml` - Textbook extraction

## Advanced Usage

### Skip Cache

Already included with `--no-cache` flag.

### Force Deep Extraction

Add `--force-deep` to force full extraction:
```bash
python -m medparse.cli extract-articles ... --force-deep
```

### Limit Pages (Testing)

Use `--max-pages` to limit processing:
```bash
python -m medparse.cli extract-articles ... --max-pages 5
```

## See Also

- Quick Start: `QUICK_START.md`
- Setup Guide: `SETUP_GUIDE.md`
- Project README: `README.md`

