#!/usr/bin/env python3
"""
FastAPI endpoints for IP Assist Lite
Provides REST API for medical information retrieval
"""

import sys
from pathlib import Path
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
import json
import logging

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from orchestration.langgraph_agent import IPAssistOrchestrator
from retrieval.hybrid_retriever import HybridRetriever

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="IP Assist Lite API",
    description="Medical information retrieval system for Interventional Pulmonology",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize orchestrator (singleton)
orchestrator = None

def get_orchestrator():
    global orchestrator
    if orchestrator is None:
        logger.info("Initializing orchestrator...")
        orchestrator = IPAssistOrchestrator()
        logger.info("Orchestrator initialized")
    return orchestrator

# Pydantic models for request/response
class QueryRequest(BaseModel):
    query: str = Field(..., description="The medical query to process")
    top_k: int = Field(5, description="Number of results to return", ge=1, le=20)
    use_reranker: bool = Field(True, description="Whether to use cross-encoder reranking")
    filters: Optional[Dict[str, Any]] = Field(None, description="Optional filters for retrieval")

class QueryResponse(BaseModel):
    query: str
    response: str
    query_type: str
    is_emergency: bool
    confidence_score: float
    citations: List[Dict[str, Any]]
    safety_flags: List[str]
    needs_review: bool
    timestamp: str

class HealthResponse(BaseModel):
    status: str
    qdrant_connected: bool
    chunks_loaded: bool
    embeddings_available: bool
    timestamp: str

class SearchRequest(BaseModel):
    query: str
    search_type: Literal["semantic", "bm25", "exact", "hybrid"] = "hybrid"
    top_k: int = Field(10, ge=1, le=50)
    authority_filter: Optional[str] = Field(None, pattern="^A[1-4]$")
    has_table: Optional[bool] = None
    has_contraindication: Optional[bool] = None

class CPTSearchRequest(BaseModel):
    cpt_code: str = Field(..., pattern="^\\d{5}$", description="5-digit CPT code")

class StatisticsResponse(BaseModel):
    total_chunks: int
    total_documents: int
    authority_distribution: Dict[str, int]
    evidence_distribution: Dict[str, int]
    doc_type_distribution: Dict[str, int]
    year_range: Dict[str, int]

