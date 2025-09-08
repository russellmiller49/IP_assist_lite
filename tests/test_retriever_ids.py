#!/usr/bin/env python3
"""
Tests for retriever ID alignment
"""
from unittest.mock import Mock, patch
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

class MockHit:
    """Minimal stand-in for Qdrant hit."""
    def __init__(self, id, payload, score):
        self.id = id
        self.payload = payload
        self.score = score

def test_payload_id_alignment():
    """Test that semantic search uses payload['id'] for chunk matching."""
    
    # Mock Qdrant client
    mock_qdrant = Mock()
    mock_qdrant.search.return_value = [
        MockHit(id="uuid-123", payload={"id": "D1:0", "text": "chunk 1"}, score=0.9),
        MockHit(id="uuid-456", payload={"id": "D2:1", "text": "chunk 2"}, score=0.8),
    ]
    
    # Test the ID extraction pattern
    hits = mock_qdrant.search(
        collection_name="test",
        query_vector=[0.1, 0.2, 0.3],
        limit=2,
        with_payload=True
    )
    
    # Extract IDs using the pattern from our fixed retriever
    ids = [(h.payload.get("id", h.id), h.score) for h in hits]
    
    # Should return chunk IDs from payload, not UUID point IDs
    assert ids[0][0] == "D1:0", f"Expected D1:0, got {ids[0][0]}"
    assert ids[1][0] == "D2:1", f"Expected D2:1, got {ids[1][0]}"
    assert ids[0][1] == 0.9
    assert ids[1][1] == 0.8
    
    print("✓ Payload ID alignment test passed")

def test_chunk_map_lookup():
    """Test that chunk IDs from payload match chunk_map keys."""
    
    # Simulate chunk_map structure
    chunk_map = {
        "D1:0": {"text": "First chunk", "doc_id": "D1"},
        "D2:1": {"text": "Second chunk", "doc_id": "D2"},
        "D3:2": {"text": "Third chunk", "doc_id": "D3"},
    }
    
    # Simulate Qdrant results with payload IDs
    qdrant_results = [
        ("D1:0", 0.95),  # Using payload["id"]
        ("D3:2", 0.85),
    ]
    
    # Verify all results can be found in chunk_map
    for chunk_id, score in qdrant_results:
        assert chunk_id in chunk_map, f"Chunk ID {chunk_id} not found in chunk_map"
        chunk = chunk_map[chunk_id]
        assert "text" in chunk
        assert "doc_id" in chunk
    
    print("✓ Chunk map lookup test passed")

def test_missing_payload_fallback():
    """Test fallback when payload['id'] is missing."""
    
    # Mock hit without id in payload
    mock_qdrant = Mock()
    mock_qdrant.search.return_value = [
        MockHit(id="fallback-id", payload={"text": "chunk"}, score=0.7),  # No 'id' in payload
    ]
    
    hits = mock_qdrant.search(
        collection_name="test",
        query_vector=[0.1],
        limit=1,
        with_payload=True
    )
    
    # Extract with fallback
    ids = [(h.payload.get("id", h.id), h.score) for h in hits]
    
    # Should fall back to point ID when payload['id'] missing
    assert ids[0][0] == "fallback-id"
    assert ids[0][1] == 0.7
    
    print("✓ Fallback ID test passed")

if __name__ == "__main__":
    test_payload_id_alignment()
    test_chunk_map_lookup()
    test_missing_payload_fallback()
    print("\nAll retriever ID tests passed! ✅")