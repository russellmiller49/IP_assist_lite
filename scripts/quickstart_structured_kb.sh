#!/usr/bin/env bash
set -euo pipefail

echo "[Structured KB pipeline]"
python -m src.prep.kb_setup
python -m src.prep.kb_extract
python -m src.prep.kb_generate
python -m src.prep.kb_validate
python -m src.index.embed_index
echo "Pipeline complete."