# Endpoints
@app.get("/", response_model=Dict[str, str])
async def root():
    """Root endpoint with API information."""
    return {
        "name": "IP Assist Lite API",
        "version": "1.0.0",
        "description": "Medical information retrieval for Interventional Pulmonology",
        "docs": "/docs",
        "health": "/health"
    }

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check the health status of the system."""
    try:
        orch = get_orchestrator()
        
        # Check Qdrant connection
        try:
            orch.retriever.qdrant.get_collections()
            qdrant_connected = True
        except:
            qdrant_connected = False
        
        # Check data availability
        chunks_loaded = len(orch.retriever.chunks) > 0
        embeddings_available = qdrant_connected  # Simplified check
        
        return HealthResponse(
            status="healthy" if all([qdrant_connected, chunks_loaded]) else "degraded",
            qdrant_connected=qdrant_connected,
            chunks_loaded=chunks_loaded,
            embeddings_available=embeddings_available,
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            qdrant_connected=False,
            chunks_loaded=False,
            embeddings_available=False,
            timestamp=datetime.now().isoformat()
        )

@app.post("/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """
    Process a medical query through the orchestration pipeline.
    
    This endpoint:
    1. Classifies the query (clinical, procedure, coding, emergency)
    2. Retrieves relevant documents
    3. Synthesizes a response with citations
    4. Applies safety checks
    """
    try:
        orch = get_orchestrator()
        
        # Process the query
        result = orch.process_query(request.query)
        
        # Return response
        return QueryResponse(
            query=request.query,
            response=result["response"],
            query_type=result["query_type"],
            is_emergency=result["is_emergency"],
            confidence_score=result["confidence_score"],
            citations=result["citations"],
            safety_flags=result["safety_flags"],
            needs_review=result["needs_review"],
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"Query processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/search", response_model=List[Dict[str, Any]])
async def search_documents(request: SearchRequest):
    """
    Perform direct search without orchestration.
    
    Useful for debugging or specific search needs.
    """
    try:
        orch = get_orchestrator()
        retriever = orch.retriever
        
        # Build filters
        filters = {}
        if request.authority_filter:
            filters["authority_tier"] = request.authority_filter
        if request.has_table is not None:
            filters["has_table"] = request.has_table
        if request.has_contraindication is not None:
            filters["has_contraindication"] = request.has_contraindication
        
        # Perform search based on type
        if request.search_type == "hybrid":
            results = retriever.retrieve(
                query=request.query,
                top_k=request.top_k,
                filters=filters if filters else None
            )
        elif request.search_type == "semantic":
            query_emb = retriever.query_encoder.encode(request.query, convert_to_numpy=True)
            semantic_results = retriever.semantic_search(query_emb, top_k=request.top_k, filters=filters)
            results = []
            for chunk_id, score in semantic_results:
                if chunk_id in retriever.chunk_map:
                    chunk = retriever.chunk_map[chunk_id]
                    results.append({
                        "chunk_id": chunk_id,
                        "text": chunk["text"][:500],
                        "score": score,
                        "doc_id": chunk.get("doc_id"),
                        "authority_tier": chunk.get("authority_tier"),
                        "year": chunk.get("year")
                    })
        elif request.search_type == "bm25":
            bm25_results = retriever.bm25_search(request.query, top_k=request.top_k)
            results = []
            for chunk_id, score in bm25_results:
                if chunk_id in retriever.chunk_map:
                    chunk = retriever.chunk_map[chunk_id]
                    results.append({
                        "chunk_id": chunk_id,
                        "text": chunk["text"][:500],
                        "score": score,
                        "doc_id": chunk.get("doc_id"),
                        "authority_tier": chunk.get("authority_tier"),
                        "year": chunk.get("year")
                    })
        else:  # exact
            exact_results = retriever.exact_match_search(request.query)
            results = []
            for chunk_id, score in exact_results:
                if chunk_id in retriever.chunk_map:
                    chunk = retriever.chunk_map[chunk_id]
                    results.append({
                        "chunk_id": chunk_id,
                        "text": chunk["text"][:500],
                        "score": score,
                        "doc_id": chunk.get("doc_id"),
                        "authority_tier": chunk.get("authority_tier"),
                        "year": chunk.get("year")
                    })
        
        # Format results for hybrid search
        if request.search_type == "hybrid":
            formatted_results = []
            for r in results:
                formatted_results.append({
                    "chunk_id": r.chunk_id,
                    "text": r.text[:500],
                    "score": r.score,
                    "doc_id": r.doc_id,
                    "section": r.section_title,
                    "authority_tier": r.authority_tier,
                    "evidence_level": r.evidence_level,
                    "year": r.year,
                    "doc_type": r.doc_type,
                    "has_table": r.has_table,
                    "has_contraindication": r.has_contraindication,
                    "has_dose_setting": r.has_dose_setting
                })
            return formatted_results
        else:
            return results
            
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/cpt/{cpt_code}")
async def get_cpt_info(cpt_code: str):
    """
    Get information about a specific CPT code.
    """
    try:
        if not cpt_code.isdigit() or len(cpt_code) != 5:
            raise HTTPException(status_code=400, detail="Invalid CPT code format")
        
        orch = get_orchestrator()
        retriever = orch.retriever
        
        # Search for exact CPT code
        if cpt_code in retriever.cpt_index:
            chunk_ids = retriever.cpt_index[cpt_code]
            results = []
            
            for chunk_id in chunk_ids[:5]:  # Limit to 5 results
                if chunk_id in retriever.chunk_map:
                    chunk = retriever.chunk_map[chunk_id]
                    results.append({
                        "chunk_id": chunk_id,
                        "text": chunk["text"],
                        "doc_id": chunk.get("doc_id"),
                        "section": chunk.get("section_title"),
                        "authority_tier": chunk.get("authority_tier"),
                        "year": chunk.get("year")
                    })
            
            return {
                "cpt_code": cpt_code,
                "found": True,
                "results": results
            }
        else:
            return {
                "cpt_code": cpt_code,
                "found": False,
                "results": []
            }
            
    except Exception as e:
        logger.error(f"CPT search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/statistics", response_model=StatisticsResponse)
async def get_statistics():
    """
    Get statistics about the indexed content.
    """
    try:
        orch = get_orchestrator()
        chunks = orch.retriever.chunks
        
        # Calculate statistics
        authority_dist = {}
        evidence_dist = {}
        doc_type_dist = {}
        years = []
        unique_docs = set()
        
        for chunk in chunks:
            # Authority tier
            at = chunk.get("authority_tier", "Unknown")
            authority_dist[at] = authority_dist.get(at, 0) + 1
            
            # Evidence level
            el = chunk.get("evidence_level", "Unknown")
            evidence_dist[el] = evidence_dist.get(el, 0) + 1
            
            # Doc type
            dt = chunk.get("doc_type", "Unknown")
            doc_type_dist[dt] = doc_type_dist.get(dt, 0) + 1
            
            # Year
            year = chunk.get("year")
            if year:
                years.append(year)
            
            # Unique documents
            doc_id = chunk.get("doc_id")
            if doc_id:
                unique_docs.add(doc_id)
        
        return StatisticsResponse(
            total_chunks=len(chunks),
            total_documents=len(unique_docs),
            authority_distribution=authority_dist,
            evidence_distribution=evidence_dist,
            doc_type_distribution=doc_type_dist,
            year_range={
                "min": min(years) if years else 0,
                "max": max(years) if years else 0
            }
        )
    except Exception as e:
        logger.error(f"Statistics calculation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/emergency")
async def check_emergency(query: str = Body(..., embed=True)):
    """
    Quick emergency check for a query.
    """
    try:
        orch = get_orchestrator()
        is_emergency = orch.retriever.detect_emergency(query)
        
        return {
            "query": query,
            "is_emergency": is_emergency,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Emergency check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Run with: uvicorn fastapi_app:app --reload --host 0.0.0.0 --port 8000
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)