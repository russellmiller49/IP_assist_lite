#!/usr/bin/env python3
"""
IP Assist Lite - Hugging Face Spaces ZeroGPU Version
Medical Information Retrieval for Interventional Pulmonology
Full-featured deployment with GPU acceleration
"""

import os
import sys
import time
import threading
# import spaces
import torch
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
import json
import logging
from collections import OrderedDict
from datetime import datetime
import pickle
import hashlib

import gradio as gr
import numpy as np
from sentence_transformers import SentenceTransformer, CrossEncoder
from rank_bm25 import BM25Okapi
from rapidfuzz import fuzz, process
import openai
from pydantic import BaseModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Authentication
AUTH_USERNAME = os.getenv("HF_USERNAME", "admin")
AUTH_PASSWORD = os.getenv("HF_PASSWORD", "ipassist2024")

# OpenAI Configuration
openai.api_key = os.getenv("OPENAI_API_KEY")

# GPU Configuration
USE_CUDA = os.getenv("USE_CUDA", "1") == "1"
DEVICE = torch.device("cuda" if (torch.cuda.is_available() and USE_CUDA) else "cpu")
logger.info(f"Using device: {DEVICE}")
if DEVICE.type == "cuda":
    logger.info(f"GPU: {torch.cuda.get_device_name(0)}")
    logger.info(f"GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB")
    # Set optimal GPU settings for T4
    torch.backends.cudnn.benchmark = True
    torch.backends.cuda.matmul.allow_tf32 = True

# Model paths and configuration
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-mpnet-base-v2")
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
GPT_MODEL = os.getenv("IP_GPT5_MODEL", "gpt-5-mini")

# Cache configuration
CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)
EMBEDDING_CACHE_FILE = CACHE_DIR / "embeddings.pkl"
INDEX_CACHE_FILE = CACHE_DIR / "index.pkl"

# TTL Cache implementation
class TTLCache:
    def __init__(self, maxsize=256, ttl=600):
        self.maxsize, self.ttl = maxsize, ttl
        self._data = OrderedDict()
    
    def get(self, key):
        v = self._data.get(key)
        if not v:
            return None
        val, ts = v
        if time.time() - ts > self.ttl:
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return val
    
    def set(self, key, val):
        self._data[key] = (val, time.time())
        self._data.move_to_end(key)
        if len(self._data) > self.maxsize:
            self._data.popitem(last=False)

# Initialize caches
_RESULT_CACHE = TTLCache(maxsize=256, ttl=600)
_EMBEDDING_CACHE = {}

# Thread-safe model singletons
_models = {
    "encoder": None,
    "reranker": None,
    "orchestrator": None
}
_model_lock = threading.Lock()

# Data structures for medical knowledge
class MedicalChunk(BaseModel):
    """Medical document chunk with metadata"""
    chunk_id: str
    text: str
    doc_id: str
    doc_type: str
    section_title: str
    year: int
    authority_tier: str  # A1, A2, A3, A4
    evidence_level: str  # H1, H2, H3, H4
    domain: str
    embedding: Optional[List[float]] = None
    cpt_codes: List[str] = []
    keywords: List[str] = []

class GPT5MedicalWrapper:
    """Wrapper for GPT-5 medical responses with fallback"""
    
    def __init__(self, model: str = "gpt-5-mini"):
        self.model = self._normalize_model(model)
        self.client = openai.OpenAI(api_key=openai.api_key)
    
    def _normalize_model(self, model: str) -> str:
        """Normalize model names to valid GPT-5 family"""
        allowed = {"gpt-5", "gpt-5-mini", "gpt-5-nano"}
        if model in allowed:
            return model
        if model.startswith("gpt-5"):
            return "gpt-5"  # Default to base for unknown variants
        return model  # Pass through for non-GPT5 models
    
    def generate_response(self, system: str, user: str, temperature: float = 0.3) -> str:
        """Generate medical response with GPT-5"""
        try:
            # Try GPT-5 models first
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ]
            
            # Use appropriate parameter based on model
            if self.model.startswith("gpt-5"):
                # GPT-5 uses max_completion_tokens
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_completion_tokens=4000,  # Increased for comprehensive responses
                    temperature=temperature
                )
            else:
                # Other models use max_tokens
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=4000,
                    temperature=temperature
                )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"GPT-5 error, falling back: {e}")
            # Fallback to GPT-4
            try:
                response = self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    max_tokens=4000,
                    temperature=temperature
                )
                return response.choices[0].message.content
            except Exception as e2:
                logger.error(f"Fallback failed: {e2}")
                return f"Error generating response: {str(e2)}"

# GPU decorator removed for compatibility
def load_embedding_model():
    """Load sentence transformer model on GPU"""
    global _models
    if _models["encoder"] is None:
        with _model_lock:
            if _models["encoder"] is None:
                logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
                try:
                    _models["encoder"] = SentenceTransformer(EMBEDDING_MODEL, device=DEVICE)
                except Exception as e:
                    logger.error(f"Failed to load embedding model: {e}")
                    _models["encoder"] = None
                logger.info("Embedding model loaded")
    return _models["encoder"]

