"""
Data Preparer v1.2 Fixed - Addresses all identified data quality issues
Fixes: ID normalization, RCT detection, OCR artifacts, disclaimers, authority tier alignment
"""
import json
import re
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import sys
sys.path.append(str(Path(__file__).parent.parent))

from ip_assistant.utils.clean import normalize_text, clean_table_cell, clean_section_title


class DataPreparerV12Fixed:
    """Enhanced data preparer with comprehensive fixes for all identified issues."""
    
    # Common OCR artifacts and broken headings
    HEADING_FIXES = {
        "etting": "Setting",
        "atients": "Patients",
        "esults": "Results",
        "ethods": "Methods",
        "ackground": "Background",
        "onclusions": "Conclusions",
        "iscussion": "Discussion",
        "ntroduction": "Introduction",
        "bstract": "Abstract",
        "eferences": "References",
        "andomization": "Randomization",
        "tudy protocol": "Study Protocol",
        "tudy outcomes": "Study Outcomes",
        "tatistical analysis": "Statistical Analysis",
        "cknowledgments": "Acknowledgments"
    }
    
    # Disclaimer patterns to move to metadata
    DISCLAIMER_PATTERNS = [
        r"MANDATORY\s+DOD\s+DISCLAIMER.*?(?:\n\n|$)",
        r"DISCLAIMER:.*?(?:\n\n|$)",
        r"The\s+views\s+expressed.*?United\s+States\s+Government.*?(?:\n\n|$)",
        r"DISTRIBUTION\s+STATEMENT.*?(?:\n\n|$)",
        r"Approved\s+for\s+public\s+release.*?(?:\n\n|$)"
    ]
    
    def __init__(self, input_dir: str = "data/raw", output_dir: str = "data/processed"):
        project_root = Path(__file__).parent.parent.parent
        self.input_dir = project_root / input_dir
        self.output_dir = project_root / output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.registry = []
        
    def process_all_files(self):
        """Process all JSON files with comprehensive fixes."""
        json_files = list(self.input_dir.glob("*.json"))
        print(f"Found {len(json_files)} files to process")
        
        for i, file_path in enumerate(json_files, 1):
            print(f"Processing {i}/{len(json_files)}: {file_path.name}")
            try:
                standardized = self.process_file(file_path)
                
                # Save processed file
                output_path = self.output_dir / file_path.name
                with open(output_path, "w") as f:
                    json.dump(standardized, f, indent=2)
                    
                # Add to registry
                self.registry.append({
                    "doc_id": standardized["doc_id"],
                    "title": standardized["title"],
                    "authority_tier": standardized["metadata"]["authority_tier"],
                    "h_level": standardized["h_level"],
                    "year": standardized["year"],
                    "domain": standardized["metadata"]["domain"],
                    "doc_type": standardized["metadata"]["doc_type"],
                    "precedence": standardized["metadata"]["precedence"],
                    "file": output_path.name
                })
                
            except Exception as e:
                print(f"  ❌ Error processing {file_path.name}: {str(e)}")
                continue
        
        # Save registry
        registry_path = self.output_dir.parent / "registry.jsonl"
        with open(registry_path, "w") as f:
            for entry in self.registry:
                f.write(json.dumps(entry) + "\n")
        print(f"✅ Registry saved to {registry_path}")
    
    def process_file(self, file_path: Path) -> Dict[str, Any]:
        """Process a single file with all fixes applied."""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # FIX 1: Normalize IDs - ensure doc_id exists at top level
        doc_id = self._normalize_id(data, file_path.stem)
        
        # Extract and clean title
        title = self._extract_and_clean_title(data)
        
        # Extract and clean abstract
        abstract = self._extract_and_clean_abstract(data)
        
        # FIX 5: Fix broken OCR headings in sections
        sections = self._fix_broken_sections(data.get("sections", []))
        
        # Get all text for analysis
        sections_text = self._get_all_sections_text(data, sections)
        
        # FIX 7: Extract disclaimers before processing content
        content, disclaimers = self._extract_disclaimers(data, sections, sections_text)
        
        # FIX 6: Handle empty content
        if not content or len(content.strip()) == 0:
            content = self._build_content_from_sections(sections, abstract)
        
        # Clean content
        content = normalize_text(content)
        
        # Extract metadata
        metadata = self._extract_metadata(data)
        
        # FIX 2: Promote year to top level
        year = self._extract_and_validate_year(data, metadata, content)
        
        # FIX 3: Align authority tier based on filename
        authority_tier = self._assign_authority_tier(metadata, file_path.stem)
        
        # Infer domain
        domains = self._infer_domains(title, metadata.get("journal", ""), content)
        
        # FIX 4: Correct doc_type detection with RCT override
        doc_type = self._determine_doc_type(title, content, file_path.stem)
        
        # Determine evidence level
        h_level = self._determine_h_level(doc_type, content)
        
        # Calculate precedence
        precedence = self._calculate_precedence(authority_tier, h_level, year, domains)
        
        # Process tables
        tables_markdown, tables_struct = self._process_tables(data)
        
        # Add tables to content if present
        if tables_markdown and "\n\n## Tables\n\n" not in content:
            content += "\n\n## Tables\n\n" + "\n\n".join(tables_markdown)
        
        # Build aliases
        aliases = self._extract_aliases(title, content)
        
        # Build temporal validity
        temporal = self._build_temporal_validity(year, domains)
        
        # Update metadata
        metadata.update({
            "authority_tier": authority_tier,
            "evidence_level": h_level,
            "precedence": precedence,
            "domain": domains,
            "doc_type": doc_type,
            "aliases": aliases,
            "temporal": temporal,
            "original_file": file_path.name
        })
        
        # Add disclaimers to metadata if present
        if disclaimers:
            metadata["nonclinical_notes"] = disclaimers
        
        # Create standardized document
        standardized = {
            "doc_id": doc_id,  # FIX 1: Always doc_id, not id
            "title": title,
            "abstract": abstract,
            "content": content,
            "year": year,  # FIX 2: Year at top level
            "h_level": h_level,  # FIX 2: H-level at top level
            "metadata": metadata,
            "sections": sections,
            "tables_markdown": tables_markdown,
            "tables_struct": tables_struct
        }
        
        # Add references if present
        if "references" in data:
            standardized["references"] = data["references"]
        
        # Emit warnings
        self._emit_warnings(file_path.name, year, domains, doc_type)
        
        return standardized
    
    def _normalize_id(self, data: Dict, filename: str) -> str:
        """FIX 1: Ensure doc_id exists, copying from id if needed."""
        if "doc_id" in data and data["doc_id"]:
            return data["doc_id"]
        elif "id" in data and data["id"]:
            return data["id"]
        else:
            return filename
    
    def _extract_and_clean_title(self, data: Dict) -> str:
        """Extract and clean title from various locations."""
        title = ""
        
        # Check metadata first
        if "metadata" in data and isinstance(data["metadata"], dict):
            title = data["metadata"].get("title", "")
        
        # Fallback to top-level
        if not title:
            title = data.get("title", "")
        
        return normalize_text(title)
    
    def _extract_and_clean_abstract(self, data: Dict) -> str:
        """Extract and clean abstract from various locations."""
        abstract = ""
        
        # Check metadata first
        if "metadata" in data and isinstance(data["metadata"], dict):
            abstract = data["metadata"].get("abstract", "")
        
        # Check sections
        if not abstract and "sections" in data:
            for section in data["sections"]:
                if isinstance(section, dict):
                    if section.get("title", "").lower() in ["abstract", "bstract"]:
                        abstract = section.get("content", "")
                        break
        
        # Fallback to top-level
        if not abstract:
            abstract = data.get("abstract", "")
        
        return normalize_text(abstract)
    
    def _fix_broken_sections(self, sections: List) -> List:
        """FIX 5: Repair broken OCR headings in sections."""
        fixed_sections = []
        
        for section in sections:
            if isinstance(section, dict):
                fixed_section = dict(section)
                
                # Fix title if present
                if "title" in fixed_section:
                    title = fixed_section["title"]
                    
                    # Remove leading ## if present
                    title = re.sub(r"^#+\s*", "", title)
                    
                    # Check for known broken patterns
                    title_lower = title.lower()
                    for broken, fixed in self.HEADING_FIXES.items():
                        if title_lower == broken:
                            fixed_section["title"] = fixed
                            break
                    else:
                        # Clean and normalize
                        fixed_section["title"] = clean_section_title(title)
                
                # Clean content
                if "content" in fixed_section:
                    fixed_section["content"] = normalize_text(fixed_section["content"])
                
                fixed_sections.append(fixed_section)
            else:
                fixed_sections.append(section)
        
        return fixed_sections
    
    def _extract_disclaimers(self, data: Dict, sections: List, sections_text: str) -> Tuple[str, str]:
        """FIX 7: Extract disclaimers and nonclinical content."""
        disclaimers = []
        content = sections_text
        
        # Check for disclaimers in content
        for pattern in self.DISCLAIMER_PATTERNS:
            matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
            for match in matches:
                disclaimers.append(match.strip())
                content = content.replace(match, "")
        
        # Clean up multiple newlines left by removal
        content = re.sub(r"\n{3,}", "\n\n", content)
        
        disclaimer_text = "\n\n".join(disclaimers) if disclaimers else ""
        return content.strip(), disclaimer_text
    
    def _build_content_from_sections(self, sections: List, abstract: str) -> str:
        """FIX 6: Build content from sections if empty."""
        parts = []
        
        if abstract:
            parts.append(abstract)
        
        for section in sections:
            if isinstance(section, dict):
                title = section.get("title", "")
                text = section.get("content", "")
                
                if title and text:
                    parts.append(f"## {title}\n\n{text}")
                elif text:
                    parts.append(text)
        
        return "\n\n".join(parts)
    
    def _extract_and_validate_year(self, data: Dict, metadata: Dict, content: str) -> int:
        """FIX 2: Extract year and ensure it's at top level."""
        year = 0
        
        # Check metadata
        if "year" in metadata:
            year = int(metadata["year"])
        # Check top level
        elif "year" in data:
            year = int(data["year"])
        # Try to extract from content
        else:
            year_match = re.search(r"\b(19[89]\d|20[012]\d)\b", content)
            if year_match:
                year = int(year_match.group(0))
        
        return year
    
    def _assign_authority_tier(self, metadata: Dict, filename: str) -> str:
        """FIX 3: Assign authority tier based on filename patterns first."""
        # Check filename patterns (most reliable)
        if filename.startswith("papoip_"):
            return "A1"
        elif filename.startswith("practical_"):
            return "A2"
        elif filename.startswith("bacada_"):
            return "A3"
        
        # Fallback to book title
        book = (metadata.get("book") or "").lower()
        year = int(metadata.get("year") or 0)
        
        if "principles and practice of interventional pulmonology" in book and year >= 2025:
            return "A1"
        elif "practical guide to interventional pulmonology" in book:
            return "A2"
        elif "bronchoscopy and central airway disorders" in book:
            return "A3"
        
        return "A4"
    
    def _determine_doc_type(self, title: str, content: str, filename: str) -> str:
        """FIX 4: Determine doc_type with RCT detection override."""
        text = f"{title}\n{content}".lower()
        
        # Check if it's from a book (book chapter)
        if filename.startswith(("papoip_", "practical_", "bacada_")):
            return "book_chapter"
        
        # Check for RCT signals (highest priority)
        rct_patterns = [
            r"\brandomi[sz]ed\s+(controlled\s+)?trial\b",
            r"\brct\b",
            r"\bdouble[\s-]blind\b",
            r"\bplacebo[\s-]controlled\b",
            r"\brandom\s+allocation\b",
            r"\brandomly\s+assigned\b"
        ]
        
        for pattern in rct_patterns:
            if re.search(pattern, text):
                return "rct"
        
        # Check for systematic review/meta-analysis
        if "systematic review" in text or "meta-analysis" in text or "meta analysis" in text:
            return "systematic_review"
        
        # Check for guidelines
        if any(term in text for term in ["guideline", "expert panel", "consensus statement", "position statement"]):
            return "guideline"
        
        # Check for coding/billing
        if any(term in text for term in ["cpt", "wrvu", "rvu", "coding", "billing", "reimbursement"]):
            return "coding_update"
        
        # Check for cohort study
        if any(term in text for term in ["cohort", "prospective study", "retrospective study", "observational"]):
            return "cohort"
        
        # Check for case series/report
        if "case series" in text or "case report" in text:
            return "case_series"
        
        # Default
        return "narrative_review"
    
    def _infer_domains(self, title: str, journal: str, content: str) -> List[str]:
        """Infer domain categories from content."""
        text = f"{title}\n{journal}\n{content}".lower()
        domains = []
        
        if any(term in text for term in ["cpt", "rvu", "wrvu", "coding", "billing", "reimbursement"]):
            domains.append("coding_billing")
        
        if any(term in text for term in ["ablation", "radiofrequency", "microwave", "cryoablation", "rfa", "mwa"]):
            domains.append("ablation")
        
        if any(term in text for term in ["endobronchial valve", "bronchoscopic lung volume reduction", 
                                          "blvr", "zephyr", "spiration", "chartis"]):
            domains.append("lung_volume_reduction")
        
        if any(term in text for term in ["navigation", "electromagnetic", "enb", "radial probe", 
                                          "rp-ebus", "ebus", "tbna", "vbn", "btpna"]):
            domains.append("technology_navigation")
        
        if any(term in text for term in ["training", "competency", "education", "fellowship", 
                                          "curriculum", "supervised", "maintenance"]):
            domains.append("training_competency")
        
        return domains if domains else ["clinical"]
    
    def _determine_h_level(self, doc_type: str, content: str) -> str:
        """Determine evidence hierarchy level."""
        if doc_type in ["guideline", "systematic_review"]:
            return "H1"
        elif doc_type == "rct":
            return "H2"  # RCTs should be H2, not H1
        elif doc_type in ["cohort", "coding_update", "book_chapter"]:
            return "H3"
        elif doc_type in ["case_series", "case_report"]:
            return "H4"
        else:
            return "H3"  # Default for narrative reviews
    
    def _calculate_precedence(self, tier: str, h_level: str, year: int, domains: List[str]) -> float:
        """Calculate precedence with domain-aware recency."""
        current_year = datetime.now().year
        age = max(0, current_year - year) if year else 10  # Default age if no year
        
        # Domain-specific half-life
        half_life = 6.0
        if "coding_billing" in domains:
            half_life = 3.0
        elif "ablation" in domains:
            half_life = 5.0
        elif "technology_navigation" in domains:
            half_life = 4.0
        
        # Calculate recency weight
        recency_weight = 0.5 ** (age / half_life)
        
        # A1 floor
        if tier == "A1":
            recency_weight = max(0.70, recency_weight)
        
        # Weights
        authority_weights = {"A1": 1.00, "A2": 0.90, "A3": 0.70, "A4": 0.65}
        h_weights = {"H1": 1.00, "H2": 0.85, "H3": 0.65, "H4": 0.45}
        
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
        
        if "tables" not in data:
            return [], []
        
        tables = data.get("tables", [])
        if not isinstance(tables, list):
            return [], []
        
        for table in tables:
            if not isinstance(table, dict):
                continue
                
            headers = table.get("headers", [])
            rows = table.get("rows", [])
            
            if not headers:
                continue
            
            # Clean headers
            headers = [clean_table_cell(str(h)) for h in headers]
            
            # Build markdown
            md_lines = []
            caption = table.get("caption", "")
            if caption:
                md_lines.append(f"**{caption}**\n")
            
            md_lines.append("| " + " | ".join(headers) + " |")
            md_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
            
            # Process rows
            for row in rows:
                if not row:
                    continue
                    
                clean_row = [clean_table_cell(str(cell)) for cell in row[:len(headers)]]
                # Pad if needed
                while len(clean_row) < len(headers):
                    clean_row.append("")
                    
                md_lines.append("| " + " | ".join(clean_row) + " |")
                
                # Create structured row
                row_dict = {}
                for i, header in enumerate(headers):
                    key = header.strip().lower().replace(" ", "_")
                    value = clean_row[i] if i < len(clean_row) else ""
                    row_dict[key] = value
                
                # Extract CPT/wRVU rows
                if any(k in row_dict for k in ["cpt", "cpt_code", "procedure_code", "wrvu", "rvu"]):
                    tables_struct.append(row_dict)
            
            tables_markdown.append("\n".join(md_lines))
        
        return tables_markdown, tables_struct
    
    def _extract_aliases(self, title: str, content: str) -> List[str]:
        """Extract relevant aliases and acronyms."""
        text = f"{title}\n{content}".lower()
        aliases = []
        
        alias_patterns = {
            "ebus": ["ebus", "endobronchial ultrasound"],
            "tbna": ["tbna", "transbronchial needle"],
            "enb": ["enb", "electromagnetic navigation"],
            "vbn": ["vbn", "virtual bronchoscopic"],
            "blvr": ["blvr", "bronchoscopic lung volume"],
            "pdt": ["pdt", "photodynamic therapy"],
            "rose": ["rose", "rapid on-site"],
            "zephyr": ["zephyr"],
            "spiration": ["spiration"],
            "chartis": ["chartis"]
        }
        
        for alias, patterns in alias_patterns.items():
            if any(p in text for p in patterns):
                aliases.append(alias)
        
        return list(set(aliases))
    
    def _build_temporal_validity(self, year: int, domains: List[str]) -> Dict:
        """Build temporal validity information."""
        temporal = {
            "valid_from": f"{year}-01-01" if year else None,
            "valid_until": None,
            "last_seen_year": year if year else None
        }
        
        # Special handling for coding content
        if "coding_billing" in domains and year:
            temporal["valid_until"] = f"{year + 2}-12-31"
        
        return temporal
    
    def _get_all_sections_text(self, data: Dict, sections: List) -> str:
        """Extract all text for analysis."""
        parts = []
        
        # Use fixed sections
        for section in sections:
            if isinstance(section, dict):
                parts.append(section.get("content", ""))
        
        # Check for text_chunks (book format)
        if not parts and "text_chunks" in data:
            for chunk in data.get("text_chunks", []):
                if isinstance(chunk, dict) and "text" in chunk:
                    parts.append(chunk["text"])
        
        # Fallback to content field
        if not parts and "content" in data:
            parts.append(data["content"])
        
        return "\n\n".join(parts)
    
    def _extract_metadata(self, data: Dict) -> Dict:
        """Extract and consolidate metadata."""
        meta = {}
        
        # Check nested metadata
        if "metadata" in data and isinstance(data["metadata"], dict):
            source = data["metadata"]
        else:
            source = data
        
        # Extract fields
        meta["book"] = source.get("book", "")
        meta["journal"] = source.get("journal", "")
        meta["year"] = source.get("year", source.get("publication_year", 0))
        meta["authors"] = source.get("authors", [])
        meta["doi"] = source.get("doi", "")
        meta["pmid"] = source.get("pmid", "")
        meta["volume"] = source.get("volume", "")
        meta["issue"] = source.get("issue", "")
        meta["pages"] = source.get("pages", "")
        
        return meta
    
    def _emit_warnings(self, filename: str, year: int, domains: List[str], doc_type: str):
        """Emit warnings for outdated content."""
        current_year = datetime.now().year
        
        # Warn for old coding content
        if "coding_billing" in domains and year and (current_year - year) >= 4:
            print(f"  ⚠️  {filename}: Coding content from {year} may be outdated")
        
        # Info for RCT detection
        if doc_type == "rct":
            print(f"  ✓ {filename}: Detected as RCT")
        
        # Info for book chapters
        if doc_type == "book_chapter":
            print(f"  📚 {filename}: Book chapter identified")


if __name__ == "__main__":
    preparer = DataPreparerV12Fixed()
    preparer.process_all_files()