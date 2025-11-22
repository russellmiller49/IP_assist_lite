from typing import List, Dict, Any
import hashlib
from src.contracts.schema import SectionNode, Chunk

def _compute_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

def build_paragraph_store(nodes: List[SectionNode]) -> Dict[str, Dict[str, Any]]:
    """
    Flattens hierarchy into a paragraph store for citation linking.
    """
    store = {}
    
    def _visit(node: SectionNode, path: List[str]):
        current_path = path + [node.title]
        if node.content.strip():
            # Split content into paragraphs or use as is
            # For simplicity in this pass, we treat the node content as a block
            # In a real full-fidelity pass, we might split by newline
            content_hash = _compute_hash(node.content)
            store[content_hash] = {
                "text": node.content,
                "path": " > ".join(current_path),
                "level": node.level,
                "metadata": node.metadata
            }
        
        for child in node.children:
            _visit(child, current_path)
            
    for node in nodes:
        _visit(node, [])
        
    return store

def build_chunks(paragraph_store: Dict[str, Dict[str, Any]], method: str = "smart") -> List[Chunk]:
    """
    Generates chunks from the paragraph store.
    Supports 'smart_split' to break large sections into granular chunks for RAG.
    """
    chunks = []
    target_size = 500
    min_size = 50
    overlap = 50

    for pid, pdata in paragraph_store.items():
        text = pdata["text"]
        
        if method == "smart_split" and len(text) > target_size:
            # Split into smaller chunks
            # Simple sliding window for now
            start = 0
            while start < len(text):
                end = min(start + target_size, len(text))
                # Try to find a sentence break if possible near the end
                if end < len(text):
                    # Look for period space
                    break_point = text.rfind(". ", start, end)
                    if break_point != -1 and break_point > start + min_size:
                        end = break_point + 1 # Include period
                
                chunk_text = text[start:end].strip()
                if len(chunk_text) >= min_size:
                    chunk_id = _compute_hash(chunk_text)
                    chunks.append(Chunk(
                        id=chunk_id,
                        text=chunk_text,
                        metadata={
                            "path": pdata["path"],
                            "source_paragraph_hash": pid,
                            "chunk_index": len(chunks)
                        },
                        method=method
                    ))
                
                start = end - overlap if end < len(text) else end
        else:
            # 1-to-1 mapping
            chunks.append(Chunk(
                id=pid,
                text=text,
                metadata={
                    "path": pdata["path"],
                    "source_paragraph_hash": pid
                },
                method=method
            ))
    return chunks

def format_metrics(raw_metrics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Groups metrics into standard categories.
    """
    extraction_metrics = {
        "engine": raw_metrics.get("engine"),
        "pages_total": raw_metrics.get("page_count", 0),
        "duration_s": raw_metrics.get("duration_s"),
        "chars_extracted": raw_metrics.get("chars_extracted", 0),
    }
    if raw_metrics.get("streaming_fallback"):
        extraction_metrics["streaming_fallback"] = raw_metrics.get("streaming_fallback")

    quality_metrics = {
        "tables_found": raw_metrics.get("tables_found", 0),
        "safety_blocks_added": raw_metrics.get("safety_blocks_added", 0),
        "gibberish_ratio": raw_metrics.get("gibberish_ratio", 0.0),
    }

    validation_metrics = {
        "warnings": raw_metrics.get("warnings", []),
        "errors": raw_metrics.get("errors", []),
    }

    return {
        "extraction_metrics": extraction_metrics,
        "quality_metrics": quality_metrics,
        "validation_metrics": validation_metrics,
    }