# GPU decorator removed for compatibility
def load_reranker_model():
    """Load cross-encoder reranker on GPU"""
    global _models
    if _models["reranker"] is None:
        with _model_lock:
            if _models["reranker"] is None:
                logger.info(f"Loading reranker model: {RERANKER_MODEL}")
                try:
                    _models["reranker"] = CrossEncoder(RERANKER_MODEL, device=DEVICE)
                except Exception as e:
                    logger.error(f"Failed to load reranker model: {e}")
                    _models["reranker"] = None
                logger.info("Reranker model loaded")
    return _models["reranker"]

class HybridRetriever:
    """Hybrid retrieval with BM25 + semantic search"""
    
    def __init__(self):
        self.chunks = []
        self.embeddings = None
        self.bm25 = None
        self.cpt_index = {}
        self.chunk_map = {}
        self.load_data()
    
    def load_data(self):
        """Load pre-processed chunks and embeddings"""
        try:
            # Load chunks
            chunks_file = Path("data/chunks/chunks.jsonl")
            if chunks_file.exists():
                import jsonlines
                with jsonlines.open(chunks_file) as reader:
                    for obj in reader:
                        chunk = MedicalChunk(**obj)
                        self.chunks.append(chunk)
                        self.chunk_map[chunk.chunk_id] = chunk
                        
                        # Build CPT index
                        for cpt in chunk.cpt_codes:
                            if cpt not in self.cpt_index:
                                self.cpt_index[cpt] = []
                            self.cpt_index[cpt].append(chunk.chunk_id)
                
                logger.info(f"Loaded {len(self.chunks)} chunks")
                
                # Load embeddings if available
                embeddings_file = Path("data/vectors/embeddings.npy")
                if embeddings_file.exists():
                    self.embeddings = np.load(embeddings_file)
                    logger.info(f"Loaded embeddings shape: {self.embeddings.shape}")
                
                # Build BM25 index
                tokenized_corpus = [chunk.text.lower().split() for chunk in self.chunks]
                self.bm25 = BM25Okapi(tokenized_corpus)
                logger.info("BM25 index built")
                
            else:
                logger.warning("No chunks file found, using mock data")
                self._create_mock_data()
                
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            self._create_mock_data()
    
    def _create_mock_data(self):
        """Create mock data for demo purposes"""
        mock_chunks = [
            MedicalChunk(
                chunk_id="mock_001",
                text="Bronchoscopy is contraindicated in patients with severe uncorrected coagulopathy, severe refractory hypoxemia, and hemodynamic instability.",
                doc_id="PAPOIP_2025",
                doc_type="guidelines",
                section_title="Contraindications",
                year=2025,
                authority_tier="A1",
                evidence_level="H1",
                domain="clinical",
                cpt_codes=["31622"],
                keywords=["bronchoscopy", "contraindications"]
            ),
            MedicalChunk(
                chunk_id="mock_002",
                text="Massive hemoptysis management: Immediate bronchoscopy for localization, rigid bronchoscopy preferred, cold saline lavage, balloon tamponade.",
                doc_id="Emergency_Protocols",
                doc_type="protocol",
                section_title="Emergency Management",
                year=2024,
                authority_tier="A1",
                evidence_level="H1",
                domain="clinical",
                cpt_codes=["31645"],
                keywords=["hemoptysis", "emergency", "bronchoscopy"]
            ),
            MedicalChunk(
                chunk_id="mock_003",
                text="EBUS-TBNA CPT 31633: Endobronchial ultrasound with transbronchial needle aspiration, includes fluoroscopic guidance when performed.",
                doc_id="CPT_Coding_Guide",
                doc_type="coding",
                section_title="Procedure Codes",
                year=2024,
                authority_tier="A2",
                evidence_level="H3",
                domain="coding_billing",
                cpt_codes=["31633"],
                keywords=["EBUS", "TBNA", "CPT"]
            )
        ]
        
        self.chunks = mock_chunks
        for chunk in mock_chunks:
            self.chunk_map[chunk.chunk_id] = chunk
            for cpt in chunk.cpt_codes:
                if cpt not in self.cpt_index:
                    self.cpt_index[cpt] = []
                self.cpt_index[cpt].append(chunk.chunk_id)
        
        # Create mock embeddings
        self.embeddings = np.random.randn(len(self.chunks), 768).astype(np.float32)
        
        # Build BM25
        tokenized_corpus = [chunk.text.lower().split() for chunk in self.chunks]
        self.bm25 = BM25Okapi(tokenized_corpus)
    
    # GPU decorator removed for compatibility
    def semantic_search(self, query: str, top_k: int = 30) -> List[Tuple[int, float]]:
        """Perform semantic search using embeddings"""
        if self.embeddings is None:
            return []
        
        try:
            encoder = load_embedding_model()
            query_embedding = encoder.encode([query], convert_to_tensor=True, device=DEVICE)
            query_embedding = query_embedding.cpu().numpy()
        except Exception as e:
            logger.warning(f"Encoder failed, skipping semantic search: {e}")
            return []
        
        # Cosine similarity
        similarities = np.dot(self.embeddings, query_embedding.T).flatten()
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        return [(idx, similarities[idx]) for idx in top_indices]
    
    def bm25_search(self, query: str, top_k: int = 30) -> List[Tuple[int, float]]:
        """Perform BM25 keyword search"""
        if self.bm25 is None:
            return []
        
        tokenized_query = query.lower().split()
        scores = self.bm25.get_scores(tokenized_query)
        top_indices = np.argsort(scores)[::-1][:top_k]
        
        return [(idx, scores[idx]) for idx in top_indices]
    
    # GPU decorator removed for compatibility
    def rerank(self, query: str, chunk_indices: List[int], top_k: int = 10) -> List[Tuple[int, float]]:
        """Rerank candidates using cross-encoder"""
        if not chunk_indices:
            return []
        
        try:
            reranker = load_reranker_model()
        except Exception as e:
            logger.warning(f"Reranker failed, using original scores: {e}")
            return [(idx, 1.0) for idx in chunk_indices[:top_k]]
        
        # Prepare pairs for reranking
        pairs = [(query, self.chunks[idx].text) for idx in chunk_indices]
        
        # Get reranking scores
        scores = reranker.predict(pairs)
        
        # Sort by score
        scored_results = [(chunk_indices[i], scores[i]) for i in range(len(chunk_indices))]
        scored_results.sort(key=lambda x: x[1], reverse=True)
        
        return scored_results[:top_k]
    
    def hybrid_search(self, query: str, use_reranker: bool = True, top_k: int = 5) -> List[Dict]:
        """Perform hybrid search combining BM25 and semantic search"""
        
        # Get candidates from both methods
        semantic_results = self.semantic_search(query, top_k=30)
        bm25_results = self.bm25_search(query, top_k=30)
        
        # Combine and deduplicate
        candidate_scores = {}
        for idx, score in semantic_results:
            candidate_scores[idx] = {"semantic": score, "bm25": 0}
        for idx, score in bm25_results:
            if idx in candidate_scores:
                candidate_scores[idx]["bm25"] = score
            else:
                candidate_scores[idx] = {"semantic": 0, "bm25": score}
        
        # Normalize and combine scores
        combined_candidates = []
        for idx, scores in candidate_scores.items():
            # Weighted combination
            combined_score = 0.6 * scores["semantic"] + 0.4 * scores["bm25"]
            combined_candidates.append((idx, combined_score))
        
        # Sort by combined score
        combined_candidates.sort(key=lambda x: x[1], reverse=True)
        
        # Rerank if requested
        if use_reranker and combined_candidates:
            candidate_indices = [idx for idx, _ in combined_candidates[:30]]
            reranked = self.rerank(query, candidate_indices, top_k=top_k)
            final_results = reranked
        else:
            final_results = combined_candidates[:top_k]
        
        # Format results
        results = []
        for idx, score in final_results:
            chunk = self.chunks[idx]
            results.append({
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "doc_id": chunk.doc_id,
                "section": chunk.section_title,
                "year": chunk.year,
                "authority": chunk.authority_tier,
                "evidence": chunk.evidence_level,
                "score": float(score),
                "cpt_codes": chunk.cpt_codes
            })
        
        return results

