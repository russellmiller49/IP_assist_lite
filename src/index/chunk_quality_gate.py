# src/index/chunk_quality_gate.py
"""
Quality gate for chunk validation
Ensures chunking meets minimum quality standards
"""
import csv, sys
from pathlib import Path

def fail(msg): 
    print(f"[chunk-quality] ❌ {msg}", file=sys.stderr)
    sys.exit(1)

def main():
    qa_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/chunks/chunks.qa.csv")
    
    if not qa_path.exists():
        fail(f"QA file not found: {qa_path}")
    
    try:
        with qa_path.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except Exception as e:
        fail(f"Failed to read QA file: {e}")
    
    if not rows:
        fail("No chunks found in QA file")
    
    n = len(rows)
    pct = lambda cond: 100.0 * sum(1 for r in rows if cond(r)) / n
    
    # Calculate metrics
    ends_ok_pct = pct(lambda r: r.get("ends_with_punct", "").lower() in {"true", "1"})
    very_short_pct = pct(lambda r: "very_short" in r.get("issues", ""))
    garble_pct = pct(lambda r: "garbled_pdf" in r.get("issues", ""))
    dupes_pct = pct(lambda r: "duplicate" in r.get("issues", ""))
    
    # Print metrics
    print(f"[chunk-quality] Metrics for {n} chunks:")
    print(f"  ✓ Sentence boundaries: {ends_ok_pct:.1f}%")
    print(f"  ✓ Very short chunks: {very_short_pct:.1f}%")
    print(f"  ✓ Garbled PDF chunks: {garble_pct:.1f}%")
    print(f"  ✓ Duplicate chunks: {dupes_pct:.1f}%")
    
    # Check thresholds
    if ends_ok_pct < 95.0:
        fail(f"Sentence boundary rate {ends_ok_pct:.1f}% < 95% threshold")
    if very_short_pct > 2.0:
        fail(f"Very-short chunks {very_short_pct:.1f}% > 2% threshold")
    if garble_pct > 0.5:
        fail(f"Garbled PDF chunks {garble_pct:.1f}% > 0.5% threshold")
    if dupes_pct > 0.2:
        fail(f"Duplicate chunks {dupes_pct:.1f}% > 0.2% threshold")
    
    print(f"[chunk-quality] ✅ PASS - All quality metrics within acceptable ranges")
    return 0

if __name__ == "__main__":
    sys.exit(main())