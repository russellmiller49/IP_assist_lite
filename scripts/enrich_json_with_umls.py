import json
import os
import sys
from pathlib import Path
from typing import Any, Optional
from tqdm import tqdm

# Ensure we can import our schema
sys.path.append(os.getcwd())
from src.contracts.schema import ExtractionResult, SectionNode, TableData


def load_quickumls() -> Optional[Any]:
    try:
        from quickumls import QuickUMLS  # type: ignore
    except Exception as exc:
        print(f"Warning: QuickUMLS is unavailable ({exc}). UMLS linking will be skipped.")
        print("Tip: Install `leveldb`/QuickUMLS in a Python 3.11 env or set QUICKUMLS_PATH to a built index.")
        return None

    quickumls_path = os.getenv("QUICKUMLS_PATH", "/home/rjm/quickumls_data")
    if not os.path.exists(quickumls_path):
        print(f"Warning: QuickUMLS path not found at {quickumls_path}")
        return None
    
    print(f"Loading QuickUMLS from {quickumls_path}...")
    try:
        return QuickUMLS(quickumls_path, threshold=0.7)
    except Exception as e:
        print(f"Warning: Failed to load QuickUMLS: {e}")
        print("Continuing without medical entity linking...")
        return None

def process_node(node: dict, matcher: Optional[Any]):
    """
    Recursively process a section node and its children.
    """
    if not matcher:
        # Just recurse if no matcher
        for child in node.get("children", []):
            process_node(child, matcher)
        return

    text = f"{node.get('title', '')}\n{node.get('content', '')}"
    if text.strip():
        matches = matcher.match(text, best_match=True, ignore_syntax=False)

        # Convert matches to serializable format
        entities = []
        for match_candidates in matches:
            for candidate in match_candidates:
                entities.append({
                    "cui": candidate["cui"],
                    "term": candidate["term"],
                    "semtypes": list(candidate["semtypes"]),
                    "score": candidate["similarity"]
                })
        
        # Store in metadata
        if "metadata" not in node:
            node["metadata"] = {}
        node["metadata"]["umls_entities"] = entities

    # Recurse
    for child in node.get("children", []):
        process_node(child, matcher)

def process_table(table: dict, matcher: Optional[Any]):
    """
    Process table metadata (caption and flattened description).
    """
    if not matcher:
        return

    text_parts = []
    if table.get("caption"):
        text_parts.append(table["caption"])
    
    if "metadata" in table and "flattened_description" in table["metadata"]:
        text_parts.append(table["metadata"]["flattened_description"])
    
    full_text = "\n".join(text_parts)
    
    if full_text.strip():
        matches = matcher.match(full_text, best_match=True, ignore_syntax=False)
        entities = []
        for match_candidates in matches:
            for candidate in match_candidates:
                entities.append({
                    "cui": candidate["cui"],
                    "term": candidate["term"],
                    "semtypes": list(candidate["semtypes"]),
                    "score": candidate["similarity"]
                })
        
        if "metadata" not in table:
            table["metadata"] = {}
        table["metadata"]["umls_entities"] = entities

def enrich_file(input_path: Path, output_path: Path, matcher: Optional[Any]):
    try:
        with open(input_path, 'r') as f:
            data = json.load(f)
        
        # We assume data matches ExtractionResult schema
        # Process Hierarchy
        for node in data.get("content_hierarchy", []):
            process_node(node, matcher)
            
        # Process Tables
        for table in data.get("tables", []):
            process_table(table, matcher)
            
        # Save
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)
            
    except Exception as e:
        print(f"Failed to enrich {input_path}: {e}")

def main():
    if len(sys.argv) < 3:
        print("Usage: python enrich_json_with_umls.py <input_dir> <output_dir>")
        sys.exit(1)
        
    input_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    
    if not input_dir.exists():
        print(f"Input directory does not exist: {input_dir}")
        sys.exit(1)
        
    output_dir.mkdir(parents=True, exist_ok=True)
    
    matcher = load_quickumls()
    
    files = list(input_dir.glob("*.json"))
    print(f"Found {len(files)} JSON files to enrich.")
    
    for json_file in tqdm(files, desc="Enriching"):
        out_file = output_dir / json_file.name
        enrich_file(json_file, out_file, matcher)
        
    print("Enrichment complete.")

if __name__ == "__main__":
    main()