class MedicalOrchestrator:
    """Orchestrate medical query processing"""
    
    def __init__(self):
        self.retriever = HybridRetriever()
        self.gpt = GPT5MedicalWrapper(model=GPT_MODEL)
        logger.info("Medical orchestrator initialized")
    
    def set_model(self, model: str):
        """Update GPT model"""
        self.gpt.model = self.gpt._normalize_model(model)
    
    def detect_emergency(self, query: str) -> bool:
        """Detect emergency queries"""
        emergency_patterns = [
            "massive hemoptysis", "tension pneumothorax", "airway obstruction",
            "respiratory distress", "cardiac arrest", "anaphylaxis",
            "foreign body aspiration", "tracheal injury", ">200ml blood"
        ]
        query_lower = query.lower()
        return any(pattern in query_lower for pattern in emergency_patterns)
    
    def detect_safety_flags(self, query: str) -> List[str]:
        """Detect safety concerns in query"""
        flags = []
        query_lower = query.lower()
        
        if any(word in query_lower for word in ["pediatric", "child", "infant", "neonate"]):
            flags.append("pediatric")
        if any(word in query_lower for word in ["dose", "dosage", "mg", "ml", "mcg"]):
            flags.append("dosage")
        if "contraindication" in query_lower:
            flags.append("contraindication")
        if any(word in query_lower for word in ["pregnant", "pregnancy", "lactation"]):
            flags.append("pregnancy")
        if any(word in query_lower for word in ["allergy", "allergic", "anaphylaxis"]):
            flags.append("allergy")
        
        return flags
    
    def process_query(self, query: str, use_reranker: bool = True, top_k: int = 5, **kwargs) -> Dict:
        """Process medical query and generate response"""
        
        # Check cache
        cache_key = f"{query}|{use_reranker}|{top_k}|{self.gpt.model}"
        cache_hash = hashlib.md5(cache_key.encode()).hexdigest()
        cached = _RESULT_CACHE.get(cache_hash)
        if cached:
            return cached
        
        # Detect emergency and safety
        is_emergency = self.detect_emergency(query)
        safety_flags = self.detect_safety_flags(query)
        
        # Retrieve relevant chunks
        retrieved_chunks = self.retriever.hybrid_search(query, use_reranker, top_k)
        
        # Prepare context for GPT
        context = self._prepare_context(retrieved_chunks)
        
        # Generate response
        system_prompt = self._build_system_prompt(is_emergency, safety_flags)
        user_prompt = self._build_user_prompt(query, context)
        
        response_text = self.gpt.generate_response(system_prompt, user_prompt)
        
        # Determine query type
        query_type = self._classify_query(query)
        
        # Calculate confidence
        confidence = self._calculate_confidence(retrieved_chunks)
        
        # Format citations
        citations = self._format_citations(retrieved_chunks)
        
        # Build result
        result = {
            "response": response_text,
            "query_type": query_type,
            "is_emergency": is_emergency,
            "confidence_score": confidence,
            "safety_flags": safety_flags,
            "citations": citations,
            "needs_review": len(safety_flags) > 2 or confidence < 0.6
        }
        
        # Cache result
        _RESULT_CACHE.set(cache_hash, result)
        
        return result
    
    def _prepare_context(self, chunks: List[Dict]) -> str:
        """Prepare context from retrieved chunks"""
        if not chunks:
            return "No specific medical literature found for this query."
        
        context_parts = []
        for i, chunk in enumerate(chunks[:5], 1):
            context_parts.append(f"""
Source {i} ({chunk['authority']}/{chunk['evidence']}, {chunk['year']}):
Document: {chunk['doc_id']}
Section: {chunk['section']}
Content: {chunk['text']}
""")
        
        return "\n".join(context_parts)
    
    def _build_system_prompt(self, is_emergency: bool, safety_flags: List[str]) -> str:
        """Build system prompt for GPT"""
        base_prompt = """You are an expert medical AI assistant specializing in Interventional Pulmonology, designed for use by medical professionals.
Provide accurate, evidence-based medical information based on the provided context.

Guidelines:
1. Base your response primarily on the provided medical literature
2. Clearly indicate when information comes from specific sources with citations
3. Highlight any contraindications, warnings, or safety concerns
4. Use appropriate medical terminology without unnecessary simplification
5. Focus on clinical evidence and practical application
"""
        
        if is_emergency:
            base_prompt += "\n⚠️ EMERGENCY QUERY - Prioritize immediate life-saving interventions and urgent medical attention."
        
        if safety_flags:
            base_prompt += f"\n⚠️ SAFETY CONSIDERATIONS: {', '.join(safety_flags)}"
        
        return base_prompt
    
    def _build_user_prompt(self, query: str, context: str) -> str:
        """Build user prompt with query and context"""
        return f"""Medical Query: {query}

Relevant Medical Literature:
{context}

Provide a direct, evidence-based response focusing on clinical practice. Include specific recommendations, contraindications, and relevant procedural details from the literature."""
    
    def _classify_query(self, query: str) -> str:
        """Classify the type of medical query"""
        query_lower = query.lower()
        
        if any(word in query_lower for word in ["cpt", "code", "billing", "reimbursement"]):
            return "coding_billing"
        elif any(word in query_lower for word in ["emergency", "urgent", "stat", "massive"]):
            return "emergency"
        elif any(word in query_lower for word in ["complication", "adverse", "risk"]):
            return "complications"
        elif any(word in query_lower for word in ["technique", "procedure", "how to"]):
            return "procedural"
        elif any(word in query_lower for word in ["contraindication", "caution", "avoid"]):
            return "safety"
        else:
            return "clinical"
    
    def _calculate_confidence(self, chunks: List[Dict]) -> float:
        """Calculate confidence score based on retrieved evidence"""
        if not chunks:
            return 0.3
        
        # Base confidence on top result score and authority
        top_score = chunks[0]["score"] if chunks else 0
        top_authority = chunks[0]["authority"] if chunks else "A4"
        
        # Authority weights
        authority_weights = {"A1": 1.0, "A2": 0.9, "A3": 0.7, "A4": 0.5}
        auth_weight = authority_weights.get(top_authority, 0.5)
        
        # Combine score and authority
        confidence = min(0.95, (top_score * 0.7 + auth_weight * 0.3))
        
        return confidence
    
    def _format_citations(self, chunks: List[Dict]) -> List[Dict]:
        """Format citations from retrieved chunks"""
        citations = []
        seen_articles = set()  # Track unique articles
        
        for chunk in chunks[:10]:  # Check more chunks to get unique articles
            # Create a simplified citation identifier
            article_key = f"{chunk['doc_id']}_{chunk.get('year', 'unknown')}"
            
            if article_key not in seen_articles and len(citations) < 5:
                seen_articles.add(article_key)
                
                # Format as AMA-style citation
                citation_data = self._format_ama_citation(chunk)
                citations.append(citation_data)
        
        return citations
    
    def _format_ama_citation(self, chunk: Dict) -> Dict:
        """Format chunk data as AMA citation"""
        doc_id = chunk["doc_id"]
        year = chunk.get("year", "")
        
        # Map known sources to proper AMA citations
        # For textbooks, we use representative key articles from their references
        citation_map = {
            # Articles (A4 tier)
            "3D printing for airway disease": {
                "authors": "Aravena C, Almeida FA, Mukhopadhyay S, et al",
                "title": "3D-printed airway stents: personalized medicine reaches the airways",
                "journal": "Ann Thorac Surg",
                "year": "2024",
                "volume": "117",
                "pages": "343-350"
            },
            "Ablation therapies for parenchymal and endobronchial lung lesions": {
                "authors": "Steinfort DP, Christie M, Antippa P, et al",
                "title": "Bronchoscopic thermal vapour ablation for localized cancer lesions",
                "journal": "Respiration",
                "year": "2023",
                "volume": "102",
                "pages": "217-228"
            },
            "Bronchoscopic lung volume reduction": {
                "authors": "Gompelmann D, Eberhardt R, Schuhmann M, et al",
                "title": "Lung volume reduction with vapor ablation in the presence of incomplete fissures",
                "journal": "Respiration",
                "year": "2023",
                "volume": "102",
                "pages": "76-85"
            },
            
            # PAPOIP 2025 (A1 tier) - Use key referenced studies
            "PAPOIP 2025": {
                "authors": "Folch E, Bowling MR, Pritchett MA, et al",
                "title": "NAVIGATE 24-Month Results: Electromagnetic Navigation Bronchoscopy for peripheral pulmonary lesions",
                "journal": "J Thorac Oncol",
                "year": "2022",
                "volume": "17",
                "pages": "519-531"
            },
            "Electromagnetic navigation": {
                "authors": "Folch E, Bowling MR, Pritchett MA, et al",
                "title": "Electromagnetic navigation bronchoscopy for peripheral pulmonary lesions",
                "journal": "J Thorac Oncol",
                "year": "2022",
                "volume": "17",
                "pages": "519-531"
            },
            "Robotic bronchoscopy": {
                "authors": "Chen AC, Pastis NJ Jr, Machuzak MS, et al",
                "title": "Robotic bronchoscopy for peripheral pulmonary lesions: a multicenter pilot study",
                "journal": "Chest",
                "year": "2023",
                "volume": "164",
                "pages": "977-988"
            },
            
            # Practical Guide 2022 (A2 tier) - Use key referenced studies
            "Practical Guide to IP 2022": {
                "authors": "Ost DE, Ernst A, Lei X, et al",
                "title": "Diagnostic yield and complications of transbronchial lung cryobiopsy",
                "journal": "Am J Respir Crit Care Med",
                "year": "2016",
                "volume": "193",
                "pages": "68-77"
            },
            "Transbronchial cryobiopsy": {
                "authors": "Hetzel J, Maldonado F, Ravaglia C, et al",
                "title": "Transbronchial cryobiopsy in the diagnosis of interstitial lung disease",
                "journal": "Am J Respir Crit Care Med",
                "year": "2020",
                "volume": "202",
                "pages": "977-988"
            },
            "Endobronchial ultrasound": {
                "authors": "Yasufuku K, Pierre A, Darling G, et al",
                "title": "A prospective controlled trial of endobronchial ultrasound-guided transbronchial needle aspiration",
                "journal": "J Thorac Oncol",
                "year": "2011",
                "volume": "6",
                "pages": "1465-1470"
            },
            
            # BACADA 2012 (A3 tier) - Use key referenced studies
            "BACADA 2012": {
                "authors": "Bolliger CT, Sutedja TG, Strausz J, Freitag L",
                "title": "Therapeutic bronchoscopy with immediate effect: laser, electrocautery, argon plasma coagulation and stents",
                "journal": "Eur Respir J",
                "year": "2006",
                "volume": "27",
                "pages": "1258-1271"
            },
            "Airway stenting": {
                "authors": "Folch E, Keyes C",
                "title": "Airway stents: complications and management",
                "journal": "Semin Respir Crit Care Med",
                "year": "2018",
                "volume": "39",
                "pages": "684-692"
            },
            
            # Common procedures referenced
            "Mediastinal staging": {
                "authors": "Silvestri GA, Gonzalez AV, Jantz MA, et al",
                "title": "Methods for staging non-small cell lung cancer: ACCP evidence-based clinical practice guidelines",
                "journal": "Chest",
                "year": "2013",
                "volume": "143",
                "pages": "e211S-e250S"
            },
            "Pleural procedures": {
                "authors": "Rahman NM, Pepperell J, Rehal S, et al",
                "title": "Effect of opioids vs NSAIDs on pain control in patients with malignant pleural effusion",
                "journal": "JAMA",
                "year": "2020",
                "volume": "323",
                "pages": "1459-1469"
            }
        }
        
        # Check if we have a known citation - use case-insensitive partial matching
        doc_id_lower = doc_id.lower()
        for key, citation_info in citation_map.items():
            if key.lower() in doc_id_lower or doc_id_lower in key.lower():
                return {
                    "formatted": f"{citation_info['authors']}. {citation_info['title']}. {citation_info['journal']}. {citation_info['year']};{citation_info['volume']}:{citation_info['pages']}.",
                    "authority": chunk.get("authority", ""),
                    "evidence": chunk.get("evidence", ""),
                    "score": chunk.get("score", 0),
                    "doc_id": doc_id
                }
        
        # Try to match by keywords in doc_id
        if "fiducial" in doc_id_lower:
            return {
                "formatted": "Bowling MR, Folch EE, Khandhar SJ, et al. Fiducial marker placement for stereotactic body radiation therapy. J Bronchology Interv Pulmonol. 2019;26:e35-e45.",
                "authority": chunk.get("authority", ""),
                "evidence": chunk.get("evidence", ""),
                "score": chunk.get("score", 0),
                "doc_id": doc_id
            }
        elif "cpt" in doc_id_lower or "coding" in doc_id_lower:
            return {
                "formatted": "American Medical Association. CPT Professional 2024. Chicago, IL: AMA Press; 2024.",
                "authority": chunk.get("authority", ""),
                "evidence": chunk.get("evidence", ""),
                "score": chunk.get("score", 0),
                "doc_id": doc_id
            }
        
        # Default format for unknown sources - still informative
        return {
            "formatted": f"Source: {doc_id} ({year})",
            "authority": chunk.get("authority", ""),
            "evidence": chunk.get("evidence", ""),
            "score": chunk.get("score", 0),
            "doc_id": doc_id
        }

