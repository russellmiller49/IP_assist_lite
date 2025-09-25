# IP Assist Lite - Intelligent Medical Knowledge Assistant

An advanced AI-powered medical knowledge assistant that combines hybrid retrieval, medical concept linking, and GPT-5 reasoning to provide evidence-based answers to medical questions.

## 🏥 Overview

IP Assist Lite is designed to help medical professionals access comprehensive, evidence-based information from medical literature. It combines multiple AI technologies to provide accurate, cited responses with integrated medical concept linking.

## ✨ Key Features

- **🧠 Hybrid Retrieval**: Combines BM25 keyword search with semantic vector search
- **🔗 Medical Concept Linking**: UMLS integration via Medparse API
- **📚 Multi-Document Support**: Articles, textbooks, guidelines, and procedural manuals
- **🎯 Smart Citations**: Automatic citation generation with source verification
- **📊 Report Generation**: Structured medical reports with templates
- **🚀 GPT-5 Integration**: Advanced medical reasoning with OpenAI's latest models
- **🌐 Web Interface**: User-friendly Gradio interface

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Docker (for Qdrant)
- OpenAI API key
- 8GB+ RAM recommended

### Installation
```bash
git clone https://github.com/your-org/IP_assist_lite.git
cd IP_assist_lite
pip install -r requirements.txt
```

### Setup
```bash
# Start vector database
docker run -p 6333:6333 qdrant/qdrant

# Set environment variables
export OPENAI_API_KEY="your-openai-key"
export MEDPARSE_URL="http://127.0.0.1:8099"

# Start the application
./run.sh
```

### Access
Open http://localhost:7862 in your browser and start asking medical questions!

## 📚 Knowledge Base Types

### 🔬 Medical Articles
- **Content**: Journal articles, research papers, case studies
- **Optimization**: Abstract extraction, clinical terminology, evidence focus
- **Use Cases**: Evidence-based medicine, research findings, clinical studies

### 📖 Medical Textbooks
- **Content**: Comprehensive medical references, educational materials
- **Optimization**: Chapter structure, comprehensive coverage, cross-references
- **Use Cases**: Medical education, comprehensive knowledge, foundational concepts

### 📋 Clinical Guidelines
- **Content**: Practice guidelines, protocols, clinical standards
- **Optimization**: Recommendations, evidence levels, clinical algorithms
- **Use Cases**: Clinical decision support, protocol adherence, best practices

### 🛠️ Procedural Manuals
- **Content**: Equipment manuals, procedural guides, technical documentation
- **Optimization**: Step-by-step procedures, safety warnings, troubleshooting
- **Use Cases**: Procedural guidance, equipment operation, safety protocols

## 🏗️ Architecture

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

## 🔄 Building Your Knowledge Base

### Step 1: Organize Documents
```
data/raw/
├── articles/           # Medical journal articles
├── textbooks/         # Medical textbooks
├── guidelines/        # Clinical guidelines
└── manuals/           # Procedural manuals
```

### Step 2: Process with Medparse
```bash
# Start medparse API
cd ../medparse-docling
uvicorn api.main:app --reload --port 8099

# Process documents
./scripts/process_all_documents.sh
```

### Step 3: Import and Build
```bash
# Import processed documents
cp ../medparse-docling/output/*/*.json data/processed/

# Build knowledge base
./scripts/build_knowledge_base.sh
```

### Step 4: Test and Deploy
```bash
# Test retrieval
python scripts/test_retrieval.py "What are the indications for bronchoscopy?"

# Start the application
./run.sh
```

## 🎯 Usage Examples

### Basic Medical Questions
```
"What are the indications for bronchoscopy?"
"How do you perform EBUS-TBNA?"
"What are the complications of chest tube placement?"
"Describe the anatomy of the tracheobronchial tree"
```

### Advanced Queries
```
"In guidelines, what are the current recommendations for pneumonia treatment?"
"Show me textbook information about pulmonary anatomy"
"What procedures are indicated for hemoptysis according to recent articles?"
```

### Report Generation
```
"Generate a procedure note for flexible bronchoscopy"
"Create a structured report for EBUS findings"
```

## ⚙️ Configuration

