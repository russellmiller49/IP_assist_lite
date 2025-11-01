#!/usr/bin/env python3
"""Update golden files from extraction output directory.

This script takes JSON outputs from out/ifus, out/articles, or out/textbooks
and converts them into canonical golden files for testing.
"""
import json
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.golden_utils import (
    canonicalize_payload,
    golden_filename,
    write_pdf_golden,
    CURRENT_GOLDEN_DIR,
)


def update_goldens_from_output(
    output_dir: Path,
    *,
    doc_type: str = "ifu",
    verbose: bool = False,
) -> list[Path]:
    """Update golden files from extraction outputs.
    
    Args:
        output_dir: Directory containing JSON output files (e.g., out/ifus)
        doc_type: Document type prefix (ifu, article, textbook)
        verbose: Print progress messages
        
    Returns:
        List of golden file paths written
    """
    output_dir = Path(output_dir)
    if not output_dir.exists():
        raise FileNotFoundError(f"Output directory not found: {output_dir}")
    
    # Find all JSON files matching the pattern
    pattern = f"{doc_type}_*.json"
    output_files = sorted(output_dir.glob(pattern))
    
    if not output_files:
        print(f"No files matching {pattern} in {output_dir}")
        return []
    
    written = []
    CURRENT_GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    
    for output_file in output_files:
        if verbose:
            print(f"Processing: {output_file.name}")
        
        try:
            # Load the output JSON
            payload = json.loads(output_file.read_text(encoding="utf-8"))
            
            # Extract the PDF filename from source_file
            pdf_name = None
            if "source_file" in payload:
                source_file = payload["source_file"]
                if isinstance(source_file, str):
                    # source_file is a path string, extract just the filename
                    pdf_name = Path(source_file).name
                    if not pdf_name.endswith(".pdf"):
                        # If source_file doesn't have .pdf extension, add it
                        pdf_name = pdf_name + ".pdf"
                elif isinstance(source_file, dict):
                    pdf_name = source_file.get("name") or source_file.get("path", "")
                    if pdf_name and not pdf_name.endswith(".pdf"):
                        pdf_name = pdf_name + ".pdf"
            
            # Fallback: try to infer from output filename
            # Output format: ifu_ion-endoluminal-system.json -> PDF: Ion Endoluminal System.pdf
            if not pdf_name or pdf_name == ".pdf":
                # Try to find matching PDF in input directory
                base_name = output_file.stem
                if base_name.startswith(f"{doc_type}_"):
                    base_name = base_name[len(f"{doc_type}_"):]
                
                # Look for matching PDF in common locations
                search_dirs = [
                    ROOT / "data" / "Input pdfs" / f"{doc_type.upper()}s" / "pdf",
                    ROOT / "data" / "Input pdfs" / f"{doc_type}s" / "pdf",
                    ROOT / "tests" / "data" / "pdfs",
                ]
                
                for search_dir in search_dirs:
                    if search_dir.exists():
                        # Try exact match first
                        for pdf_file in search_dir.glob("*.pdf"):
                            # Check if slugified name matches
                            pdf_slug = pdf_file.stem.lower().replace(" ", "-").replace("_", "-")
                            if pdf_slug == base_name.lower():
                                pdf_name = pdf_file.name
                                break
                        if pdf_name:
                            break
                
                # Last resort: construct from base name
                if not pdf_name:
                    pdf_name = base_name.replace("-", " ").replace("_", " ") + ".pdf"
            
            # Canonicalize the payload (remove non-deterministic fields)
            canonical = canonicalize_payload(payload)
            
            # Write the golden file
            golden_path = write_pdf_golden(pdf_name, canonical, directory=CURRENT_GOLDEN_DIR)
            written.append(golden_path)
            
            if verbose:
                print(f"  ✓ Created: {golden_path.name}")
                
        except Exception as e:
            print(f"  ✗ Error processing {output_file.name}: {e}", file=sys.stderr)
            continue
    
    return written


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Update golden files from extraction outputs")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: auto-detect from doc-type)",
    )
    parser.add_argument(
        "--doc-type",
        choices=["ifu", "article", "textbook"],
        default="ifu",
        help="Document type (default: ifu)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output",
    )
    
    args = parser.parse_args()
    
    # Auto-detect output directory if not specified
    if args.output_dir is None:
        output_dir = ROOT / "out" / f"{args.doc_type}s"
    else:
        output_dir = Path(args.output_dir)
    
    if not output_dir.exists():
        print(f"Error: Output directory does not exist: {output_dir}", file=sys.stderr)
        return 1
    
    written = update_goldens_from_output(
        output_dir,
        doc_type=args.doc_type,
        verbose=args.verbose,
    )
    
    print(f"\n✓ Updated {len(written)} golden file(s)")
    print(f"  Location: {CURRENT_GOLDEN_DIR}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