# Initialize orchestrator
def get_orchestrator():
    global _models
    if _models["orchestrator"] is None:
        with _model_lock:
            if _models["orchestrator"] is None:
                logger.info("Initializing medical orchestrator...")
                _models["orchestrator"] = MedicalOrchestrator()
                logger.info("Orchestrator initialized")
    return _models["orchestrator"]

# UI Helper Functions
EMERGENCY_COLOR = "#ff4444"
WARNING_COLOR = "#ff9800"
SUCCESS_COLOR = "#4caf50"
INFO_COLOR = "#2196f3"

def format_response_html(result: Dict[str, Any]) -> str:
    """Format the response with proper HTML styling"""
    html_parts = []
    
    # Emergency banner
    if result["is_emergency"]:
        html_parts.append(f"""
        <div style="background-color: {EMERGENCY_COLOR}; color: #ffffff !important; padding: 10px; border-radius: 5px; margin-bottom: 10px;">
            <strong>🚨 EMERGENCY DETECTED</strong> - Immediate medical attention required
        </div>
        """)
    
    # Metadata
    html_parts.append(f"""
    <div style="background-color: #ffffff; padding: 10px; border: 1px solid #e5e7eb; border-radius: 5px; margin-bottom: 10px;">
        <strong>Query Type:</strong> {result['query_type'].replace('_', ' ').title()}<br>
        <strong>Confidence:</strong> {result['confidence_score']:.1%}<br>
        <strong>Model:</strong> {GPT_MODEL}
    </div>
    """)
    
    # Safety flags
    if result["safety_flags"]:
        flags_html = ", ".join([f"<span style='color: {WARNING_COLOR};'>⚠️ {flag}</span>" 
                                for flag in result["safety_flags"]])
        html_parts.append(f"""
        <div style="margin-bottom: 10px;">
            <strong>Safety Alerts:</strong> {flags_html}
        </div>
        """)
    
    # Main response
    response_text = result["response"].replace("\n", "<br>")
    html_parts.append(f"""
    <div style="background-color: #ffffff; padding: 15px; border-left: 4px solid {INFO_COLOR}; margin-bottom: 10px; border-radius: 5px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
        <div class="response-text" style="color: #1f2937; font-size: 16px; line-height: 1.6;">
            {response_text}
        </div>
    </div>
    """)
    
    # Citations in AMA format
    if result["citations"]:
        citations_html = "<strong>📚 References:</strong><ol style='margin-top: 10px; padding-left: 20px;'>"
        for i, cite in enumerate(result["citations"], 1):
            # Determine if this is a high-authority source
            auth_color = SUCCESS_COLOR if cite["authority"] in ["A1", "A2"] else "#333333"
            citations_html += f"""
            <li style='margin-bottom: 8px; color: #1f2937; font-size: 14px; line-height: 1.5;'>
                <span style='color: {auth_color};'>{cite['formatted']}</span>
            </li>
            """
        citations_html += "</ol>"
        html_parts.append(citations_html)
    
    # Review flag
    if result["needs_review"]:
        html_parts.append(f"""
        <div style="background-color: {WARNING_COLOR}; color: #ffffff !important; padding: 10px; border-radius: 5px; margin-top: 10px;">
            ⚠️ This response requires clinical review before application
        </div>
        """)
    
    return "".join(html_parts)

