#!/usr/bin/env python3
"""
Test the TTL cache implementation
"""
import time
import os
from collections import OrderedDict

class TTLCache:
    """TTL cache implementation for query results and statistics."""
    
    def __init__(self, maxsize=256, ttl=600):
        self.maxsize = maxsize
        self.ttl = ttl
        self._data = OrderedDict()
        
    def get(self, key):
        """Get cached value if still valid."""
        if key in self._data:
            value, timestamp = self._data[key]
            if time.time() - timestamp < self.ttl:
                # Move to end (most recently used)
                self._data.move_to_end(key)
                return value
            else:
                # Expired, remove it
                del self._data[key]
        return None
    
    def set(self, key, value):
        """Set cached value with current timestamp."""
        # If at capacity, remove oldest
        if len(self._data) >= self.maxsize:
            self._data.popitem(last=False)
        
        self._data[key] = (value, time.time())
    
    def clear(self):
        """Clear all cached entries."""
        self._data.clear()

def test_cache():
    """Test the TTL cache functionality."""
    print("Testing TTL Cache Implementation")
    print("=" * 50)
    
    # Test 1: Basic get/set
    cache = TTLCache(maxsize=3, ttl=2)
    cache.set("key1", "value1")
    assert cache.get("key1") == "value1"
    print("✅ Test 1: Basic get/set works")
    
    # Test 2: TTL expiration
    time.sleep(2.1)
    assert cache.get("key1") is None
    print("✅ Test 2: TTL expiration works (2 second TTL)")
    
    # Test 3: Max size eviction
    cache = TTLCache(maxsize=2, ttl=10)
    cache.set("key1", "value1")
    cache.set("key2", "value2")
    cache.set("key3", "value3")  # Should evict key1
    assert cache.get("key1") is None
    assert cache.get("key2") == "value2"
    assert cache.get("key3") == "value3"
    print("✅ Test 3: Max size eviction works (maxsize=2)")
    
    # Test 4: LRU ordering
    cache = TTLCache(maxsize=3, ttl=10)
    cache.set("key1", "value1")
    cache.set("key2", "value2")
    cache.set("key3", "value3")
    
    # Access key1 to make it most recently used
    cache.get("key1")
    
    # Add key4, should evict key2 (least recently used)
    cache.set("key4", "value4")
    assert cache.get("key1") == "value1"  # Still there
    assert cache.get("key2") is None      # Evicted
    assert cache.get("key3") == "value3"  # Still there
    assert cache.get("key4") == "value4"  # New one
    print("✅ Test 4: LRU ordering works correctly")
    
    # Test 5: Clear functionality
    cache.clear()
    assert cache.get("key1") is None
    assert cache.get("key3") is None
    print("✅ Test 5: Clear functionality works")
    
    print("\n" + "=" * 50)
    print("All TTL cache tests passed! ✨")
    
    # Demo with environment variables
    print("\n" + "=" * 50)
    print("Testing with environment variables:")
    
    result_ttl = int(os.getenv("RESULT_TTL_SEC", "600"))
    result_max = int(os.getenv("RESULT_CACHE_MAX", "256"))
    
    print(f"Result cache: TTL={result_ttl}s, Max={result_max}")
    
    stats_ttl = int(os.getenv("STATS_TTL_SEC", "900"))
    print(f"Stats cache: TTL={stats_ttl}s")
    
    # Simulate cached query
    query_cache = TTLCache(maxsize=result_max, ttl=result_ttl)
    
    query = "What are contraindications for bronchoscopy?"
    cache_key = f"{query}|rerank=True|k=5"
    
    # First query - miss
    if query_cache.get(cache_key) is None:
        print(f"\n❌ Cache miss for: {query[:30]}...")
        # Simulate processing
        result = {"text": "Contraindications include...", "metadata": {"cached": False}}
        query_cache.set(cache_key, result)
    
    # Second query - hit
    cached = query_cache.get(cache_key)
    if cached:
        print(f"⚡ Cache hit for: {query[:30]}...")
        cached["metadata"]["cached"] = True
        print(f"   Result: {cached['text'][:30]}...")

if __name__ == "__main__":
    test_cache()