#!/usr/bin/env python
"""Batch extract articles with evidence bank."""
import sys
from pathlib import Path
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from medparse.pipeline.run_extract import run_extract

# Configuration
pdf_dir = Path("data/Input pdfs/articles/pdf")
output_dir = Path("out/articles_evidence_bank")
config_path = Path("configs/run_article.yaml")
output_dir.mkdir(parents=True, exist_ok=True)

# Find all PDFs
pdfs = sorted(pdf_dir.glob("*.pdf"))
print(f"Found {len(pdfs)} PDFs to extract\n")

# Extract each PDF
for i, pdf_path in enumerate(pdfs, 1):
    print(f"[{i}/{len(pdfs)}] Extracting: {pdf_path.name}")

    result = run_extract(pdf_path, config_path, use_cache=False, profile_override="enriched")

    if result.success and result.document:
        output_file = output_dir / f"{pdf_path.stem}.json"
        with open(output_file, 'w') as f:
            json.dump(result.to_payload(), f, indent=2)

        bank_size = len(result.document.evidence_bank)
        file_size_mb = output_file.stat().st_size / (1024**2)
        print(f"  ✓ Success: {bank_size} evidence items, {file_size_mb:.2f} MB\n")
    else:
        print(f"  ✗ Failed: {result.failure_reason}\n")

print(f"Extraction complete! Output in: {output_dir}")
