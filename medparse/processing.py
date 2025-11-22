import re
import logging
from typing import List, Dict, Any, Optional, Literal
from src.contracts.schema import ExtractionResult, SectionNode, TableData, MedicalMetadata, SafetyWarning, Chunk
from medparse.emit.compact import build_paragraph_store, build_chunks, format_metrics

logger = logging.getLogger(__name__)

class ManufacturerMatcher:
    """
    Restores the manufacturer-specific extraction logic from the legacy pipeline.
    """
    PATTERNS = {
        "ERBE": {
            "name": "ERBE Elektromedizin GmbH",
            "patterns": [r"ERBE\s+Elektromedizin", r"ERBE\s+GmbH"],
            "pn_regex": r"No\.\s*(\d{5}-\d{3})",
            "rev_regex": r"([A-Z]\d{6})"  # e.g. D294849
        },
        "Olympus": {
            "name": "Olympus",
            "patterns": [r"Olympus"],
            "pn_regex": r"Model\s*([A-Z0-9-]+)",
            "rev_regex": r"Revision\s*([0-9.]+)"
        },
        "Intuitive": {
            "name": "Intuitive Surgical",
            "patterns": [r"Intuitive\s+Surgical", r"Ion\s+Endoluminal"],
            "pn_regex": r"Part\s*No\.?\s*([0-9-]+)",
            "rev_regex": r"Rev\.?\s*([A-Z0-9]+)"
        }
    }

    def detect(self, text_sample: str) -> Dict[str, str]:
        """
        Scans text for manufacturer signatures.
        """
        meta = {}
        for key, profile in self.PATTERNS.items():
            for pat in profile["patterns"]:
                if re.search(pat, text_sample, re.IGNORECASE):
                    meta["manufacturer"] = profile["name"]
                    
                    # Try to find specific fields using profile regexes
                    pn_match = re.search(profile["pn_regex"], text_sample, re.IGNORECASE)
                    if pn_match:
                        meta["part_number"] = pn_match.group(1)
                        
                    rev_match = re.search(profile["rev_regex"], text_sample)
                    if rev_match:
                        meta["revision"] = rev_match.group(1)
                        
                    return meta
        return meta

