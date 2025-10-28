#!/usr/bin/env python
"""Batch extract all documents (articles, IFUs, textbooks) with evidence bank."""
import sys
from pathlib import Path
import json
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from medparse.pipeline.run_extract import run_extract

# Configuration
EXTRACTIONS = [
    {
        "name": "Articles",
        "pdf_dir": Path("data/Input pdfs/articles/pdf"),
        "output_dir": Path("out/articles_evidence_bank"),
        "config": Path("configs/run_article.yaml"),
    },
    {
        "name": "IFUs",
        "pdf_dir": Path("data/Input pdfs/IFUs/pdf"),
        "output_dir": Path("out/ifus_evidence_bank"),
        "config": Path("configs/run_ifu.yaml"),
    },
    {
        "name": "Textbooks",
        "pdf_dir": Path("data/Input pdfs/Textbooks"),
        "output_dir": Path("out/textbooks_evidence_bank"),
        "config": Path("configs/run_textbook.yaml"),
    },
]

def extract_batch(name, pdf_dir, output_dir, config_path):
    """Extract a batch of documents."""
    output_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(pdf_dir.glob("*.pdf"))
    if not pdfs:
        print(f"⚠ No PDFs found in {pdf_dir}\n")
        return 0, 0

    print(f"\n{'='*60}")
    print(f"Extracting {name}")
    print(f"{'='*60}")
    print(f"Found {len(pdfs)} PDFs\n")

    success_count = 0
    fail_count = 0
    total_bank_size = 0

    for i, pdf_path in enumerate(pdfs, 1):
        print(f"[{i}/{len(pdfs)}] {pdf_path.name[:60]}...")

        try:
            result = run_extract(pdf_path, config_path, use_cache=False)

            if result.success and result.document:
                output_file = output_dir / f"{pdf_path.stem}.json"
                with open(output_file, 'w') as f:
                    json.dump(result.to_payload(), f, indent=2)

                bank_size = len(result.document.evidence_bank)
                file_size_mb = output_file.stat().st_size / (1024**2)
                total_bank_size += bank_size
                success_count += 1
                print(f"  ✓ {bank_size} evidence items, {file_size_mb:.2f} MB")
            else:
                fail_count += 1
                print(f"  ✗ Failed: {result.failure_reason}")
        except Exception as e:
            fail_count += 1
            print(f"  ✗ Error: {e}")

    print(f"\n{name} Summary:")
    print(f"  Success: {success_count}/{len(pdfs)}")
    print(f"  Failed: {fail_count}/{len(pdfs)}")
    print(f"  Total evidence items: {total_bank_size}")
    print(f"  Output: {output_dir}")

    return success_count, fail_count

def main():
    """Run all extractions."""
    start_time = datetime.now()
    print(f"Starting batch extraction at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    total_success = 0
    total_fail = 0

    for extraction in EXTRACTIONS:
        success, fail = extract_batch(
            extraction["name"],
            extraction["pdf_dir"],
            extraction["output_dir"],
            extraction["config"],
        )
        total_success += success
        total_fail += fail

    end_time = datetime.now()
    duration = end_time - start_time

    print(f"\n{'='*60}")
    print("OVERALL SUMMARY")
    print(f"{'='*60}")
    print(f"Total Success: {total_success}")
    print(f"Total Failed: {total_fail}")
    print(f"Duration: {duration}")
    print(f"Completed at {end_time.strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()