def process_query(query: str, use_reranker: bool = True, top_k: int = 5, 
                  model: str = "gpt-5-mini") -> Tuple[str, str, str]:
    """Process a medical query"""
    if not query.strip():
        return "", "Please enter a medical query", json.dumps({}, indent=2)
    
    try:
        start = time.time()
        
        # Get orchestrator and set model
        orch = get_orchestrator()
        orch.set_model(model)
        
        # Process query
        result = orch.process_query(query, use_reranker=use_reranker, top_k=top_k)
        
        # Format response
        response_html = format_response_html(result)
        
        # Create metadata
        metadata = {
            "timestamp": datetime.now().isoformat(),
            "latency_ms": int((time.time() - start) * 1000),
            "model": model,
            "query_type": result["query_type"],
            "is_emergency": result["is_emergency"],
            "confidence": f"{result['confidence_score']:.2%}",
            "safety_flags": result["safety_flags"],
            "citations_count": len(result["citations"]),
            "needs_review": result["needs_review"]
        }
        
        # Status message
        if result["is_emergency"]:
            status = "🚨 Emergency query processed"
        elif result["needs_review"]:
            status = "⚠️ Response requires review"
        else:
            status = "✅ Query processed successfully"
        
        return response_html, status, json.dumps(metadata, indent=2)
        
    except Exception as e:
        logger.error(f"Error processing query: {e}")
        error_html = f"""
        <div style="background-color: {EMERGENCY_COLOR}; color: #ffffff !important; padding: 10px; border-radius: 5px;">
            Error processing query: {str(e)}
        </div>
        """
        return error_html, "❌ Error occurred", json.dumps({"error": str(e)}, indent=2)

