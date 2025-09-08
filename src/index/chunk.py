"""
Variable chunking system with section-aware sizing
Procedures kept intact, tables row-level, complications tighter
"""
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple
import hashlib


SECTION_TO_TYPE = {
    r"procedure|placement|technique|how to|steps": "procedure_steps",
    r"complication|adverse|risk|safety": "complications", 
    r"cpt|rvu|code|reimbursement|billing": "coding",
    r"ablation|pdt|radiofrequency|microwave|cryo": "ablation",
    r"valve|lung volume reduction|chartis|fissure|blvr": "blvr",
    r"contraindication": "contraindications",
    r"dose|dosing|energy|settings|parameters": "dose_parameters",
    r"eligibility|selection|criteria": "eligibility",
}


class VariableChunker:
    """Smart chunking based on content type and section."""
    
    def __init__(self, output_dir: str = "data/chunks"):
        # Get the project root directory
        project_root = Path(__file__).parent.parent.parent
        self.output_dir = project_root / output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.chunks = []
        self.term_index = {"cpt": {}, "aliases": {}}
        
    def chunk_all_documents(self, processed_dir: str = "data/processed"):
        """Process all standardized documents into chunks."""
        project_root = Path(__file__).parent.parent.parent
        processed_path = project_root / processed_dir
        json_files = list(processed_path.glob("*.json"))
        
        print(f"Chunking {len(json_files)} documents...")
        
        for file_path in json_files:
            with open(file_path, "r") as f:
                doc = json.load(f)
            self.chunk_document(doc)
        
        # Save chunks
        chunks_path = self.output_dir / "chunks.jsonl"
        with open(chunks_path, "w") as f:
            for chunk in self.chunks:
                f.write(json.dumps(chunk) + "\n")
        
        # Save term indexes
        self._save_term_indexes()
        
        print(f"Created {len(self.chunks)} chunks")
        print(f"Saved to {chunks_path}")
        
    def chunk_document(self, doc: Dict[str, Any]) -> List[Dict]:
        """Chunk a single document with variable sizing."""
        doc_chunks = []
        doc_id = doc.get("doc_id", doc.get("id", ""))  # Handle both doc_id and id
        metadata = doc.get("metadata", {})
        
        # Chunk abstract if present
        if doc.get("abstract"):
            abstract_chunks = self._chunk_text(
                doc["abstract"],
                section_title="Abstract",
                doc_id=doc_id,
                metadata=metadata,
                section_type="abstract"
            )
            doc_chunks.extend(abstract_chunks)
        
        # Chunk sections
        if doc.get("sections"):
            for section in doc["sections"]:
                if isinstance(section, dict):
                    title = section.get("title", "")
                    content = section.get("content", "")
                    
                    if content:
                        section_chunks = self.smart_chunk(
                            text=content,
                            section_title=title,
                            doc_id=doc_id,
                            metadata=metadata
                        )
                        doc_chunks.extend(section_chunks)
        
        # Chunk tables (row-level + full table)
        if doc.get("tables_struct"):
            table_chunks = self._chunk_tables(
                doc["tables_struct"],
                doc["tables_markdown"],
                doc_id=doc_id,
                metadata=metadata
            )
            doc_chunks.extend(table_chunks)
        
        self.chunks.extend(doc_chunks)
        return doc_chunks
    
    def smart_chunk(self, text: str, section_title: str, doc_id: str, 
                   metadata: Dict) -> List[Dict]:
        """Apply section-aware chunking strategy."""
        # Determine section type
        section_type = self._determine_section_type(section_title)
        
        if section_type == "procedure_steps":
            # Keep procedures intact up to 800 tokens
            return self._chunk_procedure(text, section_title, doc_id, metadata)
        elif section_type in ["complications", "coding"]:
            # Tighter chunks for critical info
            return self._chunk_by_paragraph(text, section_title, doc_id, metadata,
                                           target_tokens=300, max_tokens=450)
        elif section_type in ["ablation", "blvr"]:
            # Medium-sized for technical content
            return self._chunk_by_paragraph(text, section_title, doc_id, metadata,
                                           target_tokens=350, max_tokens=500)
        elif section_type == "contraindications":
            # Keep contraindications together if possible
            return self._chunk_by_paragraph(text, section_title, doc_id, metadata,
                                           target_tokens=250, max_tokens=400)
        else:
            # Default chunking
            return self._chunk_by_paragraph(text, section_title, doc_id, metadata,
                                           target_tokens=400, max_tokens=600)
    
    def _determine_section_type(self, section_title: str) -> str:
        """Determine section type from title."""
        title_lower = (section_title or "").lower()
        
        for pattern, stype in SECTION_TO_TYPE.items():
            if re.search(pattern, title_lower):
                return stype
        
        return "general"
    
    def _chunk_procedure(self, text: str, section_title: str, doc_id: str,
                        metadata: Dict) -> List[Dict]:
        """Chunk procedures keeping steps intact."""
        chunks = []
        
        # Try to identify numbered steps
        step_pattern = r"(?:^|\n)\s*(?:\d+[\.)]\s*|[IVX]+[\.)]\s*|[A-Z][\.)]\s*|•\s*|[-*]\s*)"
        parts = re.split(step_pattern, text)
        
        # If we have clear steps, keep them together
        if len(parts) > 1:
            current_chunk = []
            current_tokens = 0
            
            for part in parts:
                part_tokens = self._estimate_tokens(part)
                
                if current_tokens + part_tokens > 800 and current_chunk:
                    # Save current chunk
                    chunk_text = "\n".join(current_chunk)
                    chunks.append(self._create_chunk(
                        chunk_text, section_title, doc_id, metadata, "procedure_steps"
                    ))
                    current_chunk = [part]
                    current_tokens = part_tokens
                else:
                    current_chunk.append(part)
                    current_tokens += part_tokens
            
            # Add remaining
            if current_chunk:
                chunk_text = "\n".join(current_chunk)
                chunks.append(self._create_chunk(
                    chunk_text, section_title, doc_id, metadata, "procedure_steps"
                ))
        else:
            # No clear steps, treat as single chunk if under 800 tokens
            if self._estimate_tokens(text) <= 800:
                chunks.append(self._create_chunk(
                    text, section_title, doc_id, metadata, "procedure_steps"
                ))
            else:
                # Fall back to paragraph chunking
                chunks = self._chunk_by_paragraph(text, section_title, doc_id, metadata,
                                                 target_tokens=400, max_tokens=800)
        
        return chunks
    
    def _chunk_by_paragraph(self, text: str, section_title: str, doc_id: str,
                           metadata: Dict, target_tokens: int = 400,
                           max_tokens: int = 600) -> List[Dict]:
        """Chunk by paragraph with token limits."""
        chunks = []
        
        # Split by double newline or single newline
        paragraphs = re.split(r'\n\n+', text)
        if len(paragraphs) == 1:
            paragraphs = re.split(r'\n', text)
        
        current_chunk = []
        current_tokens = 0
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            para_tokens = self._estimate_tokens(para)
            
            # If single paragraph exceeds max, split it
            if para_tokens > max_tokens:
                # Save current chunk if any
                if current_chunk:
                    chunk_text = "\n\n".join(current_chunk)
                    chunks.append(self._create_chunk(
                        chunk_text, section_title, doc_id, metadata
                    ))
                    current_chunk = []
                    current_tokens = 0
                
                # Split large paragraph by sentences
                sentences = re.split(r'(?<=[.!?])\s+', para)
                for sent in sentences:
                    sent_tokens = self._estimate_tokens(sent)
                    
                    if current_tokens + sent_tokens > max_tokens and current_chunk:
                        chunk_text = " ".join(current_chunk)
                        chunks.append(self._create_chunk(
                            chunk_text, section_title, doc_id, metadata
                        ))
                        current_chunk = [sent]
                        current_tokens = sent_tokens
                    else:
                        current_chunk.append(sent)
                        current_tokens += sent_tokens
            
            # Normal paragraph processing
            elif current_tokens + para_tokens > target_tokens and current_chunk:
                # Save current chunk
                chunk_text = "\n\n".join(current_chunk)
                chunks.append(self._create_chunk(
                    chunk_text, section_title, doc_id, metadata
                ))
                current_chunk = [para]
                current_tokens = para_tokens
            else:
                current_chunk.append(para)
                current_tokens += para_tokens
        
        # Add remaining
        if current_chunk:
            chunk_text = "\n\n".join(current_chunk) if len(current_chunk) > 1 else current_chunk[0]
            chunks.append(self._create_chunk(
                chunk_text, section_title, doc_id, metadata
            ))
        
        return chunks
    
    def _chunk_tables(self, tables_struct: List[Dict], tables_markdown: List[str],
                     doc_id: str, metadata: Dict) -> List[Dict]:
        """Create row-level chunks for tables."""
        chunks = []
        
        # Row-level chunks
        for i, row in enumerate(tables_struct):
            # Extract CPT and wRVU if present
            cpt_code = None
            wrvu = None
            
            for key, value in row.items():
                if "cpt" in key.lower():
                    # Extract CPT code pattern
                    cpt_match = re.search(r'\b(\d{5})\b', str(value))
                    if cpt_match:
                        cpt_code = cpt_match.group(1)
                elif "rvu" in key.lower() or "wrvu" in key.lower():
                    # Extract numeric RVU
                    rvu_match = re.search(r'(\d+(?:\.\d+)?)', str(value))
                    if rvu_match:
                        wrvu = float(rvu_match.group(1))
            
            # Create chunk for row
            row_text = json.dumps(row, indent=2)
            chunk = self._create_chunk(
                row_text,
                section_title="Table Row",
                doc_id=doc_id,
                metadata=metadata,
                section_type="table_row"
            )
            
            # Add CPT/wRVU to chunk metadata if found
            if cpt_code:
                chunk["cpt_code"] = cpt_code
                # Add to CPT index
                if cpt_code not in self.term_index["cpt"]:
                    self.term_index["cpt"][cpt_code] = []
                # Use chunk_id if available, otherwise id
                chunk_identifier = chunk.get("chunk_id", chunk.get("id", chunk.get("doc_id")))
                if chunk_identifier:
                    self.term_index["cpt"][cpt_code].append(chunk_identifier)
            
            if wrvu is not None:
                chunk["wrvu"] = wrvu
            
            chunks.append(chunk)
        
        # Also create chunks for full markdown tables
        for table_md in tables_markdown:
            if table_md:
                chunk = self._create_chunk(
                    table_md,
                    section_title="Table",
                    doc_id=doc_id,
                    metadata=metadata,
                    section_type="table_full"
                )
                chunks.append(chunk)
        
        return chunks
    
    def _chunk_text(self, text: str, section_title: str, doc_id: str,
                   metadata: Dict, section_type: str = "general") -> List[Dict]:
        """Generic text chunking."""
        return self._chunk_by_paragraph(text, section_title, doc_id, metadata)
    
    def _create_chunk(self, text: str, section_title: str, doc_id: str,
                     metadata: Dict, section_type: str = None) -> Dict:
        """Create a chunk with metadata."""
        # Generate unique chunk ID
        chunk_id = hashlib.md5(f"{doc_id}:{text[:100]}".encode()).hexdigest()[:12]
        
        if section_type is None:
            section_type = self._determine_section_type(section_title)
        
        chunk = {
            "id": chunk_id,
            "doc_id": doc_id,
            "text": text,
            "section_title": section_title,
            "section_type": section_type,
            "authority_tier": metadata.get("authority_tier"),
            "evidence_level": metadata.get("evidence_level"),
            "year": metadata.get("year"),
            "domain": metadata.get("domain", ["clinical"]),
            "doc_type": metadata.get("doc_type"),
            "precedence": metadata.get("precedence"),
            "temporal": metadata.get("temporal"),
            "aliases": metadata.get("aliases", [])
        }
        
        # Add aliases to index
        for alias in metadata.get("aliases", []):
            if alias not in self.term_index["aliases"]:
                self.term_index["aliases"][alias] = []
            if chunk_id not in self.term_index["aliases"][alias]:
                self.term_index["aliases"][alias].append(chunk_id)
        
        return chunk
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count (rough approximation)."""
        # Rough estimate: ~1 token per 4 characters
        return len(text) // 4
    
    def _save_term_indexes(self):
        """Save term indexes for exact matching."""
        # Save CPT index
        project_root = Path(__file__).parent.parent.parent
        cpt_index_path = project_root / "data/term_index/cpt.jsonl"
        with open(cpt_index_path, "w") as f:
            for cpt_code, chunk_ids in self.term_index["cpt"].items():
                f.write(json.dumps({"cpt": cpt_code, "chunks": chunk_ids}) + "\n")
        
        # Save aliases index  
        aliases_index_path = project_root / "data/term_index/aliases.jsonl"
        with open(aliases_index_path, "w") as f:
            for alias, chunk_ids in self.term_index["aliases"].items():
                f.write(json.dumps({"alias": alias, "chunks": chunk_ids}) + "\n")
        
        print(f"Saved {len(self.term_index['cpt'])} CPT codes to index")
        print(f"Saved {len(self.term_index['aliases'])} aliases to index")


if __name__ == "__main__":
    chunker = VariableChunker()
    chunker.chunk_all_documents()