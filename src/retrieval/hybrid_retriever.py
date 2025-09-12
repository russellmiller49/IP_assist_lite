#!/usr/bin/env python3
"""
Hybrid retrieval system combining:
1. MedCPT semantic search (Qdrant)
2. BM25 sparse retrieval
3. Exact match for CPT codes and aliases
4. Hierarchy-aware ranking with precedence scores
"""

import json
import re
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from dataclasses import dataclass
from collections import defaultdict
import warnings

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, SearchRequest
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer, CrossEncoder

# Import query normalizer
try:
    from .query_normalizer import get_normalizer
except ImportError:
    # Fallback if not available
    def get_normalizer():
        return None


@dataclass
class RetrievalResult:
    """Container for retrieval results with scoring details."""
    chunk_id: str
    text: str
    score: float
    doc_id: str
    section_title: str
    authority_tier: str
    evidence_level: str
    year: int
    doc_type: str
    precedence_score: float
    semantic_score: float
    bm25_score: float
    exact_match_score: float
    has_table: bool = False
    has_contraindication: bool = False
    has_dose_setting: bool = False
    is_emergency: bool = False
    # Citation metadata
    authors: List[str] = None
    journal: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    doi: str = ""
    pmid: str = ""


class HybridRetriever:
    """Hybrid retrieval with hierarchy-aware ranking."""
    
    # Emergency patterns requiring immediate routing
    EMERGENCY_PATTERNS = [
        r'\bmassive\s+hemoptysis\b',
        r'\b(?:bleeding|hemorrhage)\s*>?\s*200\s*ml\b',
        r'\bforeign\s+body\s+(?:aspiration|removal)\b',
        r'\btension\s+pneumothorax\b',
        r'\bairway\s+(?:obstruction|emergency)\b',
        r'\bcardiac\s+arrest\b',
        r'\brespiratory\s+failure\b',
        r'\bemergency\s+(?:airway|intubation)\b'
    ]
    
    # CPT code pattern
    CPT_PATTERN = re.compile(r'\b\d{5}\b')
    
    def __init__(self, 
                 qdrant_host: str = "localhost",
                 qdrant_port: int = 6333,
                 collection_name: str = "ip_medcpt",
                 chunks_file: str = "data/chunks/chunks.jsonl",
                 cpt_index_file: str = "data/term_index/cpt_codes.jsonl",
                 alias_index_file: str = "data/term_index/aliases.jsonl",
                 query_encoder_model: str = "ncbi/MedCPT-Query-Encoder",
                 reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        """
        Initialize hybrid retriever.
        
        Args:
            qdrant_host: Qdrant server host
            qdrant_port: Qdrant server port
            collection_name: Name of Qdrant collection
            chunks_file: Path to chunks JSONL file
            cpt_index_file: Path to CPT codes index
            alias_index_file: Path to aliases index
            query_encoder_model: Model for query encoding
            reranker_model: Cross-encoder for reranking
        """
        # Initialize Qdrant client
        self.qdrant = QdrantClient(host=qdrant_host, port=qdrant_port)
        self.collection_name = collection_name
        
        # Load chunks for BM25 and metadata
        print("Loading chunks...")
        self.chunks = []
        self.chunk_texts = []
        self.chunk_map = {}
        
        with open(chunks_file, 'r', encoding='utf-8') as f:
            for line in f:
                chunk = json.loads(line)
                self.chunks.append(chunk)
                self.chunk_texts.append(chunk['text'])
                # Handle both 'chunk_id' and 'id' fields
                chunk_identifier = chunk.get('chunk_id', chunk.get('id', chunk.get('doc_id')))
                if chunk_identifier:
                    self.chunk_map[chunk_identifier] = chunk
        
        # Initialize BM25
        print("Initializing BM25...")
        tokenized_corpus = [text.lower().split() for text in self.chunk_texts]
        self.bm25 = BM25Okapi(tokenized_corpus)
        
        # Load term indices
        print("Loading term indices...")
        self.cpt_index = self._load_term_index(cpt_index_file)
        self.alias_index = self._load_term_index(alias_index_file)
        
        # Initialize encoders
        print(f"Loading query encoder: {query_encoder_model}")
        self.query_encoder = SentenceTransformer(query_encoder_model)
        
        print(f"Loading reranker: {reranker_model}")
        self.reranker = CrossEncoder(reranker_model)
        
        print("Hybrid retriever initialized")
    
    def _load_term_index(self, index_file: str) -> Dict[str, List[str]]:
        """Load term index from JSONL file."""
        index = defaultdict(list)
        
        if Path(index_file).exists():
            with open(index_file, 'r') as f:
                for line in f:
                    entry = json.loads(line)
                    # Handle both CPT codes and aliases
                    if 'cpt_code' in entry:
                        term = entry['cpt_code']
                        chunk_ids = entry.get('chunks', [])
                    elif 'alias' in entry:
                        term = entry['alias'].lower()
                        chunk_ids = entry.get('chunks', [])
                    else:
                        continue
                    
                    for chunk_id in chunk_ids:
                        index[term].append(chunk_id)
        
        return dict(index)
    
    def detect_emergency(self, query: str) -> bool:
        """Check if query indicates emergency situation."""
        query_lower = query.lower()
        for pattern in self.EMERGENCY_PATTERNS:
            if re.search(pattern, query_lower):
                return True
        return False
    
    def calculate_precedence(self, chunk: Dict[str, Any], current_year: int = 2024) -> float:
        """
        Calculate precedence score based on authority, evidence, and recency.
        
        Modified formula to strongly prioritize textbooks (A1-A3) over articles (A4):
        - For A1-A3: Precedence = 0.6*authority + 0.25*recency + 0.15*evidence
        - For A4: Precedence = 0.4*recency + 0.35*evidence + 0.25*authority
        """
        # Authority weights - EXTREME differentiation to ensure A1 dominance
        # A1 (PAPOIP 2025) = 1.0, A2 (Practical Guide) = 0.85, A3 (BACADA) = 0.7, A4 (Articles) = 0.1
        authority_weights = {'A1': 1.0, 'A2': 0.85, 'A3': 0.7, 'A4': 0.1}
        authority_tier = chunk.get('authority_tier', 'A4')
        authority_score = authority_weights.get(authority_tier, 0.1)
        
        # Evidence weights (H1=1.0, H2=0.75, H3=0.5, H4=0.25)
        evidence_weights = {'H1': 1.0, 'H2': 0.75, 'H3': 0.5, 'H4': 0.25}
        evidence_score = evidence_weights.get(chunk.get('evidence_level', 'H3'), 0.5)
        
        # Recency with domain-specific half-life
        year = chunk.get('year', current_year - 5)
        years_old = max(0, current_year - year)
        
        # Domain-specific half-lives
        domain = chunk.get('domain', ['clinical'])
        if isinstance(domain, list):
            domain = domain[0] if domain else 'clinical'
        
        half_lives = {
            'coding_billing': 3,
            'technology_navigation': 4,
            'ablation': 5,
            'clinical': 6
        }
        half_life = half_lives.get(domain, 6)
        
        # Exponential decay
        recency_score = 0.5 ** (years_old / half_life)
        
        # A1 floor: maintain minimum 70% recency weight
        if chunk.get('authority_tier') == 'A1':
            recency_score = max(0.7, recency_score)
        
        # Calculate precedence with different weights for textbooks vs articles
        if authority_tier == 'A1':
            # A1 (PAPOIP 2025): Maximum authority weight
            precedence = (0.7 * authority_score +
                         0.2 * recency_score + 
                         0.1 * evidence_score)
        elif authority_tier in ['A2', 'A3']:
            # A2/A3 Textbooks: Strong authority weight
            precedence = (0.6 * authority_score +
                         0.25 * recency_score + 
                         0.15 * evidence_score)
        else:
            # A4 Articles: Minimal authority weight
            precedence = (0.3 * recency_score + 
                         0.3 * evidence_score + 
                         0.4 * authority_score)  # Still 0.4 * 0.1 = 0.04 contribution
        
        return precedence
    
    def semantic_search(self, query_embedding: np.ndarray, top_k: int = 20,
                       filters: Optional[Dict] = None) -> List[Tuple[str, float]]:
        """
        Perform semantic search using Qdrant.
        
        Returns list of (chunk_id, score) tuples.
        """
        search_params = {
            "vector": query_embedding.tolist(),
            "limit": top_k
        }
        
        # Add filters if provided
        if filters:
            filter_conditions = []
            
            if 'authority_tier' in filters:
                filter_conditions.append(
                    FieldCondition(
                        key="authority_tier",
                        match=MatchValue(value=filters['authority_tier'])
                    )
                )
            
            if 'has_table' in filters:
                filter_conditions.append(
                    FieldCondition(
                        key="has_table",
                        match=MatchValue(value=filters['has_table'])
                    )
                )
            
            if filter_conditions:
                search_params['filter'] = Filter(must=filter_conditions)
        
        # Search Qdrant
        results = self.qdrant.search(
            collection_name=self.collection_name,
            query_vector=search_params["vector"],
            limit=search_params["limit"],
            query_filter=search_params.get("filter", None),
            with_payload=True  # Ensure we get payload
        )
        
        # Use payload["chunk_id"] or "id" to match chunk_map (canonical ID handling)
        return [(hit.payload.get("chunk_id", hit.payload.get("id", hit.id)), hit.score) for hit in results]
    
    def bm25_search(self, query: str, top_k: int = 20) -> List[Tuple[str, float]]:
        """
        Perform BM25 sparse retrieval.
        
        Returns list of (chunk_id, score) tuples.
        """
        tokenized_query = query.lower().split()
        scores = self.bm25.get_scores(tokenized_query)
        
        # Get top-k indices
        top_indices = np.argsort(scores)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                chunk_id = self.chunks[idx].get('chunk_id', self.chunks[idx].get('id', self.chunks[idx].get('doc_id')))
                results.append((chunk_id, float(scores[idx])))
        
        return results
    
    def exact_match_search(self, query: str) -> List[Tuple[str, float]]:
        """
        Search for exact matches of CPT codes and aliases.
        
        Returns list of (chunk_id, score) tuples.
        """
        results = []
        query_lower = query.lower()
        
        # Check for CPT codes in query
        cpt_codes = self.CPT_PATTERN.findall(query)
        for code in cpt_codes:
            if code in self.cpt_index:
                for chunk_id in self.cpt_index[code]:
                    results.append((chunk_id, 1.0))  # Perfect match
        
        # Check for aliases
        for term, chunk_ids in self.alias_index.items():
            if term in query_lower:
                for chunk_id in chunk_ids:
                    results.append((chunk_id, 0.8))  # High score for alias match
        
        return results
    
    def retrieve(self, query: str, top_k: int = 10, 
                use_reranker: bool = True,
                filters: Optional[Dict] = None) -> List[RetrievalResult]:
        """
        Perform hybrid retrieval with reranking.
        
        Args:
            query: Search query
            top_k: Number of results to return
            use_reranker: Whether to use cross-encoder reranking
            filters: Optional filters for semantic search
            
        Returns:
            List of RetrievalResult objects sorted by final score
        """
        # Normalize query to fix typos and expand abbreviations
        normalizer = get_normalizer()
        normalized_query = query
        if normalizer:
            try:
                normalized_query = normalizer.normalize(query)
                if normalized_query != query:
                    print(f"Query normalized: '{query}' -> '{normalized_query}'")
            except Exception as e:
                print(f"Query normalization failed: {e}")
                normalized_query = query
        
        # Check for emergency
        is_emergency = self.detect_emergency(normalized_query)
        if is_emergency:
            print("⚠️ EMERGENCY DETECTED - Prioritizing urgent content")
        
        # 1. Encode normalized query
        query_embedding = self.query_encoder.encode(normalized_query, convert_to_numpy=True)
        
        # 2. Get candidates from each method - retrieve more to ensure we get both textbooks and articles
        semantic_results = self.semantic_search(query_embedding, top_k=top_k*8, filters=filters)  # Increased from *5
        # Use both normalized and original query for BM25 to maximize recall
        bm25_norm = self.bm25_search(normalized_query, top_k=top_k*5)
        bm25_orig = self.bm25_search(query, top_k=top_k*2) if normalized_query != query else []
        # Combine BM25 results
        bm25_results = bm25_norm + bm25_orig
        exact_results = self.exact_match_search(normalized_query)
        
        # 3. Combine and score candidates
        candidate_scores = defaultdict(lambda: {
            'semantic': 0.0,
            'bm25': 0.0,
            'exact': 0.0
        })
        
        # Normalize and store scores
        for chunk_id, score in semantic_results:
            candidate_scores[chunk_id]['semantic'] = score
        
        if bm25_results:
            max_bm25 = max(score for _, score in bm25_results)
            for chunk_id, score in bm25_results:
                candidate_scores[chunk_id]['bm25'] = score / max_bm25 if max_bm25 > 0 else 0
        
        for chunk_id, score in exact_results:
            candidate_scores[chunk_id]['exact'] = score
        
        # 4. Calculate final scores
        results = []
        for chunk_id, scores in candidate_scores.items():
            if chunk_id not in self.chunk_map:
                continue
            
            chunk = self.chunk_map[chunk_id]
            
            # Calculate precedence
            precedence = self.calculate_precedence(chunk)
            
            # Get section bonus
            section_bonus = 0.1 if any(term in chunk.get('section_title', '').lower() 
                                      for term in query.lower().split()) else 0
            
            # Get entity bonus
            entity_bonus = 0.1 if scores['exact'] > 0 else 0
            
            # Calculate final score
            # Give much more weight to precedence to prioritize textbooks
            if is_emergency:
                final_score = (0.7 * precedence +
                             0.20 * scores['semantic'] +
                             0.05 * scores['bm25'] +
                             0.025 * section_bonus +
                             0.025 * entity_bonus)
            else:
                # Balanced scoring to allow articles to compete
                final_score = (0.45 * precedence +  # Reduced from 0.65
                             0.35 * scores['semantic'] +  # Increased from 0.25
                             0.10 * scores['bm25'] +  # Increased from 0.05
                             0.05 * section_bonus +  # Increased from 0.025
                             0.05 * entity_bonus)  # Increased from 0.025
            
            # Boost for high-value content
            if chunk.get('has_contraindication') and 'contraindication' in query.lower():
                final_score *= 1.2
            if chunk.get('has_table') and any(term in query.lower() for term in ['table', 'cpt', 'code']):
                final_score *= 1.15
            if chunk.get('has_dose_setting') and any(term in query.lower() for term in ['dose', 'setting', 'energy']):
                final_score *= 1.15
            
            # Minimal boost for textbook sources to ensure articles compete
            if chunk.get('authority_tier') == 'A1':
                final_score *= 1.1  # Only 10% boost for A1 (PAPOIP 2025)
            elif chunk.get('authority_tier') in ['A2', 'A3']:
                final_score *= 1.05  # Only 5% boost for A2/A3 textbooks
            
            result = RetrievalResult(
                chunk_id=chunk_id,
                text=chunk['text'],
                score=final_score,
                doc_id=chunk.get('doc_id', ''),
                section_title=chunk.get('section_title', ''),
                authority_tier=chunk.get('authority_tier', 'A4'),
                evidence_level=chunk.get('evidence_level', 'H3'),
                year=chunk.get('year', 2024),
                doc_type=chunk.get('doc_type', 'journal_article'),
                precedence_score=precedence,
                semantic_score=scores['semantic'],
                bm25_score=scores['bm25'],
                exact_match_score=scores['exact'],
                has_table=chunk.get('has_table', False),
                has_contraindication=chunk.get('has_contraindication', False),
                has_dose_setting=chunk.get('has_dose_setting', False),
                is_emergency=is_emergency,
                # Add citation metadata
                authors=chunk.get('authors', []),
                journal=chunk.get('journal', ''),
                volume=chunk.get('volume', ''),
                issue=chunk.get('issue', ''),
                pages=chunk.get('pages', ''),
                doi=chunk.get('doi', ''),
                pmid=chunk.get('pmid', '')
            )
            results.append(result)
        
        # 5. Rerank if requested
        if use_reranker and len(results) > 0:
            # Prepare pairs for reranking
            pairs = [[query, r.text] for r in results[:top_k*3]]  # Rerank top candidates
            
            # Get reranker scores
            rerank_scores = self.reranker.predict(pairs)
            
            # Update scores with reranking
            for i, score in enumerate(rerank_scores):
                if i < len(results):
                    # Blend reranker score with original score
                    # More balanced blending to allow articles to compete
                    if results[i].authority_tier == 'A1':
                        # A1: Balanced blending
                        results[i].score = 0.6 * results[i].score + 0.4 * score
                    elif results[i].authority_tier in ['A2', 'A3']:
                        # A2/A3: Balanced blending
                        results[i].score = 0.55 * results[i].score + 0.45 * score
                    else:
                        # A4: Favor reranker for articles
                        results[i].score = 0.5 * results[i].score + 0.5 * score
        
        # 6. Sort and return top-k
        results.sort(key=lambda x: x.score, reverse=True)
        
        return results[:top_k]
    
    def format_results(self, results: List[RetrievalResult]) -> str:
        """Format retrieval results for display."""
        if not results:
            return "No results found."
        
        output = []
        for i, result in enumerate(results, 1):
            output.append(f"\n{'='*60}")
            output.append(f"Result {i} (Score: {result.score:.3f})")
            output.append(f"{'='*60}")
            output.append(f"📄 Document: {result.doc_id}")
            output.append(f"📚 Section: {result.section_title}")
            output.append(f"🏛️ Authority: {result.authority_tier} | Evidence: {result.evidence_level}")
            output.append(f"📅 Year: {result.year} | Type: {result.doc_type}")
            
            # Show score breakdown
            output.append(f"\n📊 Scores:")
            output.append(f"  • Precedence: {result.precedence_score:.3f}")
            output.append(f"  • Semantic: {result.semantic_score:.3f}")
            output.append(f"  • BM25: {result.bm25_score:.3f}")
            if result.exact_match_score > 0:
                output.append(f"  • Exact Match: {result.exact_match_score:.3f}")
            
            # Show tags
            tags = []
            if result.has_table:
                tags.append("📊 Table")
            if result.has_contraindication:
                tags.append("⚠️ Contraindication")
            if result.has_dose_setting:
                tags.append("💊 Dose/Setting")
            if result.is_emergency:
                tags.append("🚨 EMERGENCY")
            
            if tags:
                output.append(f"\n🏷️ Tags: {' | '.join(tags)}")
            
            # Show text excerpt
            output.append(f"\n📝 Content:")
            text_lines = result.text[:500].split('\n')
            for line in text_lines[:5]:
                output.append(f"  {line}")
            if len(result.text) > 500:
                output.append("  ...")
        
        return '\n'.join(output)


def main():
    """Test the hybrid retriever."""
    retriever = HybridRetriever(
        chunks_file="data/chunks/chunks.jsonl",
        cpt_index_file="data/term_index/cpt_codes.jsonl",
        alias_index_file="data/term_index/aliases.jsonl"
    )
    
    # Test queries
    test_queries = [
        "What are the contraindications for bronchoscopy?",
        "CPT code 31622",
        "Fiducial marker placement technique",
        "Massive hemoptysis management",
        "EBUS-TBNA procedure steps"
    ]
    
    for query in test_queries:
        print(f"\n{'#'*60}")
        print(f"Query: {query}")
        print('#'*60)
        
        results = retriever.retrieve(query, top_k=3)
        print(retriever.format_results(results))


if __name__ == "__main__":
    main()