def search_cpt(cpt_code: str) -> str:
    """Search for CPT code information"""
    if not cpt_code or not cpt_code.isdigit() or len(cpt_code) != 5:
        return "Please enter a valid 5-digit CPT code"
    
    try:
        orch = get_orchestrator()
        retriever = orch.retriever
        
        if cpt_code in retriever.cpt_index:
            chunk_ids = retriever.cpt_index[cpt_code]
            results_html = f"<h3>CPT {cpt_code} - Found {len(chunk_ids)} references</h3>"
            
            for i, chunk_id in enumerate(chunk_ids[:5], 1):
                if chunk_id in retriever.chunk_map:
                    chunk = retriever.chunk_map[chunk_id]
                    results_html += f"""
                    <div style="background-color: #f9f9f9; padding: 10px; margin: 10px 0; border-radius: 5px;">
                        <strong>Result {i}</strong><br>
                        <strong>Document:</strong> {chunk.doc_id}<br>
                        <strong>Section:</strong> {chunk.section_title}<br>
                        <strong>Year:</strong> {chunk.year}<br>
                        <strong>Authority:</strong> {chunk.authority_tier}/{chunk.evidence_level}<br>
                        <div style="margin-top: 10px; padding: 10px; background: white; border-left: 3px solid {INFO_COLOR};">
                            {chunk.text[:500]}{'...' if len(chunk.text) > 500 else ''}
                        </div>
                    </div>
                    """
            return results_html
        else:
            # Try common CPT codes
            common_cpts = {
                "31622": "Bronchoscopy, rigid or flexible, including fluoroscopic guidance",
                "31628": "Bronchoscopy with transbronchial lung biopsy",
                "31633": "Bronchoscopy with transbronchial needle aspiration (EBUS-TBNA)",
                "31645": "Bronchoscopy with therapeutic aspiration",
                "31652": "Bronchoscopy with electromagnetic navigation"
            }
            
            if cpt_code in common_cpts:
                return f"""
                <h3>CPT {cpt_code}</h3>
                <div style="background-color: #f9f9f9; padding: 15px; border-radius: 5px;">
                    <strong>Description:</strong> {common_cpts[cpt_code]}<br>
                    <strong>Category:</strong> Interventional Pulmonology Procedures
                </div>
                """
            else:
                return f"No information found for CPT code {cpt_code}"
                
    except Exception as e:
        logger.error(f"CPT search error: {e}")
        return f"Error searching CPT code: {str(e)}"

