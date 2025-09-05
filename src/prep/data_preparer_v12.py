"""
Data Preparer v1.2 - Standardizes medical literature with enhanced metadata
Includes: table promotion, domain classification, authority tiers, and temporal tracking
"""
import json
import re
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import sys
sys.path.append(str(Path(__file__).parent.parent))

from ip_assistant.utils.clean import normalize_text, clean_table_cell, clean_section_title


class DataPreparerV12:
    """Enhanced data preparer with domain awareness and table promotion."""
    
    def __init__(self, input_dir: str = "data/raw", output_dir: str = "data/processed"):
        # Get the project root directory (2 levels up from this file)
        project_root = Path(__file__).parent.parent.parent
        self.input_dir = project_root / input_dir
        self.output_dir = project_root / output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.registry = []
        
    def process_all_files(self):
        """Process all JSON files in the input directory."""
        json_files = list(self.input_dir.glob("*.json"))
        print(f"Found {len(json_files)} files to process")
        
        for i, file_path in enumerate(json_files, 1):
            print(f"Processing {i}/{len(json_files)}: {file_path.name}")
            try:
                self.process_file(file_path)
            except Exception as e:
                print(f"Error processing {file_path.name}: {str(e)}")
                continue
        
        # Save registry
        project_root = Path(__file__).parent.parent.parent
        registry_path = project_root / "data" / "registry.jsonl"
        with open(registry_path, "w") as f:
            for entry in self.registry:
                f.write(json.dumps(entry) + "\n")
        print(f"Registry saved to {registry_path}")
    
    def process_file(self, file_path: Path) -> Dict[str, Any]:
        """Process a single file with full standardization."""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Apply text cleaning to all text fields first
        data = self._clean_all_text_fields(data)
        
        # Extract metadata
        meta = self._extract_metadata(data)
        
        # Get title and abstract from appropriate location
        title = self._extract_title(data)
        abstract = self._extract_abstract(data)
        
        # Determine authority tier and evidence level
        authority_tier = self._assign_authority_tier(meta)
        
        # Infer domain and document type
        sections_text = self._get_all_sections_text(data)
        domain, doc_type = self._infer_domain_and_doc_type(
            title, 
            meta.get("journal", ""),
            sections_text
        )
        
        # Determine evidence level based on doc type
        evidence_level = self._determine_h_level(doc_type, sections_text)
        
        # Calculate precedence
        year = int(meta.get("year", 0))
        precedence = self._calculate_precedence(authority_tier, evidence_level, year, domain)
        
        # Process tables
        tables_markdown, tables_struct = self._process_tables(data)
        
        # Build aliases
        aliases = self._extract_aliases(data.get("title", ""), sections_text)
        
        # Build temporal validity
        temporal = self._build_temporal_validity(data, year, domain)
        
        # Create standardized document
        standardized = {
            "id": file_path.stem,
            "title": title,
            "abstract": abstract,
            "content": self._build_content(data, tables_markdown),
            "metadata": {
                **meta,
                "authority_tier": authority_tier,
                "evidence_level": evidence_level,
                "precedence": precedence,
                "domain": domain,
                "doc_type": doc_type,
                "aliases": aliases,
                "temporal": temporal,
                "original_file": file_path.name
            },
            "sections": data.get("sections", []),
            "tables_markdown": tables_markdown,
            "tables_struct": tables_struct,
            "references": data.get("references", [])
        }
        
        # Save processed file
        output_path = self.output_dir / f"{file_path.stem}.json"
        with open(output_path, "w") as f:
            json.dump(standardized, f, indent=2)
        
        # Add to registry
        self.registry.append({
            "id": standardized["id"],
            "title": standardized["title"],
            "authority_tier": authority_tier,
            "evidence_level": evidence_level,
            "year": year,
            "domain": domain,
            "doc_type": doc_type,
            "precedence": precedence,
            "file": output_path.name
        })
        
        # Emit warning for old coding content
        if "coding_billing" in domain and datetime.now().year - year >= 4:
            print(f"  ⚠️  WARNING: Coding content from {year} may be outdated")
        
        return standardized
    
    def _clean_all_text_fields(self, data: Dict) -> Dict:
        """Apply text cleaning to all text fields in the data."""
        if isinstance(data, dict):
            cleaned = {}
            for key, value in data.items():
                if isinstance(value, str):
                    cleaned[key] = normalize_text(value)
                elif isinstance(value, list):
                    cleaned[key] = self._clean_all_text_fields(value)
                elif isinstance(value, dict):
                    cleaned[key] = self._clean_all_text_fields(value)
                else:
                    cleaned[key] = value
            return cleaned
        elif isinstance(data, list):
            return [self._clean_all_text_fields(item) for item in data]
        else:
            return data
    
    def _extract_metadata(self, data: Dict) -> Dict:
        """Extract and standardize metadata."""
        meta = {}
        
        # Check if metadata is nested
        if "metadata" in data and isinstance(data["metadata"], dict):
            metadata = data["metadata"]
            meta["book"] = metadata.get("book", data.get("book", ""))
            meta["journal"] = metadata.get("journal", data.get("journal", ""))
            meta["year"] = metadata.get("year") or metadata.get("publication_year") or data.get("year", 0)
            meta["authors"] = metadata.get("authors", data.get("authors", []))
            meta["doi"] = metadata.get("doi", data.get("doi", ""))
            meta["pmid"] = metadata.get("pmid", data.get("pmid", ""))
            meta["volume"] = metadata.get("volume", "")
            meta["issue"] = metadata.get("issue", "")
            meta["pages"] = metadata.get("pages", "")
        else:
            # Fallback to top-level fields
            meta["book"] = data.get("book", "")
            meta["journal"] = data.get("journal", "")
            meta["year"] = data.get("year") or data.get("publication_year") or 0
            meta["authors"] = data.get("authors", [])
            meta["doi"] = data.get("doi", "")
            meta["pmid"] = data.get("pmid", "")
            meta["volume"] = ""
            meta["issue"] = ""
            meta["pages"] = ""
        
        # Try to extract year from text if still missing
        if not meta["year"]:
            year_match = re.search(r"\b(19|20)\d{2}\b", str(data))
            if year_match:
                meta["year"] = int(year_match.group(0))
        
        return meta
    
    def _extract_title(self, data: Dict) -> str:
        """Extract title from appropriate location."""
        # Check metadata first
        if "metadata" in data and isinstance(data["metadata"], dict):
            if "title" in data["metadata"] and data["metadata"]["title"]:
                return data["metadata"]["title"]
        
        # Fallback to top-level title
        return data.get("title", "")
    
    def _extract_abstract(self, data: Dict) -> str:
        """Extract abstract from appropriate location."""
        # Check metadata first
        if "metadata" in data and isinstance(data["metadata"], dict):
            if "abstract" in data["metadata"] and data["metadata"]["abstract"]:
                return data["metadata"]["abstract"]
        
        # Check for abstract in sections
        if "sections" in data:
            for section in data["sections"]:
                if isinstance(section, dict):
                    if section.get("title", "").lower() == "abstract":
                        return section.get("content", "")
        
        # Fallback to top-level abstract
        return data.get("abstract", "")
    
    def _assign_authority_tier(self, meta: Dict) -> str:
        """Assign authority tier based on source."""
        book = (meta.get("book") or "").lower()
        journal = (meta.get("journal") or "").lower()
        year = int(meta.get("year") or 0)
        
        if "principles and practice of interventional pulmonology" in book:
            if year >= 2025:
                return "A1"
            else:
                return "A2"  # Older edition
        elif "practical guide to interventional pulmonology" in book:
            return "A2"
        elif "bronchoscopy and central airway disorders" in book:
            return "A3"
        else:
            return "A4"  # Journal articles
    
    def _infer_domain_and_doc_type(self, title: str, journal: str, sections_text: str) -> Tuple[List[str], str]:
        """Infer domain categories and document type."""
        text = f"{title}\n{journal}\n{sections_text}".lower()
        
        # Domain inference
        domains = []
        
        if any(term in text for term in ["cpt", "rvu", "wrvu", "coding", "billing", "reimbursement"]):
            domains.append("coding_billing")
        
        if any(term in text for term in ["ablation", "radiofrequency", "microwave", "cryoablation", "rfa", "mwa"]):
            domains.append("ablation")
        
        if any(term in text for term in ["endobronchial valve", "bronchoscopic lung volume reduction", 
                                          "blvr", "zephyr", "spiration", "chartis"]):
            domains.append("lung_volume_reduction")
        
        if any(term in text for term in ["navigation bronchoscopy", "electromagnetic navigation", 
                                          "enb", "radial probe", "rp-ebus", "vbn", "btpna"]):
            domains.append("technology_navigation")
        
        if any(term in text for term in ["training", "competency", "education", "fellowship", "curriculum"]):
            domains.append("training_competency")
        
        # Document type inference
        doc_type = "narrative_review"  # Default
        
        if "guideline" in text or "expert panel report" in text or "consensus statement" in text:
            doc_type = "guideline"
        elif "systematic review" in text or "meta-analysis" in text:
            doc_type = "systematic_review"
        elif re.search(r"\brandomi[sz]ed\b|\brct\b|randomized controlled trial", text):
            doc_type = "RCT"
        elif "cohort study" in text or "prospective study" in text:
            doc_type = "cohort"
        elif "case series" in text or "case report" in text:
            doc_type = "case_series"
        elif any(term in text for term in ["coding", "wrvu", "cpt", "reimbursement"]):
            doc_type = "coding_update"
        
        # Default domain if none found
        if not domains:
            domains = ["clinical"]
        
        return domains, doc_type
    
    def _determine_h_level(self, doc_type: str, text: str) -> str:
        """Determine evidence hierarchy level based on document type."""
        if doc_type == "guideline" or doc_type == "systematic_review":
            return "H1"
        elif doc_type == "RCT":
            return "H2"
        elif doc_type in ["cohort", "coding_update"]:
            return "H3"
        elif doc_type == "case_series":
            return "H4"
        else:
            # Narrative reviews get H3 by default
            return "H3"
    
    def _calculate_precedence(self, tier: str, h_level: str, year: int, domains: List[str]) -> float:
        """Calculate precedence score with domain-aware recency."""
        # Recency weight calculation
        current_year = datetime.now().year
        age = max(0, current_year - year)
        
        # Domain-specific half-life
        half_life = 6.0  # Default
        if "coding_billing" in domains:
            half_life = 3.0
        elif "ablation" in domains:
            half_life = 5.0
        elif "technology_navigation" in domains:
            half_life = 4.0
        
        # Calculate recency weight
        recency_weight = 0.5 ** (age / half_life)
        
        # A1 floor - A1 documents maintain minimum 70% recency
        if tier == "A1":
            recency_weight = max(0.70, recency_weight)
        
        # Authority weights
        authority_weights = {
            "A1": 1.00,
            "A2": 0.90,
            "A3": 0.70,
            "A4": 0.65
        }
        
        # Evidence level weights
        h_weights = {
            "H1": 1.00,
            "H2": 0.85,
            "H3": 0.65,
            "H4": 0.45
        }
        
        # Calculate final precedence
        precedence = (
            0.5 * recency_weight +
            0.3 * h_weights.get(h_level, 0.5) +
            0.2 * authority_weights.get(tier, 0.5)
        )
        
        return round(precedence, 3)
    
    def _process_tables(self, data: Dict) -> Tuple[List[str], List[Dict]]:
        """Process tables into markdown and structured format."""
        tables_markdown = []
        tables_struct = []
        
        if "tables" not in data or not isinstance(data["tables"], list):
            return [], []
        
        for table in data["tables"]:
            # Extract headers and rows
            headers = table.get("headers", [])
            rows = table.get("rows", [])
            
            if not headers:
                continue
            
            # Clean headers
            headers = [clean_table_cell(str(h)) for h in headers]
            
            # Build markdown table
            md_lines = []
            md_lines.append("| " + " | ".join(headers) + " |")
            md_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
            
            # Process rows
            for row in rows:
                # Clean cells
                clean_row = [clean_table_cell(str(cell)) for cell in row]
                md_lines.append("| " + " | ".join(clean_row) + " |")
                
                # Create structured row
                if len(clean_row) == len(headers):
                    row_dict = {}
                    for header, value in zip(headers, clean_row):
                        # Normalize header for structured data
                        key = header.strip().lower().replace(" ", "_")
                        row_dict[key] = value
                    
                    # Try to extract CPT and wRVU if present
                    if any("cpt" in k for k in row_dict.keys()):
                        tables_struct.append(row_dict)
            
            # Add caption if present
            caption = table.get("caption", "")
            if caption:
                md_lines.insert(0, f"**{caption}**\n")
            
            tables_markdown.append("\n".join(md_lines))
        
        return tables_markdown, tables_struct
    
    def _build_content(self, data: Dict, tables_markdown: List[str]) -> str:
        """Build complete content including tables."""
        content_parts = []
        
        # Add abstract
        if data.get("abstract"):
            content_parts.append(data["abstract"])
        
        # Check for text_chunks (book format)
        if "text_chunks" in data and isinstance(data["text_chunks"], list):
            # Extract text from chunks
            for chunk in data["text_chunks"]:
                if isinstance(chunk, dict) and "text" in chunk:
                    content_parts.append(chunk["text"])
        
        # Add sections (journal article format)
        elif "sections" in data:
            for section in data["sections"]:
                if isinstance(section, dict):
                    title = clean_section_title(section.get("title", ""))
                    text = section.get("content", "")
                    if title:
                        content_parts.append(f"## {title}")
                    if text:
                        content_parts.append(text)
        
        # If still no content, check for direct content field
        elif data.get("content"):
            content_parts.append(data["content"])
        
        # Append tables at the end
        if tables_markdown:
            content_parts.append("\n## Tables\n")
            content_parts.extend(tables_markdown)
        
        return "\n\n".join(content_parts).strip()
    
    def _extract_aliases(self, title: str, sections_text: str) -> List[str]:
        """Extract relevant aliases and acronyms."""
        aliases = []
        text = f"{title}\n{sections_text}".lower()
        
        # Common IP aliases
        alias_patterns = {
            "ebus": "endobronchial ultrasound",
            "rp-ebus": "radial probe endobronchial ultrasound", 
            "enb": "electromagnetic navigation bronchoscopy",
            "vbn": "virtual bronchoscopic navigation",
            "blvr": "bronchoscopic lung volume reduction",
            "pdt": "photodynamic therapy",
            "tbna": "transbronchial needle aspiration",
            "rose": "rapid on-site evaluation",
        }
        
        for abbrev, full in alias_patterns.items():
            if abbrev in text or full in text:
                aliases.append(abbrev)
        
        return list(set(aliases))
    
    def _build_temporal_validity(self, data: Dict, year: int, domains: List[str]) -> Dict:
        """Build temporal validity information."""
        temporal = {
            "valid_from": f"{year}-01-01" if year else None,
            "valid_until": None,
            "last_seen_year": year
        }
        
        # Special handling for volatile domains
        if "coding_billing" in domains:
            # Coding updates typically valid for ~2 years
            if year:
                temporal["valid_until"] = f"{year + 2}-12-31"
        
        return temporal
    
    def _get_all_sections_text(self, data: Dict) -> str:
        """Extract all section text for analysis."""
        parts = []
        
        # Check for text_chunks (book format)
        if "text_chunks" in data and isinstance(data["text_chunks"], list):
            for chunk in data["text_chunks"]:
                if isinstance(chunk, dict) and "text" in chunk:
                    parts.append(chunk["text"])
        
        # Check for sections (journal article format)
        elif "sections" in data:
            for section in data["sections"]:
                if isinstance(section, dict):
                    parts.append(section.get("content", ""))
                elif isinstance(section, str):
                    parts.append(section)
        
        # Fallback to content field
        elif data.get("content"):
            parts.append(data["content"])
        
        return "\n".join(parts)


if __name__ == "__main__":
    preparer = DataPreparerV12()
    preparer.process_all_files()