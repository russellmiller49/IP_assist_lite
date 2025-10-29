# Always use conda run to ensure proper environment
conda run -n medparse-py311 python -m medparse.cli extract-articles \
    "data/Input pdfs/articles/pdf" \
    --out out/articles \
    --config configs/run_article.yaml \
    --profile enriched \
    --no-cache
Or use the wrapper script I created:
./scripts/run_extraction.sh

conda run -n medparse-py311 python -m medparse.cli extract-ifus \
    "data/Input pdfs/IFUs/pdf" \
    --out out/ifus \
    --config configs/run_ifu.yaml \
    --profile enriched \
    --no-cache