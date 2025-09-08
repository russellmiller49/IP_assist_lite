#!/usr/bin/env python3
"""
Tests for chunker v2
"""
import json
import tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from index.chunker_v2 import chunk_document, load_policy, make_token_len_fn

def _mkdoc(text, sec="general", doc_id="D1"): 
    return {"doc_id": doc_id, "section_type": sec, "text": text, "meta": {}}

def test_sentence_boundaries():
    """Test that chunks end on sentence boundaries."""
    # Create minimal policy config
    policy_content = """
version: 2
default:
  target_tokens: 50
  max_tokens: 100
  min_tokens: 10
  overlap_tokens: 10
  ensure_sentence_boundary: true
  drop_patterns: []
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(policy_content)
        policy_path = Path(f.name)
    
    try:
        base, over = load_policy(policy_path)
        tlen = make_token_len_fn()
        doc = _mkdoc("Dr. Smith placed a stent. It was successful. No complications occurred. The patient recovered well.")
        chunks = chunk_document(doc, base, over, tlen)
        
        # Check all chunks end with punctuation
        for chunk in chunks:
            assert "mid_sentence_end" not in chunk["issues"], f"Chunk doesn't end on sentence: {chunk['text']}"
            assert chunk["text"].rstrip().endswith(('.', '!', '?', '"')), f"No sentence ending: {chunk['text']}"
        
        print(f"✓ Sentence boundaries test passed ({len(chunks)} chunks)")
    finally:
        policy_path.unlink()

def test_table_pack():
    """Test table row packing."""
    policy_content = """
version: 2
default:
  target_tokens: 50
  max_tokens: 100
  min_tokens: 10
  overlap_tokens: 0
  drop_patterns: []
section_overrides:
  table_row:
    pack_rows: 3
    target_tokens: 50
    overlap_tokens: 0
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(policy_content)
        policy_path = Path(f.name)
    
    try:
        base, over = load_policy(policy_path)
        tlen = make_token_len_fn()
        
        # Create table with 10 rows
        rows = "\n".join([f"Row {i}: Value {i}" for i in range(10)])
        chunks = chunk_document(_mkdoc(rows, sec="table_row"), base, over, tlen)
        
        # With pack_rows=3 and 10 rows, expect ~4 chunks (3+3+3+1)
        assert len(chunks) >= 3 and len(chunks) <= 4, f"Expected 3-4 chunks, got {len(chunks)}"
        
        # Check first chunk has multiple rows joined
        assert "; " in chunks[0]["text"], "Rows should be joined with '; '"
        
        print(f"✓ Table packing test passed ({len(chunks)} chunks from 10 rows)")
    finally:
        policy_path.unlink()

def test_deduplication():
    """Test that duplicate chunks are removed."""
    policy_content = """
version: 2
default:
  target_tokens: 50
  max_tokens: 100
  min_tokens: 10
  overlap_tokens: 0
  drop_patterns: []
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(policy_content)
        policy_path = Path(f.name)
    
    try:
        base, over = load_policy(policy_path)
        tlen = make_token_len_fn()
        
        # Create document with repeated content
        text = "This is a test sentence. " * 20  # Repeat same sentence
        doc = _mkdoc(text)
        chunks = chunk_document(doc, base, over, tlen)
        
        # Check that duplicates were detected
        unique_texts = set(c["text"] for c in chunks)
        assert len(unique_texts) == len(chunks), "Duplicates should be removed"
        
        print(f"✓ Deduplication test passed ({len(chunks)} unique chunks)")
    finally:
        policy_path.unlink()

def test_garble_detection():
    """Test detection of garbled PDF text."""
    policy_content = """
version: 2
default:
  target_tokens: 50
  max_tokens: 100
  min_tokens: 10
  overlap_tokens: 0
  drop_patterns: []
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(policy_content)
        policy_path = Path(f.name)
    
    try:
        base, over = load_policy(policy_path)
        tlen = make_token_len_fn()
        
        # Create document with garbled text
        garbled = "/C01/C02/C03/C04/C05/C06/C07/C08"
        doc = _mkdoc(garbled)
        chunks = chunk_document(doc, base, over, tlen)
        
        if chunks:
            assert "garbled_pdf" in chunks[0]["issues"], "Should detect garbled PDF text"
            print(f"✓ Garble detection test passed")
        else:
            print(f"✓ Garbled text was filtered out")
    finally:
        policy_path.unlink()

if __name__ == "__main__":
    test_sentence_boundaries()
    test_table_pack()
    test_deduplication()
    test_garble_detection()
    print("\nAll chunker v2 tests passed! ✅")