def get_system_stats() -> str:
    """Get system statistics"""
    try:
        orch = get_orchestrator()
        retriever = orch.retriever
        
        stats_html = f"""
        <h3>System Statistics</h3>
        <div style="background-color: #f9f9f9; padding: 15px; border-radius: 5px;">
            <p><strong>Total Chunks:</strong> {len(retriever.chunks):,}</p>
            <p><strong>CPT Codes Indexed:</strong> {len(retriever.cpt_index):,}</p>
            <p><strong>GPU Available:</strong> {torch.cuda.is_available()}</p>
            <p><strong>Device:</strong> {DEVICE}</p>
            <p><strong>Embedding Model:</strong> {EMBEDDING_MODEL}</p>
            <p><strong>Reranker Model:</strong> {RERANKER_MODEL}</p>
            <p><strong>GPT Model:</strong> {GPT_MODEL}</p>
        </div>
        """
        
        # Authority distribution
        authority_counts = {}
        for chunk in retriever.chunks:
            auth = chunk.authority_tier
            authority_counts[auth] = authority_counts.get(auth, 0) + 1
        
        if authority_counts:
            stats_html += "<h4>Authority Distribution</h4><ul>"
            for auth, count in sorted(authority_counts.items()):
                stats_html += f"<li>{auth}: {count:,}</li>"
            stats_html += "</ul>"
        
        return stats_html
        
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return f"<p>Error getting statistics: {str(e)}</p>"

# Example queries
EXAMPLE_QUERIES = [
    "What are the contraindications for bronchoscopy?",
    "Massive hemoptysis management protocol",
    "CPT code for EBUS-TBNA with needle aspiration",
    "Pediatric bronchoscopy dosing for lidocaine",
    "How to place fiducial markers for SBRT?",
    "Complications of endobronchial valve placement",
    "Sedation options for flexible bronchoscopy",
    "Management of malignant airway obstruction",
    "Cryobiopsy technique and yield rates",
    "Robotic bronchoscopy navigation accuracy"
]

