# IP Assist Lite - User Guide

## Table of Contents
1. [Getting Started](#getting-started)
2. [Building Your Knowledge Base](#building-your-knowledge-base)
3. [Using the Application](#using-the-application)
4. [Configuration](#configuration)
5. [Advanced Features](#advanced-features)
6. [Integration Guide](#integration-guide)
7. [Best Practices](#best-practices)
8. [Examples](#examples)
9. [FAQ](#faq)

## Getting Started

### Prerequisites

- Python 3.11+
- Docker (for Qdrant vector database)
- OpenAI API key
- UMLS API key (optional, for enhanced medical concept linking)
- 8GB+ RAM recommended
- GPU support (optional, for faster processing)

### Quick Installation

```bash
# 1. Clone the repository
git clone https://github.com/your-org/IP_assist_lite.git
cd IP_assist_lite

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start required services
docker run -p 6333:6333 qdrant/qdrant  # Vector database

# 4. Set up environment variables
export OPENAI_API_KEY="your-openai-key"
export MEDPARSE_URL="http://127.0.0.1:8099"  # If using medparse
export MEDPARSE_API_KEY="your-medparse-key"

# 5. Start the application
./run.sh
```

### First Run

1. **Access the Interface**: Open http://localhost:7862 in your browser
2. **Test Basic Functionality**: Try asking "What are the indications for bronchoscopy?"
3. **Check System Status**: Verify all components are running correctly

## Building Your Knowledge Base

### Overview

IP Assist Lite uses a structured approach to building medical knowledge bases from different document types:

- **Articles**: Medical journal articles, research papers, case studies
- **Textbooks**: Medical textbooks, comprehensive references
- **Guidelines**: Clinical practice guidelines, protocols, standards  
- **Manuals**: Procedural manuals, technical documentation

### Step-by-Step Process

#### 1. Prepare Your Documents

Organize your medical documents by type:

```
data/raw/
├── articles/           # Medical journal articles
│   ├── research_paper_1.pdf
│   ├── case_study_2.pdf
│   └── clinical_trial_3.pdf
├── textbooks/         # Medical textbooks
│   ├── medical_textbook_ch1.pdf
│   ├── anatomy_reference.pdf
│   └── pathology_guide.pdf
├── guidelines/        # Clinical guidelines
│   ├── treatment_guideline.pdf
│   ├── diagnostic_protocol.pdf
│   └── safety_standards.pdf
└── manuals/          # Procedural manuals
    ├── equipment_manual.pdf
    ├── procedure_guide.pdf
    └── troubleshooting.pdf
```

#### 2. Process Documents with Medparse

```bash
# Start medparse API (in separate terminal)
cd ../ip_knowledge/medparse/medparse-docling
uvicorn api.main:app --reload --port 8099

# Process your documents
./scripts/process_all_documents.sh

# Or process specific types
./scripts/process_articles.sh
./scripts/process_textbooks.sh
./scripts/process_guidelines.sh
./scripts/process_manuals.sh
```

#### 3. Import Processed Documents

```bash
# Copy processed documents to IP Assist Lite
cp ../ip_knowledge/medparse/medparse-docling/output/articles/*.json data/processed/articles/
cp ../ip_knowledge/medparse/medparse-docling/output/textbooks/*.json data/processed/textbooks/
cp ../ip_knowledge/medparse/medparse-docling/output/guidelines/*.json data/processed/guidelines/
cp ../ip_knowledge/medparse/medparse-docling/output/manuals/*.json data/processed/manuals/
```

#### 4. Build Knowledge Base

```bash
# Build the complete knowledge base
./scripts/build_knowledge_base.sh
```

This script will:
- Extract and chunk text from processed documents
- Generate embeddings using MedCPT
- Build BM25 indices for keyword search
- Create Qdrant collections for semantic search
- Generate citation indices

#### 5. Verify Knowledge Base

```bash
# Check knowledge base statistics
python scripts/knowledge_base_stats.py

# Test retrieval
python scripts/test_retrieval.py "What are the indications for EBUS?"
```

### Document Processing Options

#### Articles Processing
- **Focus**: Abstracts, references, clinical terminology
- **Chunk Size**: 500 tokens (optimal for research findings)
- **Features**: Evidence extraction, citation linking, clinical concept focus

#### Textbooks Processing  
- **Focus**: Chapters, figures, comprehensive coverage
- **Chunk Size**: 1000 tokens (optimal for educational content)
- **Features**: Hierarchical structure, cross-references, comprehensive terminology

#### Guidelines Processing
- **Focus**: Recommendations, evidence levels, algorithms
- **Chunk Size**: 750 tokens (optimal for protocols)
- **Features**: Recommendation extraction, evidence grading, algorithm preservation

#### Manuals Processing
- **Focus**: Procedures, steps, safety warnings
- **Chunk Size**: 600 tokens (optimal for procedural content)
- **Features**: Step-by-step extraction, safety highlighting, troubleshooting guides

## Using the Application

### Web Interface

#### Main Query Interface
1. **Ask Questions**: Type medical questions in natural language
2. **Get Responses**: Receive evidence-based answers with citations
3. **View Sources**: Click on citations to see source documents
4. **Generate Reports**: Create structured medical reports

#### Query Examples
```
"What are the indications for bronchoscopy?"
"How do you perform EBUS-TBNA?"
"What are the complications of chest tube placement?"
"Describe the anatomy of the tracheobronchial tree"
"What are the current guidelines for pneumonia treatment?"
```

#### Advanced Query Features
- **Document Type Filtering**: "In textbooks, what is the anatomy of..."
- **Specific Procedures**: "Show me the procedure for..."
- **Evidence Levels**: "What does the evidence say about..."
- **Safety Information**: "What are the safety considerations for..."

### Response Features

#### Smart Citations
- **Automatic Citation**: All responses include relevant citations
- **Source Verification**: Citations link back to original documents
- **Evidence Grading**: Citations show evidence levels when available
- **Multiple Sources**: Responses combine information from multiple documents

#### Medical Concept Linking
- **UMLS Integration**: Medical terms linked to standard concepts
- **Concept Definitions**: Hover over terms for definitions
- **Related Concepts**: Explore related medical concepts
- **Semantic Relationships**: Understand relationships between concepts

#### Report Generation
- **Synoptic Reports**: Generate structured medical reports
- **Template-Based**: Use predefined templates for consistency
- **Customizable**: Modify templates for specific needs
- **Export Options**: Export reports in various formats

## Configuration

### Basic Configuration

Edit `configs/knowledge_base_config.yaml`:

```yaml
# Document Processing
documents:
  pdf_directory: "data/raw"
  output_directory: "data/processed"
  
# Retrieval Configuration  
retrieval:
  embedding_model: "ncbi/MedCPT-Query-Encoder"
  hybrid:
    bm25_weight: 0.3
    semantic_weight: 0.7
    rerank_top_k: 20

# LLM Configuration
llm:
  model: "gpt-4o-mini"
  temperature: 0.1
  max_tokens: 4000

# Medparse Integration
medparse:
  url: "http://127.0.0.1:8099"
  api_key: "your-secret-key"
  enable_concept_linking: true
```

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

# Optional: UMLS Integration
export UMLS_API_KEY="your-umls-key"
export NCBI_API_KEY="your-ncbi-key"
export NCBI_EMAIL="your-email@example.com"
```

### Document Type Customization

```yaml
# Customize processing for each document type
document_types:
  articles:
    chunk_size: 500
    chunk_overlap: 100
    retrieval_weight: 0.8
    focus_areas: ["diagnosis", "treatment", "outcomes"]
  
  textbooks:
    chunk_size: 1000
    chunk_overlap: 200
    retrieval_weight: 0.7
    focus_areas: ["anatomy", "physiology", "pathology"]
  
  guidelines:
    chunk_size: 750
    chunk_overlap: 150
    retrieval_weight: 0.9
    focus_areas: ["recommendations", "evidence", "protocols"]
  
  manuals:
    chunk_size: 600
    chunk_overlap: 120
    retrieval_weight: 0.8
    focus_areas: ["procedures", "steps", "safety"]
```

## Advanced Features

### Custom Medical Specialties

#### Pulmonology Focus
```yaml
specialty_config:
  name: "pulmonology"
  focus_terms:
    - "bronchoscopy"
    - "lung biopsy"
    - "pleural procedures"
    - "airway management"
  document_priorities:
    - guidelines: 0.9
    - articles: 0.8
    - textbooks: 0.7
    - manuals: 0.8
```

#### Cardiology Focus
```yaml
specialty_config:
  name: "cardiology"
  focus_terms:
    - "cardiac catheterization"
    - "echocardiography"
    - "coronary intervention"
    - "heart failure"
  document_priorities:
    - guidelines: 0.9
    - articles: 0.8
    - textbooks: 0.6
    - manuals: 0.7
```

### Multi-Language Support

```yaml
language_config:
  primary: "en"
  supported: ["en", "es", "fr", "de"]
  translation_service: "openai"
  medical_terminology: "umls_multilingual"
```

### Custom Report Templates

```yaml
# Create custom report templates
report_templates:
  procedure_note:
    sections:
      - patient_info
      - indication
      - procedure_details
      - findings
      - complications
      - recommendations
    
  pathology_report:
    sections:
      - specimen_info
      - gross_description
      - microscopic_findings
      - diagnosis
      - comments
```

## Integration Guide

### API Integration

```python
import requests
import json

class IPAssistClient:
    def __init__(self, base_url="http://localhost:7862"):
        self.base_url = base_url
    
    def query(self, question, document_types=None):
        """Send a query to IP Assist Lite."""
        payload = {
            "question": question,
            "document_types": document_types or ["articles", "guidelines"]
        }
        
        response = requests.post(
            f"{self.base_url}/api/query",
            json=payload
        )
        
        return response.json()
    
    def generate_report(self, template, data):
        """Generate a structured report."""
        payload = {
            "template": template,
            "data": data
        }
        
        response = requests.post(
            f"{self.base_url}/api/report",
            json=payload
        )
        
        return response.json()

# Example usage
client = IPAssistClient()
result = client.query("What are the indications for EBUS?")
print(f"Answer: {result['response']}")
print(f"Citations: {len(result['citations'])}")
```

### EMR Integration

```python
# Example EMR integration
class EMRIntegration:
    def __init__(self, emr_client, ip_assist_client):
        self.emr = emr_client
        self.ip_assist = ip_assist_client
    
    def get_procedure_guidance(self, patient_id, procedure_code):
        """Get procedure guidance based on patient data."""
        # Get patient data from EMR
        patient_data = self.emr.get_patient(patient_id)
        
        # Query IP Assist for procedure guidance
        query = f"What are the considerations for {procedure_code} in a patient with {patient_data['conditions']}?"
        
        guidance = self.ip_assist.query(query, document_types=["guidelines", "manuals"])
        
        # Generate procedure note template
        template_data = {
            "patient": patient_data,
            "procedure": procedure_code,
            "guidance": guidance['response'],
            "citations": guidance['citations']
        }
        
        return self.ip_assist.generate_report("procedure_note", template_data)
```

### PACS Integration

```python
# Example PACS integration for image-guided procedures
class PACSIntegration:
    def __init__(self, pacs_client, ip_assist_client):
        self.pacs = pacs_client
        self.ip_assist = ip_assist_client
    
    def get_imaging_guidance(self, study_id):
        """Get guidance based on imaging findings."""
        # Get imaging data from PACS
        study = self.pacs.get_study(study_id)
        findings = study['findings']
        
        # Query IP Assist for imaging-guided procedure guidance
        query = f"What procedures are indicated for {findings}?"
        
        guidance = self.ip_assist.query(query, document_types=["guidelines", "articles"])
        
        return guidance
```

## Best Practices

### Document Management

1. **Quality Control**
   - Use high-quality, text-based PDFs
   - Verify document completeness before processing
   - Regularly update knowledge base with new literature

2. **Organization**
   - Maintain consistent document naming conventions
   - Use appropriate document type classifications
   - Keep raw and processed documents separate

3. **Version Control**
   - Track document versions and updates
   - Maintain audit trails for knowledge base changes
   - Regular backups of processed data

### Query Optimization

1. **Effective Questioning**
   - Use specific medical terminology
   - Include relevant context (patient population, setting)
   - Specify document types when appropriate

2. **Response Evaluation**
   - Always review citations for accuracy
   - Cross-reference with primary sources
   - Consider evidence levels and quality

3. **Iterative Refinement**
   - Refine queries based on initial results
   - Use follow-up questions for clarification
   - Provide feedback to improve system performance

### System Maintenance

1. **Regular Updates**
   - Update knowledge base monthly with new literature
   - Monitor system performance and optimize as needed
   - Keep software dependencies up to date

2. **Quality Assurance**
   - Regular testing of key clinical questions
   - Validation of responses against known standards
   - User feedback collection and analysis

3. **Security**
   - Secure API keys and credentials
   - Regular security audits
   - HIPAA compliance for patient data

## Examples

### Example 1: Building a Pulmonology Knowledge Base

```bash
# 1. Organize pulmonology documents
mkdir -p data/raw/{articles,textbooks,guidelines,manuals}
cp pulmonology_articles/* data/raw/articles/
cp pulmonology_textbooks/* data/raw/textbooks/
cp bts_guidelines/* data/raw/guidelines/
cp bronchoscopy_manuals/* data/raw/manuals/

# 2. Process through medparse
cd ../ip_knowledge/medparse/medparse-docling
./scripts/process_all_documents.sh

# 3. Import to IP Assist Lite
cd ../IP_assist_lite
cp ../ip_knowledge/medparse/medparse-docling/output/*/*.json data/processed/

# 4. Build knowledge base
./scripts/build_knowledge_base.sh

# 5. Test with pulmonology queries
echo "Testing pulmonology knowledge base..."
python scripts/test_retrieval.py "What are the indications for bronchoscopy?"
python scripts/test_retrieval.py "How do you perform EBUS-TBNA?"
python scripts/test_retrieval.py "What are the complications of pleural biopsy?"
```

### Example 2: Custom Medical Specialty Configuration

```python
# Create custom configuration for interventional cardiology
specialty_config = {
    "name": "interventional_cardiology",
    "focus_terms": [
        "cardiac catheterization",
        "percutaneous coronary intervention",
        "transcatheter aortic valve replacement",
        "coronary angiography"
    ],
    "document_weights": {
        "guidelines": 0.9,  # High weight for evidence-based guidelines
        "articles": 0.8,    # High weight for research evidence
        "textbooks": 0.6,   # Lower weight for general education
        "manuals": 0.8      # High weight for procedural guidance
    },
    "retrieval_settings": {
        "chunk_size": 600,
        "overlap": 120,
        "top_k": 30
    }
}

# Apply configuration
with open("configs/specialty_cardiology.yaml", "w") as f:
    yaml.dump(specialty_config, f)

# Build knowledge base with specialty focus
python scripts/build_knowledge_base.py --config configs/specialty_cardiology.yaml
```

### Example 3: Integration with Clinical Workflow

```python
# Clinical decision support integration
class ClinicalDecisionSupport:
    def __init__(self):
        self.ip_assist = IPAssistClient()
        self.emr = EMRClient()
    
    def get_procedure_recommendations(self, patient_id, symptoms):
        """Get procedure recommendations based on patient symptoms."""
        # Get patient history
        patient = self.emr.get_patient(patient_id)
        
        # Formulate clinical query
        query = f"""
        Patient with {symptoms} and history of {patient['medical_history']}.
        What diagnostic procedures are indicated?
        Consider contraindications and patient factors.
        """
        
        # Query IP Assist
        response = self.ip_assist.query(
            query, 
            document_types=["guidelines", "articles"]
        )
        
        # Format recommendations
        recommendations = {
            "primary_recommendations": response['response'],
            "evidence_level": self.extract_evidence_level(response),
            "contraindications": self.extract_contraindications(response),
            "citations": response['citations'],
            "confidence_score": response['confidence']
        }
        
        return recommendations
    
    def generate_procedure_note(self, procedure_code, findings):
        """Generate structured procedure note."""
        template_data = {
            "procedure_code": procedure_code,
            "findings": findings,
            "timestamp": datetime.now(),
            "physician": self.get_current_physician()
        }
        
        return self.ip_assist.generate_report("procedure_note", template_data)

# Usage example
cds = ClinicalDecisionSupport()
recommendations = cds.get_procedure_recommendations(
    patient_id="12345",
    symptoms="chronic cough, hemoptysis"
)
print(f"Recommended procedures: {recommendations['primary_recommendations']}")
```

## FAQ

### General Questions

**Q: What types of medical documents can I use?**
A: IP Assist Lite supports PDFs and text files including medical journal articles, textbooks, clinical guidelines, and procedural manuals. Documents should be text-based (not scanned images) for best results.

**Q: How accurate are the responses?**
A: Response accuracy depends on the quality of your knowledge base. The system provides citations for all answers, allowing you to verify information against primary sources. Always validate clinical decisions with current guidelines and professional judgment.

**Q: Can I use IP Assist Lite without medparse?**
A: Yes, but you'll miss enhanced medical concept linking and UMLS integration. The system will still work with basic text processing and retrieval.

**Q: How much computational resources do I need?**
A: Minimum 8GB RAM, recommended 16GB+. GPU acceleration is optional but improves performance. Vector database (Qdrant) requires additional storage space.

### Technical Questions

**Q: How do I update my knowledge base?**
A: Add new documents to the appropriate `data/raw/` directories, process them through medparse, then run `./scripts/build_knowledge_base.sh` to update the knowledge base.

**Q: Can I customize the chunking strategy?**
A: Yes, modify the chunking settings in `configs/knowledge_base_config.yaml`. Different document types can have different chunk sizes and overlap settings.

**Q: How do I backup my knowledge base?**
A: Backup the `data/` directory and Qdrant collections. You can export Qdrant collections using their API or backup the Docker volume.

**Q: Can I run multiple instances?**
A: Yes, but each instance needs its own Qdrant database and port configuration. Use Docker Compose or Kubernetes for orchestration.

### Integration Questions

**Q: Can I integrate with my EMR system?**
A: Yes, IP Assist Lite provides REST APIs that can be integrated with EMR systems. See the Integration Guide for examples.

**Q: Does it support FHIR?**
A: Not directly, but you can build FHIR adapters using the API integration patterns shown in the examples.

**Q: Can I deploy this in a HIPAA-compliant environment?**
A: The system can be configured for HIPAA compliance, but you'll need to ensure proper security measures, access controls, and audit logging are implemented.

**Q: What about multi-user support?**
A: The current version is designed for single-user or small team use. For enterprise deployment with user management, additional authentication and authorization layers would need to be implemented.

### Performance Questions

**Q: How can I improve query response time?**
A: Enable caching, optimize chunk sizes, use GPU acceleration, and ensure adequate RAM. Monitor system resources and tune configuration parameters.

**Q: What's the maximum knowledge base size?**
A: This depends on your system resources. Qdrant can handle millions of vectors, but RAM and storage requirements scale with knowledge base size.

**Q: Can I use different embedding models?**
A: Yes, but MedCPT is optimized for medical content. If you change models, you'll need to rebuild embeddings and may need to adjust similarity thresholds.

**Q: How do I monitor system performance?**
A: Use the built-in health checks, monitor response times, and track resource usage. Consider implementing Prometheus metrics for production deployments.
