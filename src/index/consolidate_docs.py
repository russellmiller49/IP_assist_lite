#!/usr/bin/env python3
"""
Consolidate individual JSON documents into a single JSONL file
"""
import json
import glob
from pathlib import Path
import sys

def consolidate_documents(input_dir="data/processed", 
                         output_file="data/processed/documents.jsonl",
                         limit=None):
    """
    Consolidate JSON documents into JSONL format.
    
    Args:
        input_dir: Directory containing JSON files
        output_file: Output JSONL file path
        limit: Optional limit on number of documents
    """
    # Get all JSON files in directory
    input_path = Path(input_dir)
    files = sorted(input_path.glob("*.json"))
    
    if limit:
        files = files[:limit]
    
    if not files:
        print(f"No JSON files found in: {input_dir}")
        return 0
    
    # Read and write documents
    count = 0
    with open(output_file, 'w', encoding='utf-8') as out:
        for filepath in files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    doc = json.load(f)
                    # Map content to text if needed
                    if 'content' in doc and 'text' not in doc:
                        doc['text'] = doc['content']
                    # Also add doc_id if missing
                    if 'id' in doc and 'doc_id' not in doc:
                        doc['doc_id'] = doc['id']
                    # Ensure doc has text field
                    if 'text' in doc or 'content' in doc:
                        out.write(json.dumps(doc, ensure_ascii=False) + '\n')
                        count += 1
            except Exception as e:
                print(f"Error processing {filepath}: {e}")
                continue
    
    print(f"Consolidated {count} documents into {output_file}")
    return count

if __name__ == "__main__":
    # Check command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == "--dev":
            # Development mode: first 5 documents
            consolidate_documents(
                output_file="data/processed/dev_documents.jsonl",
                limit=5
            )
        else:
            # Custom directory provided
            consolidate_documents(input_dir=sys.argv[1])
    else:
        # Default: all documents
        consolidate_documents()