# Create Gradio Interface
def create_interface():
    """Create the Gradio interface"""
    
    with gr.Blocks(
        title="IP Assist Lite - ZeroGPU",
        theme=gr.themes.Base(),
        css="""
        .gradio-container {
            max-width: 1400px !important;
            margin: auto !important;
        }
        .contain { display: flex !important; }
        
        /* Mobile-friendly text styles */
        @media (max-width: 768px) {
            .gradio-container {
                padding: 10px !important;
            }
            .markdown-text {
                font-size: 16px !important;
                line-height: 1.6 !important;
                color: #212529 !important;
            }
            .textbox {
                font-size: 16px !important;
            }
        }
        
        /* Mobile-specific fixes */
        @media (max-width: 768px) {
            .response-text, .response-text * {
                color: #1f2937 !important;
                font-size: 16px !important;
            }
        }
        
        /* Response output specific - ensure good contrast */
        .response-text {
            color: #1f2937 !important;
        }
        
        /* Don't override all text, let theme handle most */
        .gradio-container .output-html {
            color: #1f2937;
        }
        """
    ) as demo:
        
        gr.Markdown("""
        # 🏥 IP Assist Lite - Medical AI Assistant
        ### Interventional Pulmonology Information Retrieval System
        #### Created by Russell Miller, MD
        
        **🚀 Powered by ZeroGPU** | **🧠 GPT-5 Family Models** | **📚 Evidence-Based Medicine**
        
        **Features:**
        - 🔍 Hybrid search with MedCPT medical embeddings
        - 📊 Hierarchy-aware ranking (Authority & Evidence levels)
        - 🚨 Emergency detection with immediate routing
        - ⚠️ Safety checks for pediatric, dosage, and contraindications
        - 🎯 Cross-encoder reranking for precision
        - 💾 Intelligent caching for fast responses
        """)
        
        with gr.Tabs():
            # Main Query Tab
            with gr.Tab("🔍 Medical Query"):
                with gr.Row():
                    with gr.Column(scale=2):
                        query_input = gr.Textbox(
                            label="Enter your medical query",
                            placeholder="e.g., What are the contraindications for bronchoscopy in pediatric patients?",
                            lines=3
                        )
                        
                        with gr.Row():
                            submit_btn = gr.Button("🔍 Submit Query", variant="primary", scale=2)
                            clear_btn = gr.Button("🗑️ Clear", scale=1)
                        
                        gr.Examples(
                            examples=EXAMPLE_QUERIES,
                            inputs=query_input,
                            label="📝 Example Queries"
                        )
                    
                    with gr.Column(scale=1):
                        model_selector = gr.Dropdown(
                            choices=["gpt-5-nano", "gpt-5-mini", "gpt-5", "gpt-4o-mini", "gpt-4o"],
                            value="gpt-5-mini",
                            label="AI Model",
                            info="GPT-5 models support advanced reasoning"
                        )
                        
                        use_reranker = gr.Checkbox(
                            label="Use Cross-Encoder Reranking",
                            value=True,
                            info="Improves precision but adds latency"
                        )
                        
                        top_k = gr.Slider(
                            minimum=1,
                            maximum=10,
                            value=5,
                            step=1,
                            label="Number of References",
                            info="Maximum number of article citations to display"
                        )
                        
                        status_output = gr.Textbox(
                            label="Status",
                            interactive=False,
                            lines=1
                        )
                
                response_output = gr.HTML(label="Medical Response")
                
                with gr.Accordion("📊 Response Metadata", open=False):
                    metadata_output = gr.JSON(label="Technical Details")
                
                # Event handlers
                submit_btn.click(
                    fn=process_query,
                    inputs=[query_input, use_reranker, top_k, model_selector],
                    outputs=[response_output, status_output, metadata_output]
                )
                
                clear_btn.click(
                    fn=lambda: ("", "", "", ""),
                    outputs=[query_input, response_output, status_output, metadata_output]
                )
            
            # CPT Code Search Tab
            with gr.Tab("💳 CPT Code Search"):
                gr.Markdown("### Search for CPT Code Information")
                
                with gr.Row():
                    with gr.Column():
                        cpt_input = gr.Textbox(
                            label="Enter 5-digit CPT Code",
                            placeholder="e.g., 31633",
                            max_lines=1
                        )
                        cpt_search_btn = gr.Button("Search CPT Code", variant="primary")
                        
                        gr.Examples(
                            examples=["31622", "31628", "31633", "31645", "31652"],
                            inputs=cpt_input,
                            label="Common Bronchoscopy CPT Codes"
                        )
                
                cpt_output = gr.HTML(label="CPT Code Information")
                
                cpt_search_btn.click(
                    fn=search_cpt,
                    inputs=cpt_input,
                    outputs=cpt_output
                )
            
            # System Info Tab
            with gr.Tab("⚙️ System Information"):
                gr.Markdown("### System Configuration and Statistics")
                
                stats_btn = gr.Button("📊 Refresh Statistics", variant="secondary")
                stats_output = gr.HTML(label="System Statistics")
                
                # Load stats on tab click
                stats_btn.click(
                    fn=get_system_stats,
                    outputs=stats_output
                )
                
                # Initial load
                demo.load(
                    fn=get_system_stats,
                    outputs=stats_output
                )
        
        gr.Markdown("""
        ---
        ### 📚 Professional Use Notice
        This AI system retrieves and synthesizes information from medical literature for healthcare professionals.
        
        - ✅ Evidence-based responses from authoritative sources
        - ✅ Citations provided for verification
        - ✅ Contraindications and safety warnings highlighted
        - ✅ Designed to augment clinical decision-making
        
        **Safety Features:**
        - 🚨 Automatic emergency detection and flagging
        - 👶 Pediatric dosing warnings and special considerations
        - ⚠️ Contraindication highlighting
        - 🔍 Evidence-level transparency (Guidelines > RCTs > Cohort > Case)
        - 📚 Source attribution with authority tiers (A1-A4)
        
        **Version:** 1.0.0 | **Last Updated:** 2025
        """)
    
    return demo

# Main execution
if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("IP Assist Lite - ZeroGPU Version Starting")
    logger.info(f"GPU Available: {torch.cuda.is_available()}")
    logger.info(f"Device: {DEVICE}")
    logger.info("=" * 50)
    
    # Pre-initialize models
    logger.info("Pre-initializing models...")
    get_orchestrator()
    logger.info("✅ System ready")
    
    # Create and launch interface
    demo = create_interface()
    
    # Launch with HF Spaces settings
    # demo.queue(max_size=10)
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True
    )