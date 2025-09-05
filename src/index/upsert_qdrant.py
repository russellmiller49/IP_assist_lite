"""
Qdrant vector database indexing
Uploads embeddings and metadata for similarity search
"""
import json
import numpy as np
from pathlib import Path
from typing import List, Dict, Any
from tqdm import tqdm

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    CollectionStatus,
    OptimizersConfigDiff,
    CreateCollection
)


class QdrantIndexer:
    """Index embeddings and metadata in Qdrant."""
    
    def __init__(self, host: str = "localhost", port: int = 6333,
                 collection_name: str = "ip_medcpt"):
        """
        Initialize Qdrant client and collection.
        
        Args:
            host: Qdrant host
            port: Qdrant port
            collection_name: Name of the collection
        """
        self.client = QdrantClient(host=host, port=port)
        self.collection_name = collection_name
        
        print(f"Connecting to Qdrant at {host}:{port}")
        
    def create_collection(self, vector_size: int = 768, recreate: bool = False):
        """
        Create or recreate the collection.
        
        Args:
            vector_size: Dimension of vectors
            recreate: Whether to recreate if exists
        """
        # Check if collection exists
        collections = self.client.get_collections().collections
        exists = any(c.name == self.collection_name for c in collections)
        
        if exists:
            if recreate:
                print(f"Deleting existing collection: {self.collection_name}")
                self.client.delete_collection(self.collection_name)
            else:
                print(f"Collection {self.collection_name} already exists")
                return
        
        print(f"Creating collection: {self.collection_name}")
        
        # Create collection with optimized settings
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE
            ),
            optimizers_config=OptimizersConfigDiff(
                indexing_threshold=20000,  # Start indexing after 20k points
                memmap_threshold=50000,    # Use memmap for large collections
            )
        )
        
        print(f"Collection created with vector size {vector_size}")
    
    def index_chunks(self, 
                    embeddings_file: str = "../../data/vectors/medcpt_article_embeddings.npy",
                    metadata_file: str = "../../data/vectors/chunk_metadata.jsonl",
                    chunks_file: str = "../../data/chunks/chunks.jsonl",
                    batch_size: int = 100):
        """
        Index chunks with embeddings and metadata.
        
        Args:
            embeddings_file: Path to numpy embeddings
            metadata_file: Path to chunk metadata
            chunks_file: Path to original chunks with text
            batch_size: Batch size for uploading
        """
        # Load embeddings
        print(f"Loading embeddings from {embeddings_file}")
        embeddings = np.load(embeddings_file)
        vector_size = embeddings.shape[1]
        
        # Create collection
        self.create_collection(vector_size=vector_size, recreate=True)
        
        # Load metadata
        print(f"Loading metadata from {metadata_file}")
        metadata_list = []
        with open(metadata_file, "r") as f:
            for line in f:
                metadata_list.append(json.loads(line))
        
        # Load chunk texts
        print(f"Loading chunk texts from {chunks_file}")
        chunk_texts = {}
        with open(chunks_file, "r") as f:
            for line in f:
                chunk = json.loads(line)
                chunk_texts[chunk["id"]] = chunk["text"]
        
        # Verify counts match
        assert len(embeddings) == len(metadata_list), \
            f"Mismatch: {len(embeddings)} embeddings vs {len(metadata_list)} metadata entries"
        
        print(f"Indexing {len(embeddings)} chunks...")
        
        # Upload in batches
        points = []
        for i in tqdm(range(len(embeddings)), desc="Preparing points"):
            metadata = metadata_list[i]
            
            # Add text back to metadata for retrieval
            if metadata["id"] in chunk_texts:
                metadata["text"] = chunk_texts[metadata["id"]]
            
            # Create point
            point = PointStruct(
                id=i,
                vector=embeddings[i].tolist(),
                payload=metadata
            )
            points.append(point)
            
            # Upload batch
            if len(points) >= batch_size:
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=points
                )
                points = []
        
        # Upload remaining points
        if points:
            self.client.upsert(
                collection_name=self.collection_name,
                points=points
            )
        
        # Wait for indexing to complete
        print("Waiting for indexing to complete...")
        self.client.wait_for_indexing(self.collection_name)
        
        # Get collection info
        collection_info = self.client.get_collection(self.collection_name)
        print(f"\nCollection statistics:")
        print(f"  Points: {collection_info.points_count}")
        print(f"  Vectors: {collection_info.vectors_count}")
        print(f"  Status: {collection_info.status}")
    
    def search(self, query_vector: np.ndarray, limit: int = 10,
              filters: Dict[str, Any] = None) -> List[Dict]:
        """
        Search for similar vectors.
        
        Args:
            query_vector: Query embedding
            limit: Number of results
            filters: Optional filters
            
        Returns:
            List of search results
        """
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector.tolist(),
            limit=limit,
            query_filter=filters,
            with_payload=True,
            with_vectors=False
        )
        
        return [
            {
                "id": hit.id,
                "score": hit.score,
                "payload": hit.payload
            }
            for hit in results
        ]
    
    def search_with_filters(self, query_vector: np.ndarray, 
                           domain: str = None,
                           min_year: int = None,
                           authority_tier: str = None,
                           limit: int = 10) -> List[Dict]:
        """
        Search with metadata filters.
        
        Args:
            query_vector: Query embedding
            domain: Filter by domain
            min_year: Minimum publication year
            authority_tier: Filter by authority tier
            limit: Number of results
            
        Returns:
            Filtered search results
        """
        from qdrant_client.models import Filter, FieldCondition, Range
        
        conditions = []
        
        if domain:
            conditions.append(
                FieldCondition(
                    key="domain",
                    match={"any": [domain]}
                )
            )
        
        if min_year:
            conditions.append(
                FieldCondition(
                    key="year",
                    range=Range(gte=min_year)
                )
            )
        
        if authority_tier:
            conditions.append(
                FieldCondition(
                    key="authority_tier",
                    match={"value": authority_tier}
                )
            )
        
        filter_query = Filter(must=conditions) if conditions else None
        
        return self.search(query_vector, limit=limit, filters=filter_query)
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """Get collection statistics."""
        info = self.client.get_collection(self.collection_name)
        
        return {
            "name": self.collection_name,
            "points_count": info.points_count,
            "vectors_count": info.vectors_count,
            "status": str(info.status),
            "config": {
                "vector_size": info.config.params.vectors.size,
                "distance": str(info.config.params.vectors.distance)
            }
        }
    
    def test_search(self):
        """Test search functionality with a sample query."""
        # Load a random embedding for testing
        embeddings_file = "data/vectors/medcpt_article_embeddings.npy"
        if not Path(embeddings_file).exists():
            print("No embeddings found. Run embedding generation first.")
            return
        
        embeddings = np.load(embeddings_file)
        
        # Use first embedding as query
        query_vector = embeddings[0]
        
        print("\nTesting search with first chunk as query...")
        results = self.search(query_vector, limit=5)
        
        for i, result in enumerate(results, 1):
            print(f"\n{i}. Score: {result['score']:.3f}")
            print(f"   ID: {result['payload'].get('id', 'N/A')}")
            print(f"   Section: {result['payload'].get('section_title', 'N/A')}")
            print(f"   Authority: {result['payload'].get('authority_tier', 'N/A')}")
            print(f"   Year: {result['payload'].get('year', 'N/A')}")
            
            # Show preview of text if available
            text = result['payload'].get('text', '')
            if text:
                preview = text[:150] + "..." if len(text) > 150 else text
                print(f"   Text: {preview}")


def main():
    """Main indexing pipeline."""
    # Check if required files exist
    required_files = [
        "../../data/vectors/medcpt_article_embeddings.npy",
        "../../data/vectors/chunk_metadata.jsonl",
        "../../data/chunks/chunks.jsonl"
    ]
    
    for file_path in required_files:
        if not Path(file_path).exists():
            print(f"Missing required file: {file_path}")
            print("Please run the embedding generation first.")
            return
    
    # Initialize indexer
    indexer = QdrantIndexer()
    
    try:
        # Index all chunks
        indexer.index_chunks()
        
        # Print statistics
        stats = indexer.get_collection_stats()
        print("\nFinal collection statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
        
        # Test search
        indexer.test_search()
        
    except Exception as e:
        print(f"Error during indexing: {e}")
        print("Make sure Qdrant is running (use 'make docker-up')")


if __name__ == "__main__":
    main()