class DoclingProcessor:
    def __init__(self):
        self.matcher = ManufacturerMatcher()
        # Regex patterns for metadata (Fallbacks)
        self.PN_PATTERN = re.compile(r'\b(PN|P/N|Part No\.?|Ref\.?|Order No\.?|No\.)\s*[:#]?\s*([A-Z0-9-]{5,})', re.IGNORECASE)
        self.REV_PATTERN = re.compile(r'\b(Rev(?:ision)?|Ver(?:sion)?)\s*[:.]?\s*([A-Z0-9.]{2,})', re.IGNORECASE)
        self.DATE_PATTERN = re.compile(r'\b(20\d{2}[-.]\d{2}(?:[-.]\d{2})?)\b')
        self.MODEL_PATTERN = re.compile(r'\bModel\s*[:.]?\s*([A-Z0-9-\s]+?)(?=\n|$)', re.IGNORECASE)
        self.NCT_PATTERN = re.compile(r'\b(NCT\d{8})\b')

    def process(self, doc_object: Any, doc_id: str, doc_type: Literal["article", "ifu", "textbook"]) -> ExtractionResult:
        """
        Process a Docling Document object into our standardized ExtractionResult.
        """
        logger.info(f"Processing document: {doc_id} (Type: {type(doc_object).__name__})")
        
        # 1. Flatten Text for Metadata Scanning (First 5 pages approx)
        full_text_sample = self._get_full_text_sample(doc_object, max_items=1000)

        # 2. Build Hierarchy
        hierarchy = self._build_hierarchy(doc_object)
        
        # 3. Extract Tables
        tables = self._extract_tables(doc_object)
        table_sentences = []
        for t in tables:
            if t.metadata.get("flattened_description"):
                table_sentences.append({
                    "text": t.metadata["flattened_description"],
                    "table_id": t.id,
                    "caption": t.caption
                })

        # 4. Extract Metadata
        metadata = self._extract_metadata(doc_object, doc_id, doc_type, full_text_sample)
        
        # 5. Safety Warnings (More Aggressive)
        safety_warnings = []
        safety_blocks_added = 0
        if doc_type == "ifu":
            safety_warnings = self._detect_safety_warnings(hierarchy, full_text_sample)
            # Safety Density Logic
            page_count = self._get_page_count(doc_object)
            min_blocks = self._get_min_safety_blocks(page_count)
            if len(safety_warnings) < min_blocks:
                 logger.warning(f"Safety density low: found {len(safety_warnings)}, expected {min_blocks}")

        # 6. Compact Emission (Contracts Parity)
        paragraph_store = build_paragraph_store(hierarchy)
        chunks = build_chunks(paragraph_store, method="smart_split") 
        
        # Metrics
        raw_metrics = {
            "page_count": self._get_page_count(doc_object),
            "chars_extracted": sum(len(c.text) for c in chunks),
            "tables_found": len(tables),
            "safety_blocks_added": safety_blocks_added,
            "gibberish_ratio": 0.0 
        }
        metrics = format_metrics(raw_metrics)

        return ExtractionResult(
            doc_id=doc_id,
            doc_type=doc_type,
            content_hierarchy=hierarchy,
            paragraph_store=paragraph_store,
            chunks=chunks,
            evidence_bank={}, 
            tables=tables,
            table_sentences=table_sentences,
            metadata=metadata,
            safety_warnings=safety_warnings,
            metrics=metrics
        )

    def _extract_metadata(self, doc: Any, doc_id: str, doc_type: str, text_sample: str) -> MedicalMetadata:
        meta = MedicalMetadata(
            title=getattr(doc, "name", doc_id),
            source="Medparse (Docling Enhanced)"
        )
        
        # 1. Manufacturer Detection
        manu_info = self.matcher.detect(text_sample)
        if "manufacturer" in manu_info:
            meta.other["manufacturer"] = manu_info["manufacturer"]
        if "part_number" in manu_info:
            meta.other["part_number"] = manu_info["part_number"]
        if "revision" in manu_info:
             meta.other["revision"] = manu_info["revision"]

        # 2. Fallback Regexes
        if "part_number" not in meta.other:
            m = self.PN_PATTERN.search(text_sample)
            if m: meta.other["part_number"] = m.group(2)
            
        if "revision" not in meta.other:
            m = self.REV_PATTERN.search(text_sample)
            if m: meta.other["revision"] = m.group(2)

        if not meta.publication_date:
            m = self.DATE_PATTERN.search(text_sample)
            if m: meta.publication_date = m.group(1)

        # 3. Model (Heuristic: often near Title or PN)
        if "model" not in meta.other:
            m = self.MODEL_PATTERN.search(text_sample)
            if m: 
                meta.other["model"] = m.group(1).strip()
                
        # 4. Product Name (Heuristic: often the largest text on page 1)
        # For now, default to title or filename stem
        meta.other["product_name"] = meta.title

        # 5. Article Specifics
        if doc_type == "article":
            meta.clinical_trial_ids = self._find_nct_ids(doc)

        return meta

    def _detect_safety_warnings(self, hierarchy: List[SectionNode], full_text: str) -> List[SafetyWarning]:
        """
        Scans both the structured hierarchy AND the raw text for safety blocks.
        """
        warnings = []
        seen_texts = set()

        def _add(text, severity, loc):
            clean = text.strip()
            if clean and clean not in seen_texts and len(clean) > 10:
                warnings.append(SafetyWarning(text=clean, severity=severity, location=loc))
                seen_texts.add(clean)

        # 1. Scan Hierarchy nodes for headers like "WARNING"
        def _scan_nodes(nodes):
            for node in nodes:
                title_upper = node.title.upper()
                content_upper = node.content.upper()
                
                severity = None
                if "WARNING" in title_upper or "WARNING" in content_upper[:20]: severity = "warning"
                elif "CAUTION" in title_upper or "CAUTION" in content_upper[:20]: severity = "caution"
                elif "DANGER" in title_upper or "DANGER" in content_upper[:20]: severity = "danger"
                
                if severity:
                    _add(node.content or node.title, severity, "Section")
                
                _scan_nodes(node.children)
        
        _scan_nodes(hierarchy)

        # 2. Fallback: Regex on raw text if we missed things
        # This catches "boxes" that might have been flattened into text
        keyword_patterns = [
            (r"(?i)WARNING\s*[:!]\s*(.{10,300})", "warning"),
            (r"(?i)CAUTION\s*[:!]\s*(.{10,300})", "caution"),
            (r"(?i)DANGER\s*[:!]\s*(.{10,300})", "danger")
        ]
        
        for pat, sev in keyword_patterns:
            matches = re.finditer(pat, full_text)
            for m in matches:
                _add(m.group(1), sev, "Regex Scan")

        return warnings

    def _get_full_text_sample(self, doc: Any, max_items: int = 1000) -> str:
        """
        Reconstructs a linear text representation of the document for regex scanning.
        """
        text_parts = []
        count = 0
        if hasattr(doc, "iterate_items"):
             for item in doc.iterate_items():
                 payload = item if not isinstance(item, tuple) else item[0]
                 t = self._get_text(payload)
                 if t:
                     text_parts.append(t)
                     count += 1
                 if count > max_items: break
        elif hasattr(doc, "body") and hasattr(doc.body, "children"):
             for item in getattr(doc.body, "children", []):
                 t = self._get_text(item)
                 if t:
                     text_parts.append(t)
                     count += 1
                 if count > max_items: break
        
        return "\n".join(text_parts)

    def _build_hierarchy(self, doc: Any) -> List[SectionNode]:
        roots: List[SectionNode] = []
        stack: List[SectionNode] = []
        
        if not doc: return []

        items_stream = []
        if hasattr(doc, "iterate_items"):
            for payload in doc.iterate_items():
                if isinstance(payload, tuple): items_stream.append(payload[0])
                else: items_stream.append(payload)
        elif hasattr(doc, "body") and hasattr(doc.body, "children"):
            items_stream = getattr(doc.body, "children", [])
        
        current_section: Optional[SectionNode] = None
        
        for child in items_stream:
            is_header = self._is_header(child)
            if is_header:
                level = getattr(child, "level", 1)
                text = self._get_text(child)
                new_node = SectionNode(title=text, level=level, content="", children=[])
                while stack and stack[-1].level >= level: stack.pop()
                if stack: stack[-1].children.append(new_node)
                else: roots.append(new_node)
                stack.append(new_node)
                current_section = new_node
            else:
                text = self._get_text(child)
                if text and current_section:
                    current_section.content += "\n" + text

        return roots

    def _extract_tables(self, doc: Any) -> List[TableData]:
        extracted_tables = []
        if not doc or not hasattr(doc, "tables"): return []
        tables = getattr(doc, "tables", [])
        for idx, table in enumerate(tables):
            data = self._table_to_list(table)
            caption = self._get_caption(table)
            flattened_text = self._flatten_table(data, caption)
            table_data = TableData(
                id=f"table_{idx}",
                caption=caption,
                data=data,
                metadata={"flattened_description": flattened_text}
            )
            extracted_tables.append(table_data)
        return extracted_tables

    def _get_min_safety_blocks(self, page_count: int) -> int:
        if page_count <= 4: return 8
        if page_count < 40: return 12
        return 20

    def _get_page_count(self, doc: Any) -> int:
        if hasattr(doc, "pages") and isinstance(doc.pages, dict): return len(doc.pages)
        val = getattr(doc, "num_pages", 1)
        if callable(val): return val()
        return int(val)

    def _find_nct_ids(self, doc: Any) -> List[str]:
        ids = set()
        # Helper to scan body
        if hasattr(doc, "body"):
             for child in getattr(doc.body, "children", []):
                 text = self._get_text(child)
                 ids.update(self.NCT_PATTERN.findall(text))
        return list(ids)

    # --- Helper methods ---
    
    def _is_header(self, item: Any) -> bool:
        tname = type(item).__name__
        if "SectionHeader" in tname: return True
        if hasattr(item, "label") and str(item.label).lower() in ["section_header", "title", "header"]: return True
        return False

    def _get_text(self, item: Any) -> str:
        text = ""
        if hasattr(item, "text"): text = str(item.text)
        elif hasattr(item, "content"): text = str(item.content)
        elif hasattr(item, "value"): text = str(item.value)
        if not text and hasattr(item, "main_text"): text = str(item.main_text)
        return text.strip()

    def _table_to_list(self, table: Any) -> List[List[str]]:
        if hasattr(table, "export_to_list"): return table.export_to_list()
        return []

    def _get_caption(self, table: Any) -> str:
        return getattr(table, "caption", "") or ""

    def _flatten_table(self, data: List[List[str]], caption: str) -> str:
        sentences = []
        if caption: sentences.append(f"Table caption: {caption}.")
        if not data: return "Empty table."
        headers = data[0]
        rows = data[1:]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(headers):
                    header = headers[i]
                    sentences.append(f"The {header} is {cell}.")
        return " ".join(sentences)