#!/usr/bin/env python3
"""
Build a citation index mapping doc_id to proper author names and metadata.
This allows accurate citation formatting without parsing doc_ids.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def extract_author_from_content(doc: Dict) -> str:
    """Extract first author from document content."""
    
    # Try to get from metadata first
    if 'metadata' in doc:
        meta = doc['metadata']
        if 'authors' in meta and meta['authors']:
            # Get first author
            first_author = meta['authors'][0] if isinstance(meta['authors'], list) else meta['authors']
            # Clean up author name
            first_author = re.sub(r'[^A-Za-z\s\-]', '', str(first_author))
            return first_author.split()[0] if first_author else "Unknown"
        
        if 'author' in meta and meta['author']:
            author = str(meta['author'])
            author = re.sub(r'[^A-Za-z\s\-]', '', author)
            return author.split()[0] if author else "Unknown"
    
    # Try to extract from text (look for common author patterns)
    text = doc.get('text', '')[:2000]  # First 2000 chars
    
    # Pattern 1: "by Author Name" or "Author Name, MD"
    author_patterns = [
        r'by\s+([A-Z][a-z]+)\s+[A-Z]',
        r'^([A-Z][a-z]+)\s+[A-Z][a-z]+,?\s+(?:MD|PhD|DO)',
        r'([A-Z][a-z]+)\s+et\s+al[,\.]',
        r'([A-Z][a-z]+)\s+and\s+[A-Z][a-z]+',
    ]
    
    for pattern in author_patterns:
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            return match.group(1)
    
    return None


def build_citation_index(data_dir: Path = Path("data/processed")) -> Dict:
    """Build citation index from processed documents."""
    
    citation_index = {}
    
    # Process all JSON files
    json_files = list(data_dir.glob("*.json"))
    logger.info(f"Processing {len(json_files)} documents")
    
    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                doc = json.load(f)
            
            doc_id = doc.get('doc_id', json_file.stem)
            
            # Skip textbooks
            if any(pattern in doc_id.lower() for pattern in ['papoip', 'practical_guide', 'bacada', '_enriched']):
                continue
            
            # Extract metadata
            year = doc.get('year', 2024)
            doc_type = doc.get('doc_type', 'journal_article')
            
            # Extract title (clean it up)
            title = doc.get('title', '')
            if not title and 'metadata' in doc:
                title = doc['metadata'].get('title', '')
            
            # Clean title
            title = re.sub(r'\[.*?\]', '', title)  # Remove brackets
            title = re.sub(r'\s+', ' ', title).strip()
            if len(title) > 100:
                title = title[:97] + "..."
            
            # Extract author
            author = extract_author_from_content(doc)
            
            # If still no author, try to get from doc_id
            if not author or author == "Unknown":
                # Handle doc_ids that start with topic (e.g., "fistula Schweigert-2019-...")
                cleaned_id = doc_id
                
                # Remove leading topic words
                topic_prefixes = ['fistula', 'stent', 'ablation', 'bronchoscopy', 'biopsy']
                for prefix in topic_prefixes:
                    if cleaned_id.lower().startswith(prefix + ' '):
                        cleaned_id = cleaned_id[len(prefix)+1:].strip()
                        break
                
                # Pattern: Author-Year-Title or Author_Year_Title
                match = re.match(r'^([A-Za-z]+)[-_](\d{4})', cleaned_id)
                if match:
                    author = match.group(1).capitalize()
                    if not year or year == 2024:  # Update year if default
                        year = int(match.group(2))
            
            # Build citation entry
            citation_index[doc_id] = {
                'author': author or 'Unknown',
                'year': year,
                'title': title,
                'doc_type': doc_type,
                'ama_format': f"{author or 'Unknown'} et al. {title}. {year}." if title else f"{author or 'Unknown'} et al. ({year})"
            }
            
            logger.debug(f"Indexed: {doc_id} -> {author} ({year})")
            
        except Exception as e:
            logger.error(f"Error processing {json_file}: {e}")
            continue
    
    logger.info(f"Built index with {len(citation_index)} citations")
    return citation_index


def save_citation_index(citation_index: Dict, output_path: Path = Path("data/citation_index.json")):
    """Save citation index to JSON file."""
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(citation_index, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Saved citation index to {output_path}")


def main():
    """Build and save citation index."""
    
    # Build index
    citation_index = build_citation_index()
    
    # Save it
    save_citation_index(citation_index)
    
    # Print sample
    print("\nSample citations:")
    for doc_id, citation in list(citation_index.items())[:5]:
        print(f"  {doc_id}:")
        print(f"    Author: {citation['author']}")
        print(f"    Year: {citation['year']}")
        print(f"    Title: {citation['title'][:60]}...")
        print()


if __name__ == "__main__":
    main()