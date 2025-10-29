# Conda Run Commands

Quick reference for running extractions without activating the environment.

## Textbook Extraction

```bash
cd /home/rjm/projects/IP_assist_lite

# Load environment variables first
set -a
source <(grep -v '^#' .env | grep -v '^$' | sed 's/#.*$//g' | grep '=')
set +a

# Run textbook extraction
conda run -n medparse-py311 python -m medparse.cli extract-textbook \
  "data/Input pdfs/Texbooks" \
  --out out/textbooks \
  --config configs/run_textbook.yaml \
  --profile enriched \
  --no-cache
```

## All Three Extractions

### Articles
```bash
conda run -n medparse-py311 python -m medparse.cli extract-articles \
  "data/Input pdfs/articles/pdf" \
  --out out/articles \
  --config configs/run_article.yaml \
  --profile enriched \
  --no-cache
```

### IFUs
```bash
conda run -n medparse-py311 python -m medparse.cli extract-ifus \
  "data/Input pdfs/IFUs/pdf" \
  --out out/ifus \
  --config configs/run_ifu.yaml \
  --profile enriched \
  --no-cache
```

### Textbooks
```bash
conda run -n medparse-py311 python -m medparse.cli extract-textbook \
  "data/Input pdfs/Texbooks" \
  --out out/textbooks \
  --config configs/run_textbook.yaml \
  --profile enriched \
  --no-cache
```

## Important Notes

**Environment Variables:** You still need to load environment variables before running, or they won't be available inside the `conda run` command:

```bash
# Load env vars
set -a
source <(grep -v '^#' .env | grep -v '^$' | sed 's/#.*$//g' | grep '=')
set +a

# Now conda run will have access to them
conda run -n medparse-py311 env | grep UMLS
```

**Alternative:** Pass variables directly:
```bash
UMLS_API_KEY=$(grep UMLS_API_KEY .env | cut -d '=' -f2) \
QUICKUMLS_PATH=$(grep QUICKUMLS_PATH .env | cut -d '=' -f2) \
conda run -n medparse-py311 python -m medparse.cli extract-textbook ...
```

## Recommended: Use the Script Instead

The `./run_extractions.sh` script handles everything automatically and logs output:

```bash
./run_extractions.sh
```


