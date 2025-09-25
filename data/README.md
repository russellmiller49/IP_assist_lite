# IP Assist Lite Data Structure

This directory contains organized data folders for different types of medical documents and knowledge base components.

## Directory Structure

```
data/
├── raw/                    # Raw input documents
│   ├── articles/           # Medical journal articles
│   ├── textbooks/         # Medical textbooks and references
│   ├── guidelines/        # Clinical practice guidelines
│   └── manuals/           # Procedural manuals and technical docs
├── processed/             # Processed documents from medparse
│   ├── articles/          # Processed articles
│   ├── textbooks/         # Processed textbooks
│   ├── guidelines/        # Processed guidelines
│   └── manuals/          # Processed manuals
├── chunks/               # Text chunks for retrieval
│   ├── articles/          # Article chunks
│   ├── textbooks/         # Textbook chunks
│   ├── guidelines/        # Guideline chunks
│   └── manuals/          # Manual chunks
├── vectors/               # Embeddings and vector data
├── term_index/           # BM25 term indices
└── templates/            # Report templates
```

## Document Types

### Articles (`data/raw/articles/`)
- **Purpose**: Medical journal articles, research papers, case studies
- **Processing**: Focus on abstracts, references, clinical terminology
- **Chunking**: Smaller chunks for precise retrieval
- **Use Case**: Evidence-based medicine, research findings, case studies

### Textbooks (`data/raw/textbooks/`)
- **Purpose**: Medical textbooks, comprehensive references, educational materials
- **Processing**: Focus on chapters, figures, comprehensive terminology
- **Chunking**: Larger chunks for comprehensive coverage
- **Use Case**: Educational content, comprehensive medical knowledge

### Guidelines (`data/raw/guidelines/`)
- **Purpose**: Clinical practice guidelines, protocols, standards
- **Processing**: Focus on recommendations, evidence levels, algorithms
- **Chunking**: Medium chunks for protocol retrieval
- **Use Case**: Clinical decision support, protocol adherence

### Manuals (`data/raw/manuals/`)
- **Purpose**: Procedural manuals, technical documentation, equipment guides
- **Processing**: Focus on procedures, steps, safety warnings
- **Chunking**: Step-by-step chunks for procedural guidance
- **Use Case**: Procedural guidance, equipment operation, safety protocols

## Workflow

### 1. Document Ingestion
```bash
# Place documents in appropriate raw directories
cp your_articles.pdf data/raw/articles/
cp your_textbook.pdf data/raw/textbooks/
cp your_guidelines.pdf data/raw/guidelines/
cp your_manual.pdf data/raw/manuals/
```

### 2. Document Processing
```bash
# Process documents through medparse
cd ../ip_knowledge/medparse/medparse-docling
./scripts/process_all_documents.sh

# Copy processed results to IP Assist Lite
cp output/articles/*.json ../IP_assist_lite/data/processed/articles/
cp output/textbooks/*.json ../IP_assist_lite/data/processed/textbooks/
cp output/guidelines/*.json ../IP_assist_lite/data/processed/guidelines/
cp output/manuals/*.json ../IP_assist_lite/data/processed/manuals/
```

### 3. Knowledge Base Building
```bash
# Build knowledge base from processed documents
./scripts/build_knowledge_base.sh
```

## Configuration

### Document Type Settings
Each document type can have different processing settings:

- **Chunk Size**: Articles (500), Textbooks (1000), Guidelines (750), Manuals (600)
- **Overlap**: Articles (100), Textbooks (200), Guidelines (150), Manuals (120)
- **Embedding Model**: All use `ncbi/MedCPT-Query-Encoder`
- **Retrieval Weight**: Articles (0.8), Textbooks (0.7), Guidelines (0.9), Manuals (0.8)

### Retrieval Strategy
- **Hybrid Retrieval**: Combines BM25 and semantic search
- **Document Type Filtering**: Can filter by document type in queries
- **Relevance Scoring**: Different scoring for different document types
- **Citation Integration**: Smart citations from processed documents

## Integration with Medparse

The structured approach integrates seamlessly with medparse:

1. **Input**: Documents organized by type in medparse input directories
2. **Processing**: Document-type-specific processing in medparse
3. **Output**: Processed JSON files organized by type
4. **Integration**: Copy processed files to IP Assist Lite data directories
5. **Building**: Build knowledge base with type-specific settings

## Best Practices

1. **Organize by Type**: Always place documents in the appropriate type directory
2. **Use Descriptive Names**: Use clear, descriptive filenames
3. **Maintain Structure**: Keep the directory structure consistent
4. **Process in Batches**: Process documents by type for better organization
5. **Monitor Quality**: Check processed outputs for quality and completeness
6. **Version Control**: Keep track of document versions and updates
7. **Backup Data**: Regularly backup your data directories

## Customization

### Adding New Document Types
1. Create new directories in `data/raw/`, `data/processed/`, and `data/chunks/`
2. Add processing script in medparse
3. Update configuration files
4. Modify knowledge base builder

### Adjusting Processing Settings
1. Edit `configs/knowledge_base_config.yaml`
2. Modify chunk sizes, overlap, and retrieval weights
3. Update embedding models if needed
4. Rebuild knowledge base with new settings