### Environment Variables
```bash
# Core Configuration
export OPENAI_API_KEY="your-openai-key"
export IP_GPT5_MODEL="gpt-4o-mini"

# Vector Database
export QDRANT_HOST="localhost"
export QDRANT_PORT="6333"

# Medparse Integration
export MEDPARSE_URL="http://127.0.0.1:8099"
export MEDPARSE_API_KEY="your-medparse-key"
```

### Knowledge Base Configuration
```yaml
# configs/knowledge_base_config.yaml
retrieval:
  embedding_model: "ncbi/MedCPT-Query-Encoder"
  hybrid:
    bm25_weight: 0.3
    semantic_weight: 0.7

document_types:
  articles:
    chunk_size: 500
    focus_areas: ["diagnosis", "treatment"]
  textbooks:
    chunk_size: 1000
    focus_areas: ["anatomy", "physiology"]
```

## 🔧 API Integration

### Python Client
```python
import requests

def query_ip_assist(question):
    response = requests.post(
        "http://localhost:7862/api/query",
        json={"question": question}
    )
    return response.json()

# Example usage
result = query_ip_assist("What are the indications for EBUS?")
print(f"Answer: {result['response']}")
print(f"Citations: {len(result['citations'])}")
```

### EMR Integration
```python
class EMRIntegration:
    def get_procedure_guidance(self, patient_id, procedure_code):
        # Get patient data from EMR
        patient_data = self.emr.get_patient(patient_id)
        
        # Query IP Assist for guidance
        query = f"Considerations for {procedure_code} in patient with {patient_data['conditions']}"
        guidance = self.ip_assist.query(query)
        
        return guidance
```

## 🧪 Testing

```bash
# Run all tests
pytest

# Run specific test categories
pytest tests/test_retrieval.py
pytest tests/test_orchestrator.py
pytest tests/test_medparse_integration.py

# Run with coverage
pytest --cov=src --cov-report=html
```

## 🚀 Deployment

### Docker Deployment
```bash
# Build image
docker build -t ip-assist-lite .

# Run with Docker Compose
docker-compose up -d
```

### Production Deployment
```bash
# Using Gunicorn (for API mode)
gunicorn app:app --bind 0.0.0.0:7862 --workers 4

# Using systemd service
sudo systemctl enable ip-assist-lite
sudo systemctl start ip-assist-lite
```

### HuggingFace Spaces
```bash
cd t4_deployment/
# Follow deployment instructions in README
```

## 🔗 Integration with Medparse

IP Assist Lite works seamlessly with Medparse for enhanced medical document processing:

1. **Document Processing**: Medparse extracts and structures medical content
2. **Concept Linking**: UMLS concepts are linked to medical terms
3. **Knowledge Integration**: Processed documents are imported into IP Assist Lite
4. **Enhanced Retrieval**: Medical concepts improve search accuracy
5. **Smart Citations**: Citations include concept-linked metadata

## 📊 Monitoring and Analytics

### Performance Metrics
- Query response time
- Retrieval accuracy
- User satisfaction scores
- System resource usage

### Health Checks
```bash
# Check system health
curl http://localhost:7862/health

# Monitor component status
python scripts/health_check.py
```

## 🎓 Medical Specialties

### Pulmonology Focus
- Bronchoscopy procedures
- Pleural interventions
- Airway management
- Lung biopsy techniques

### Interventional Procedures
- Image-guided procedures
- Minimally invasive techniques
- Safety protocols
- Equipment operation

### Evidence-Based Medicine
- Clinical guidelines
- Research findings
- Best practices
- Quality metrics

## 📖 Documentation

- **[Technical Documentation](TECHNICAL_DOCUMENTATION.md)**: Detailed architecture and API reference
- **[User Guide](USER_GUIDE.md)**: Step-by-step usage instructions
- **[Medparse Integration Guide](docs/medparse_integration/README.md)**: Integration documentation

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

- **Issues**: [GitHub Issues](https://github.com/your-org/IP_assist_lite/issues)
- **Documentation**: See documentation files in the repository
- **Community**: Join our medical AI community discussions

## 🔄 Changelog

### Latest Version
- ✅ Enhanced Medparse integration
- ✅ Structured document type processing
- ✅ Improved hybrid retrieval
- ✅ Smart citation system
- ✅ Report generation capabilities
- ✅ Comprehensive documentation

---

**Ready to transform medical knowledge access with AI-powered intelligence!** 🏥🧠✨