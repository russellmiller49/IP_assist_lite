# IP Assist Lite - Technical Documentation

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [System Components](#system-components)
3. [API Reference](#api-reference)
4. [Knowledge Base Architecture](#knowledge-base-architecture)
5. [Medparse Integration](#medparse-integration)
6. [Development Guide](#development-guide)
7. [Deployment](#deployment)
8. [Troubleshooting](#troubleshooting)

## Architecture Overview

### High-Level Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Gradio UI     │    │  Enhanced       │    │   Medparse      │
│   (Port 7862)   │◄──►│  Orchestrator   │◄──►│   API           │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Knowledge     │    │  Hybrid         │    │   UMLS          │
│   Base          │    │  Retriever      │    │   Concepts      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Qdrant        │    │  BM25 +         │    │   GPT-5         │
│   Vector DB     │    │  Semantic       │    │   Medical       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Data Flow

1. **Query Processing**: User query → Query normalization → Intent detection
2. **Retrieval**: Hybrid search (BM25 + Semantic) → Document ranking → Context selection
3. **Enhancement**: Medparse concept linking → Smart citations → Context enrichment
4. **Generation**: GPT-5 medical reasoning → Structured response → Report generation
5. **Output**: Formatted response → Citations → Optional synoptic report

## System Components

### Core Modules

#### 1. Enhanced Orchestrator (`src/orchestrator/`)
- **Purpose**: Central coordination of all system components
- **Key Features**: Query processing, context management, response generation
- **Files**: `enhanced_orchestrator.py`, `smart_citations.py`

#### 2. Hybrid Retriever (`src/retrieval/`)
- **Purpose**: Multi-modal document retrieval
- **Key Features**: BM25 + semantic search, document ranking, filtering
- **Files**: `hybrid_retriever.py`, `query_normalizer.py`

#### 3. LLM Integration (`src/llm/`)
- **Purpose**: GPT-5 medical reasoning and generation
- **Key Features**: Responses API, tool calling, medical specialization
- **Files**: `gpt5_medical.py`, `llm_client.py`

#### 4. Medparse Integration (`src/adapters/`)
- **Purpose**: Medical concept linking and enhancement
- **Key Features**: UMLS concept extraction, semantic filtering
- **Files**: `medparse_client.py`, `openai_responses.py`

#### 5. Reporting System (`src/reporting/`)
- **Purpose**: Structured medical report generation
- **Key Features**: Synoptic reports, template rendering, validation
- **Files**: `integration.py`, `llm_structurer.py`, `render.py`

### Data Architecture

```
data/
├── raw/                    # Raw input documents
│   ├── articles/           # Medical journal articles
│   ├── textbooks/         # Medical textbooks
│   ├── guidelines/        # Clinical guidelines
│   └── manuals/           # Procedural manuals
├── processed/             # Processed documents from medparse
├── chunks/               # Text chunks for retrieval
├── vectors/              # Embeddings and vector data
├── term_index/          # BM25 term indices
└── templates/           # Report templates
```

## API Reference

### Core Endpoints

#### Query Processing
```python
# src/orchestrator/enhanced_orchestrator.py
class EnhancedOrchestrator:
    async def process_query(
        self, 
        query: str, 
        context: Optional[Dict] = None
    ) -> Dict:
        """
        Process user query and generate response.
        
        Args:
            query: User's medical question
            context: Optional context from previous interactions
            
        Returns:
            Dict with response, citations, and metadata
        """
```

#### Retrieval System
```python
# src/retrieval/hybrid_retriever.py
class HybridRetriever:
    def search(
        self, 
        query: str, 
        top_k: int = 50,
        document_types: List[str] = None
    ) -> List[Dict]:
        """
        Hybrid search combining BM25 and semantic retrieval.
        
        Args:
            query: Search query
            top_k: Number of results to return
            document_types: Filter by document types
            
        Returns:
            List of ranked search results
        """
```

#### Medparse Integration
```python
# src/adapters/medparse_client.py
class MedparseClient:
    async def link_concepts(
        self, 
        text: str, 
        document_type: str = "article"
    ) -> Dict:
        """
        Link medical concepts using Medparse API.
        
        Args:
            text: Text to analyze
            document_type: Type of document for context
            
        Returns:
            Dict with UMLS concepts and metadata
        """
```

### Configuration API

```python
# configs/knowledge_base_config.yaml
class KnowledgeBaseConfig:
    def __init__(self, config_path: str):
        """Load configuration from YAML file."""
        
    def get_document_settings(self, doc_type: str) -> Dict:
        """Get processing settings for document type."""
        
    def get_retrieval_settings(self) -> Dict:
        """Get hybrid retrieval configuration."""
```

## Knowledge Base Architecture

### Vector Database (Qdrant)

```python
# Vector collection structure
collections = {
    "ip_articles": {
        "vectors": 768,  # MedCPT embedding dimension
        "distance": "Cosine",
        "payload_schema": {
            "chunk_id": "keyword",
            "document_type": "keyword",
            "section": "keyword",
            "metadata": "json"
        }
    },
    "ip_textbooks": {
        "vectors": 768,
        "distance": "Cosine",
        "payload_schema": {
            "chunk_id": "keyword",
            "chapter": "keyword",
            "page": "integer",
            "metadata": "json"
        }
    }
}
```

### BM25 Index

```python
# Term indexing structure
term_index = {
    "articles": {
        "terms": {},  # term -> document frequency
        "documents": {},  # doc_id -> term frequencies
        "idf": {},  # term -> inverse document frequency
        "avg_doc_length": float
    },
    "textbooks": {
        # Similar structure for textbooks
    }
}
```

### Chunking Strategy

```python
# Document-type-specific chunking
chunking_strategies = {
    "articles": {
        "chunk_size": 500,
        "overlap": 100,
        "strategy": "semantic",
        "preserve_sections": True
    },
    "textbooks": {
        "chunk_size": 1000,
        "overlap": 200,
        "strategy": "hierarchical",
        "preserve_chapters": True
    },
    "guidelines": {
        "chunk_size": 750,
        "overlap": 150,
        "strategy": "recommendation_based",
        "preserve_algorithms": True
    },
    "manuals": {
        "chunk_size": 600,
        "overlap": 120,
        "strategy": "procedure_based",
        "preserve_steps": True
    }
}
```

## Medparse Integration

### Integration Architecture

```python
# src/adapters/medparse_client.py
class MedparseClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key
        self.session = aiohttp.ClientSession()
    
    async def enhance_context(self, context: List[Dict]) -> List[Dict]:
        """Enhance retrieved context with medical concepts."""
        enhanced_context = []
        
        for chunk in context:
            # Link UMLS concepts
            concepts = await self.link_concepts(
                chunk["text"], 
                chunk.get("document_type", "article")
            )
            
            # Add concept metadata
            chunk["umls_concepts"] = concepts.get("umls_links", [])
            chunk["processing_metadata"] = {
                "medparse_version": concepts.get("version"),
                "processing_time": concepts.get("processing_time"),
                "confidence_threshold": 0.8
            }
            
            enhanced_context.append(chunk)
        
        return enhanced_context
```

### Concept Filtering

```python
# Semantic filtering by document type
concept_filters = {
    "articles": {
        "allowed_semantic_types": [
            "Disease or Syndrome",
            "Therapeutic or Preventive Procedure",
            "Pharmacologic Substance",
            "Clinical Attribute"
        ],
        "confidence_threshold": 0.8
    },
    "textbooks": {
        "allowed_semantic_types": [
            "Anatomical Structure",
            "Physiologic Function",
            "Disease or Syndrome",
            "Body System"
        ],
        "confidence_threshold": 0.7
    }
}
```

## Development Guide

### Setting Up Development Environment

```bash
# Clone repository
git clone https://github.com/your-org/IP_assist_lite.git
cd IP_assist_lite

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your configuration

# Start Qdrant (using Docker)
docker run -p 6333:6333 qdrant/qdrant

# Start Medparse API
cd ../ip_knowledge/medparse/medparse-docling
uvicorn api.main:app --reload --port 8099

# Return to IP_assist_lite
cd ../IP_assist_lite

# Start the application
./run.sh
```

### Testing

```bash
# Run unit tests
pytest tests/

# Run integration tests
pytest tests/integration/

# Run specific test file
pytest tests/test_hybrid_retriever.py

# Run with coverage
pytest --cov=src --cov-report=html

# Run performance tests
pytest tests/performance/
```

### Code Quality

```bash
# Format code
black src/ tests/

# Lint code
flake8 src/ tests/

# Type checking
mypy src/

# Security check
bandit -r src/

# Import sorting
isort src/ tests/
```

### Adding New Features

#### 1. Adding New Document Types

```python
# 1. Update configuration
# configs/knowledge_base_config.yaml
document_types:
  new_type:
    chunk_size: 800
    chunk_overlap: 160
    strategy: "custom"
    focus_terms: ["custom", "terms"]

# 2. Update retriever
# src/retrieval/hybrid_retriever.py
def get_collection_name(self, doc_type: str) -> str:
    collection_mapping = {
        "articles": "ip_articles",
        "textbooks": "ip_textbooks",
        "guidelines": "ip_guidelines",
        "manuals": "ip_manuals",
        "new_type": "ip_new_type"  # Add new mapping
    }
    return collection_mapping.get(doc_type, "ip_articles")

# 3. Update processing scripts
# scripts/build_knowledge_base.sh
# Add processing logic for new document type
```

#### 2. Adding New LLM Models

```python
# src/llm/gpt5_medical.py
class GPT5Medical:
    def __init__(self, model: str = "gpt-5-mini"):
        supported_models = [
            "gpt-5-mini",
            "gpt-5",
            "gpt-4o-mini",
            "new-model"  # Add new model
        ]
        
        if model not in supported_models:
            raise ValueError(f"Unsupported model: {model}")
        
        self.model = model
```

### Performance Optimization

#### 1. Caching Strategy

```python
# src/adapters/medparse_client.py
from functools import lru_cache
import asyncio

class MedparseClient:
    def __init__(self):
        self._concept_cache = {}
        self._cache_lock = asyncio.Lock()
    
    @lru_cache(maxsize=1000)
    def _cached_concept_lookup(self, text_hash: str) -> Dict:
        """Cache concept lookups by text hash."""
        return self._concept_cache.get(text_hash)
```

#### 2. Batch Processing

```python
# src/orchestrator/enhanced_orchestrator.py
async def process_queries_batch(self, queries: List[str]) -> List[Dict]:
    """Process multiple queries concurrently."""
    tasks = [self.process_query(query) for query in queries]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
```

#### 3. Memory Management

```python
# src/retrieval/hybrid_retriever.py
import gc
import psutil

class HybridRetriever:
    def __init__(self):
        self.memory_threshold = 0.85  # 85% memory usage threshold
    
    def _check_memory_usage(self):
        """Monitor memory usage and trigger cleanup if needed."""
        memory_percent = psutil.virtual_memory().percent / 100
        if memory_percent > self.memory_threshold:
            gc.collect()
            logger.warning(f"Memory usage high: {memory_percent:.1%}")
```

## Deployment

### Docker Deployment

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 7862

# Start application
CMD ["python", "app.py"]
```

```bash
# Build and run
docker build -t ip-assist-lite .
docker run -p 7862:7862 \
  -e OPENAI_API_KEY=your-key \
  -e MEDPARSE_URL=http://medparse:8099 \
  ip-assist-lite
```

### Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  qdrant:
    image: qdrant/qdrant
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage

  medparse:
    build: ../ip_knowledge/medparse/medparse-docling
    ports:
      - "8099:8099"
    environment:
      - UMLS_API_KEY=${UMLS_API_KEY}
      - NCBI_API_KEY=${NCBI_API_KEY}
    depends_on:
      - qdrant

  ip-assist-lite:
    build: .
    ports:
      - "7862:7862"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - QDRANT_HOST=qdrant
      - MEDPARSE_URL=http://medparse:8099
    depends_on:
      - qdrant
      - medparse

volumes:
  qdrant_data:
```

### Production Deployment

#### Using Kubernetes

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ip-assist-lite
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ip-assist-lite
  template:
    metadata:
      labels:
        app: ip-assist-lite
    spec:
      containers:
      - name: ip-assist-lite
        image: ip-assist-lite:latest
        ports:
        - containerPort: 7862
        env:
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: api-keys
              key: openai-key
        - name: QDRANT_HOST
          value: "qdrant-service"
        - name: MEDPARSE_URL
          value: "http://medparse-service:8099"
        resources:
          requests:
            memory: "2Gi"
            cpu: "1"
          limits:
            memory: "4Gi"
            cpu: "2"
```

#### Load Balancing

```yaml
# k8s/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: ip-assist-lite-service
spec:
  selector:
    app: ip-assist-lite
  ports:
  - port: 80
    targetPort: 7862
  type: LoadBalancer
```

### Monitoring and Logging

```python
# src/monitoring/metrics.py
from prometheus_client import Counter, Histogram, Gauge
import time

# Metrics
query_counter = Counter('queries_total', 'Total number of queries')
response_time = Histogram('response_time_seconds', 'Response time')
active_users = Gauge('active_users', 'Number of active users')

class MetricsCollector:
    def record_query(self, query_type: str):
        query_counter.labels(type=query_type).inc()
    
    def record_response_time(self, duration: float):
        response_time.observe(duration)
    
    def update_active_users(self, count: int):
        active_users.set(count)
```

## Troubleshooting

### Common Issues

#### 1. Qdrant Connection Issues

```python
# Check Qdrant connectivity
def check_qdrant_connection():
    try:
        client = QdrantClient(host="localhost", port=6333)
        collections = client.get_collections()
        print(f"Connected to Qdrant. Collections: {len(collections.collections)}")
        return True
    except Exception as e:
        print(f"Qdrant connection failed: {e}")
        return False
```

#### 2. Medparse API Issues

```python
# Check Medparse connectivity
async def check_medparse_connection():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8099/healthz") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"Medparse API healthy: {data}")
                    return True
    except Exception as e:
        print(f"Medparse API connection failed: {e}")
        return False
```

#### 3. Memory Issues

```python
# Monitor memory usage
def check_memory_usage():
    import psutil
    memory = psutil.virtual_memory()
    print(f"Memory usage: {memory.percent}%")
    print(f"Available memory: {memory.available / (1024**3):.1f} GB")
    
    if memory.percent > 90:
        print("WARNING: High memory usage detected")
        return False
    return True
```

#### 4. Performance Issues

```python
# Profile query processing
import cProfile
import pstats

def profile_query_processing(query: str):
    """Profile query processing performance."""
    profiler = cProfile.Profile()
    profiler.enable()
    
    # Process query
    result = orchestrator.process_query(query)
    
    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    stats.print_stats(10)  # Top 10 functions
    
    return result
```

### Debug Mode

```python
# Enable debug logging
import logging

def enable_debug_mode():
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Enable debug for specific modules
    logging.getLogger('src.orchestrator').setLevel(logging.DEBUG)
    logging.getLogger('src.retrieval').setLevel(logging.DEBUG)
    logging.getLogger('src.adapters').setLevel(logging.DEBUG)
```

### Health Checks

```python
# Comprehensive health check
async def health_check():
    """Perform comprehensive system health check."""
    checks = {
        "qdrant": check_qdrant_connection(),
        "medparse": await check_medparse_connection(),
        "memory": check_memory_usage(),
        "openai": check_openai_connection(),
        "knowledge_base": check_knowledge_base_integrity()
    }
    
    all_healthy = all(checks.values())
    
    return {
        "status": "healthy" if all_healthy else "unhealthy",
        "checks": checks,
        "timestamp": time.time()
    }
```
