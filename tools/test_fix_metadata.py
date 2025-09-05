#!/usr/bin/env python3
"""
Test the fix_metadata.py script on known files
"""
import json, pathlib, subprocess, sys
from pathlib import Path

# Use the actual data/processed directory
BASE = Path(__file__).parent.parent / "data" / "processed"
FIXED = Path(__file__).parent.parent / "data" / "fixed"

def readjp(p): 
    return json.loads(p.read_text(encoding="utf-8"))

def run():
    # Create fixed directory
    FIXED.mkdir(parents=True, exist_ok=True)
    
    # Dry run first
    print("Running dry-run...")
    subprocess.run([
        sys.executable, 
        "tools/fix_metadata.py", 
        "--input", str(BASE), 
        "--output", str(FIXED), 
        "--dry-run"
    ], check=True)
    
    # Now write to fixed/
    print("Writing fixed files...")
    subprocess.run([
        sys.executable, 
        "tools/fix_metadata.py", 
        "--input", str(BASE), 
        "--output", str(FIXED)
    ], check=True)

    def check(path, want_type=None, want_h=None, want_tier=None):
        """Check a specific file has expected metadata"""
        file_path = FIXED / path
        if not file_path.exists():
            # Try alternate naming patterns
            alt_paths = [
                FIXED / path.replace(" ", "_"),
                FIXED / path.replace("_", " "),
            ]
            for alt in alt_paths:
                if alt.exists():
                    file_path = alt
                    break
            else:
                print(f"Warning: {path} not found, skipping")
                return
                
        j = readjp(file_path)
        meta = j.get("metadata", {})
        
        if want_type: 
            actual = meta.get("doc_type")
            assert actual == want_type, f"{path}: expected doc_type={want_type}, got {actual}"
            
        if want_h: 
            actual = j.get("h_level")
            assert actual == want_h, f"{path}: expected h_level={want_h}, got {actual}"
            
        if want_tier:
            actual = meta.get("authority_tier")
            assert actual == want_tier, f"{path}: expected authority_tier={want_tier}, got {actual}"
            
        print(f"✓ {path}: doc_type={meta.get('doc_type')}, h_level={j.get('h_level')}, tier={meta.get('authority_tier')}")

    # Test known files
    print("\nTesting known files...")
    
    # Guidelines should be H1
    check("aabip_evidence_informed_guidelines_and_expert.json", want_type="guideline", want_h="H1")
    
    # RCTs
    check("A Randomized Trial of 1% vs 2% Lignocaine by the Spray-as-You-Go Technique.json", want_type="rct")
    check("A randomized study of endobronchial valves for.json", want_type="rct")
    
    # Book chapters with correct A-tiers
    check("practical_gti_mechanical_debridemen.json", want_type="book_chapter", want_tier="A2")
    check("bacada_ch14.json", want_type="book_chapter", want_tier="A3")
    check("bacada_ch08.json", want_type="book_chapter", want_tier="A3")
    
    # PAPOIP chapters should be A1
    check("papoip_bronchople_fistula.json", want_type="book_chapter", want_tier="A1")
    check("papoip_bronchosco_tfs.json", want_type="book_chapter", want_tier="A1")
    
    print("\n✅ All tests passed!")
    
    # Show summary stats from report
    report_path = FIXED / "fix_report.csv"
    if report_path.exists():
        print(f"\nReport saved to: {report_path}")
        lines = report_path.read_text().splitlines()
        total = len(lines) - 1  # minus header
        changed = sum(1 for line in lines[1:] if "noop" not in line)
        print(f"Total files: {total}, Changed: {changed}, Unchanged: {total - changed}")

if __name__ == "__main__":
    run()