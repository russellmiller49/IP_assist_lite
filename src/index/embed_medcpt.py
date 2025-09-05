"""
MedCPT embedding generation for medical text chunks
Uses GPU acceleration with batch optimization
"""
import json
import numpy as np
from pathlib import Path
from typing import List, Dict, Any
from tqdm import tqdm
import torch

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    print("sentence-transformers not installed. Install with: pip install sentence-transformers")
    raise

from emb_batch import get_batch_config, adaptive_batch_size


class MedCPTEmbedder:
    """Generate embeddings using MedCPT models."""
    
    def __init__(self, model_type: str = "article", device: str = None):
        """
        Initialize MedCPT embedder.
        
        Args:
            model_type: "article" for document encoder, "query" for query encoder
            device: Device to use (None for auto-detect)
        """
        self.model_type = model_type
        
        # Select appropriate model
        if model_type == "article":
            model_name = "ncbi/MedCPT-Article-Encoder"
        else:
            model_name = "ncbi/MedCPT-Query-Encoder"
        
        # Auto-detect device if not specified
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        
        print(f"Loading {model_name} on {device}...")
        
        # Initialize model
        self.model = SentenceTransformer(model_name, device=device)
        self.model.max_seq_length = 512
        
        # Get batch configuration
        self.batch_config = get_batch_config()
        self.device = device
        
        print(f"Model loaded successfully on {device}")
    
    def embed_chunks(self, chunks_file: str = "../../data/chunks/chunks.jsonl",
                     output_dir: str = "../../data/vectors") -> tuple:
        """
        Embed all chunks from JSONL file.
        
        Args:
            chunks_file: Path to chunks JSONL file
            output_dir: Directory to save embeddings
            
        Returns:
            Tuple of (embeddings array, rows list)
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Load chunks
        print(f"Loading chunks from {chunks_file}...")
        chunks = []
        with open(chunks_file, "r") as f:
            for line in f:
                chunks.append(json.loads(line))
        
        print(f"Loaded {len(chunks)} chunks")
        
        # Extract texts
        texts = [chunk["text"] for chunk in chunks]
        
        # Generate embeddings
        embeddings = self.embed_batch(texts)
        
        # Save embeddings
        embeddings_file = output_path / f"medcpt_{self.model_type}_embeddings.npy"
        np.save(embeddings_file, embeddings)
        print(f"Saved embeddings to {embeddings_file}")
        
        # Save chunk metadata (without text to save space)
        rows_file = output_path / "chunk_metadata.jsonl"
        with open(rows_file, "w") as f:
            for chunk in chunks:
                # Remove text field for metadata storage
                metadata = {k: v for k, v in chunk.items() if k != "text"}
                f.write(json.dumps(metadata) + "\n")
        print(f"Saved metadata to {rows_file}")
        
        return embeddings, chunks
    
    def embed_batch(self, texts: List[str]) -> np.ndarray:
        """
        Embed a batch of texts with automatic batching.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            Numpy array of embeddings
        """
        batch_size = self.batch_config["batch_size"]
        
        # Try adaptive batch sizing if GPU
        if self.device == "cuda":
            batch_size = adaptive_batch_size(batch_size)
        
        all_embeddings = []
        
        # Process in batches with progress bar
        for i in tqdm(range(0, len(texts), batch_size), desc="Generating embeddings"):
            batch_texts = texts[i:i + batch_size]
            
            try:
                # Generate embeddings
                batch_embeddings = self.model.encode(
                    batch_texts,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                    batch_size=len(batch_texts)  # Use actual batch size
                )
                
                all_embeddings.append(batch_embeddings)
                
                # Clear cache periodically if using GPU
                if self.device == "cuda" and i % (batch_size * 10) == 0:
                    torch.cuda.empty_cache()
                    
            except torch.cuda.OutOfMemoryError:
                print(f"OOM at batch {i}, reducing batch size and retrying...")
                torch.cuda.empty_cache()
                
                # Reduce batch size and retry
                smaller_batch_size = batch_size // 2
                for j in range(0, len(batch_texts), smaller_batch_size):
                    small_batch = batch_texts[j:j + smaller_batch_size]
                    small_embeddings = self.model.encode(
                        small_batch,
                        convert_to_numpy=True,
                        normalize_embeddings=True,
                        show_progress_bar=False
                    )
                    all_embeddings.append(small_embeddings)
        
        # Concatenate all embeddings
        embeddings = np.vstack(all_embeddings)
        
        print(f"Generated embeddings shape: {embeddings.shape}")
        print(f"Embedding dimension: {embeddings.shape[1]}")
        
        return embeddings
    
    def embed_queries(self, queries: List[str]) -> np.ndarray:
        """
        Embed queries (uses query encoder if available).
        
        Args:
            queries: List of query strings
            
        Returns:
            Numpy array of query embeddings
        """
        # For queries, use smaller batch size
        batch_size = min(32, self.batch_config["batch_size"])
        
        embeddings = self.model.encode(
            queries,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=batch_size
        )
        
        return embeddings
    
    def compute_similarity(self, query_embedding: np.ndarray, 
                          doc_embeddings: np.ndarray) -> np.ndarray:
        """
        Compute cosine similarity between query and documents.
        
        Args:
            query_embedding: Query embedding vector
            doc_embeddings: Document embedding matrix
            
        Returns:
            Similarity scores
        """
        # Ensure embeddings are normalized
        query_norm = query_embedding / np.linalg.norm(query_embedding)
        doc_norms = doc_embeddings / np.linalg.norm(doc_embeddings, axis=1, keepdims=True)
        
        # Compute cosine similarity
        similarities = np.dot(doc_norms, query_norm)
        
        return similarities


def main():
    """Main embedding pipeline."""
    # Create article encoder
    article_embedder = MedCPTEmbedder(model_type="article")
    
    # Check if chunks exist
    chunks_file = Path("../../data/chunks/chunks.jsonl")
    if not chunks_file.exists():
        print(f"Chunks file not found at {chunks_file.absolute()}. Run chunking first.")
        return
    
    # Generate embeddings
    embeddings, chunks = article_embedder.embed_chunks()
    
    # Print statistics
    print("\nEmbedding Statistics:")
    print(f"Total chunks embedded: {len(embeddings)}")
    print(f"Embedding dimension: {embeddings.shape[1]}")
    print(f"Memory usage: {embeddings.nbytes / 1e6:.2f} MB")
    
    # Create query encoder for later use
    print("\nInitializing query encoder...")
    query_embedder = MedCPTEmbedder(model_type="query")
    
    # Test with sample query
    test_query = "What are the contraindications for bronchoscopy?"
    query_emb = query_embedder.embed_queries([test_query])[0]
    
    # Find top matches
    similarities = article_embedder.compute_similarity(query_emb, embeddings)
    top_indices = np.argsort(similarities)[::-1][:5]
    
    print(f"\nTop 5 matches for: '{test_query}'")
    for idx in top_indices:
        print(f"  Score: {similarities[idx]:.3f} - Chunk: {chunks[idx]['id']}")


if __name__ == "__main__":
    main()