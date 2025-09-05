#!/usr/bin/env python3
"""
Fix chunk quality issues:
- Normalize headings in chunk text
- Merge short chunks (<80 tokens) or drop boilerplate
- Split long chunks (>600 tokens) at sentence boundaries
- Deduplicate exact repeats within same doc
- Fill missing metadata
- Tag high-value chunks (tables, contraindications, doses)
"""

import json
import re
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional
import argparse
from collections import defaultdict
import tiktoken

# Initialize tokenizer
tokenizer = tiktoken.get_encoding("cl100k_base")

# Heading fix patterns (from heading_fixes.yaml)
HEADING_FIXES = {
    "## etting": "## Setting",
    "## atients": "## Patients", 
    "## esults": "## Results",
    "## onclusion": "## Conclusion",
    "## ethod": "## Method",
    "## bjective": "## Objective",
    "## ackground": "## Background",
    "## ntroduction": "## Introduction",
    "## iscussion": "## Discussion",
    "## eferences": "## References",
    "## igure": "## Figure",
    "## able": "## Table",
}

# High-value content patterns
TABLE_PATTERNS = [
    r'\|.*\|.*\|',  # Markdown table
    r'┌─.*─┐',  # Box drawing
    r'Table \d+',
    r'(?:CPT|ICD|wRVU|RVU)',
]

CONTRAINDICATION_PATTERNS = [
    r'\b(?:contraindic|absolute(?:ly)?\s+contraindic|relative(?:ly)?\s+contraindic|caution|avoid|do not|should not|must not)\b',
    r'\b(?:pregnancy|pregnan|pediatric|children|infant)\b',
    r'\b(?:allergy|allergic|hypersensitiv|anaphyla)',
]

DOSE_SETTING_PATTERNS = [
    r'\d+\s*(?:mg|mcg|μg|ml|cc|units?|IU|joules?|J|watts?|W|°C|celsius|fahrenheit)',
    r'\d+\s*(?:seconds?|minutes?|hours?|min|sec|hr)',
    r'\d+\s*(?:mm|cm|Fr|French|gauge)',
    r'(?:dose|dosage|dosing|energy|power|temperature|duration|size)',
]

def normalize_headings(text: str) -> str:
    """Fix OCR artifacts in headings."""
    if not text:
        return ""
    
    lines = []
    for line in text.splitlines():
        if line.startswith("## "):
            # Apply exact fixes
            for bad, good in HEADING_FIXES.items():
                if line.startswith(bad):
                    line = good
                    break
            # Ensure first letter after ## is capitalized
            if len(line) > 3 and line[3].islower():
                line = "## " + line[3].upper() + line[4:]
        lines.append(line)
    
    return "\n".join(lines)

def count_tokens(text: str) -> int:
    """Count tokens in text."""
    return len(tokenizer.encode(text))

def split_at_sentence(text: str, max_tokens: int = 600) -> List[str]:
    """Split text at sentence boundaries."""
    # Simple sentence splitting
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    chunks = []
    current = []
    current_tokens = 0
    
    for sent in sentences:
        sent_tokens = count_tokens(sent)
        
        if current_tokens + sent_tokens > max_tokens and current:
            chunks.append(' '.join(current))
            current = [sent]
            current_tokens = sent_tokens
        else:
            current.append(sent)
            current_tokens += sent_tokens
    
    if current:
        chunks.append(' '.join(current))
    
    return chunks

def is_boilerplate(text: str) -> bool:
    """Check if text is boilerplate/copyright."""
    lower = text.lower()
    if len(text) < 100:
        boilerplate_patterns = [
            r'copyright\s*©?\s*\d{4}',
            r'all rights reserved',
            r'reprinted with permission',
            r'doi:\s*10\.\d+',
            r'^\s*\d+\s*$',  # Just page numbers
            r'^\s*references?\s*$',
            r'^\s*acknowledgments?\s*$',
        ]
        for pattern in boilerplate_patterns:
            if re.search(pattern, lower):
                return True
    return False

def compute_text_hash(text: str) -> str:
    """Compute hash of normalized text."""
    # Normalize whitespace for dedup
    normalized = re.sub(r'\s+', ' ', text.strip().lower())
    return hashlib.md5(normalized.encode()).hexdigest()

def has_table(text: str) -> bool:
    """Check if text contains a table."""
    for pattern in TABLE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False

def has_contraindication(text: str) -> bool:
    """Check if text contains contraindication info."""
    for pattern in CONTRAINDICATION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False

def has_dose_setting(text: str) -> bool:
    """Check if text contains dose/setting info."""
    for pattern in DOSE_SETTING_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False

def ensure_metadata(chunk: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure all required metadata fields are present."""
    # Required fields with defaults
    defaults = {
        'doc_id': chunk.get('id', 'unknown'),
        'section_title': chunk.get('section', ''),
        'section_type': 'general',
        'h_level': 'H3',  # Conservative default
        'authority_tier': 'A4',  # Conservative default
        'year': 2024,  # Current year as fallback
        'evidence_level': chunk.get('h_level', 'H3'),
    }
    
    for field, default_value in defaults.items():
        if field not in chunk or chunk[field] is None:
            chunk[field] = default_value
    
    # Ensure h_level is valid
    if chunk.get('h_level') not in ['H1', 'H2', 'H3', 'H4']:
        chunk['h_level'] = 'H3'
    
    # Ensure authority_tier is valid
    if chunk.get('authority_tier') not in ['A1', 'A2', 'A3', 'A4']:
        chunk['authority_tier'] = 'A4'
    
    # Ensure year is int
    if not isinstance(chunk.get('year'), int):
        try:
            chunk['year'] = int(chunk['year'])
        except:
            chunk['year'] = 2024
    
    return chunk

def process_chunks(input_file: Path, output_file: Path, dry_run: bool = False) -> Dict[str, Any]:
    """Process and fix all chunks."""
    
    print(f"Loading chunks from {input_file}...")
    chunks = []
    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                chunks.append(json.loads(line))
    
    print(f"Loaded {len(chunks)} chunks")
    
    # Group chunks by doc_id for dedup and merging
    doc_chunks = defaultdict(list)
    for i, chunk in enumerate(chunks):
        doc_id = chunk.get('doc_id', chunk.get('id', f'unknown_{i}'))
        doc_chunks[doc_id].append(chunk)
    
    fixed_chunks = []
    stats = {
        'total_original': len(chunks),
        'normalized_headings': 0,
        'merged_short': 0,
        'split_long': 0,
        'dropped_boilerplate': 0,
        'deduplicated': 0,
        'metadata_fixed': 0,
        'tagged_table': 0,
        'tagged_contra': 0,
        'tagged_dose': 0,
    }
    
    for doc_id, chunks_list in doc_chunks.items():
        # Track text hashes for dedup
        seen_hashes = set()
        doc_fixed = []
        
        i = 0
        while i < len(chunks_list):
            chunk = chunks_list[i].copy()  # Work on copy
            original_text = chunk.get('text', '')
            
            # 1. Normalize headings
            normalized = normalize_headings(original_text)
            if normalized != original_text:
                chunk['text'] = normalized
                stats['normalized_headings'] += 1
            
            # 2. Check chunk length
            tokens = count_tokens(chunk['text'])
            
            if tokens < 80:
                # Check if boilerplate
                if is_boilerplate(chunk['text']):
                    stats['dropped_boilerplate'] += 1
                    i += 1
                    continue
                
                # Try to merge with next chunk if from same section
                if i + 1 < len(chunks_list):
                    next_chunk = chunks_list[i + 1]
                    if (chunk.get('section_title') == next_chunk.get('section_title') and
                        count_tokens(chunk['text'] + '\n\n' + next_chunk['text']) < 600):
                        # Merge chunks
                        chunk['text'] = chunk['text'] + '\n\n' + next_chunk['text']
                        stats['merged_short'] += 1
                        i += 2  # Skip next chunk
                    else:
                        i += 1
                else:
                    i += 1
            
            elif tokens > 600:
                # Split long chunk
                splits = split_at_sentence(chunk['text'], max_tokens=500)
                if len(splits) > 1:
                    stats['split_long'] += 1
                    for j, split_text in enumerate(splits):
                        split_chunk = chunk.copy()
                        split_chunk['text'] = split_text
                        split_chunk['id'] = f"{chunk.get('id', '')}_{j}"
                        doc_fixed.append(split_chunk)
                    i += 1
                    continue
                else:
                    i += 1
            else:
                i += 1
            
            # 3. Deduplicate
            text_hash = compute_text_hash(chunk['text'])
            if text_hash in seen_hashes:
                stats['deduplicated'] += 1
                continue
            seen_hashes.add(text_hash)
            
            # 4. Ensure metadata
            original_meta = chunk.copy()
            chunk = ensure_metadata(chunk)
            if chunk != original_meta:
                stats['metadata_fixed'] += 1
            
            # 5. Tag high-value content
            if has_table(chunk['text']):
                chunk['has_table'] = True
                stats['tagged_table'] += 1
            
            if has_contraindication(chunk['text']):
                chunk['has_contraindication'] = True
                stats['tagged_contra'] += 1
            
            if has_dose_setting(chunk['text']):
                chunk['has_dose_setting'] = True
                stats['tagged_dose'] += 1
            
            doc_fixed.append(chunk)
        
        fixed_chunks.extend(doc_fixed)
    
    stats['total_fixed'] = len(fixed_chunks)
    
    # Write output
    if not dry_run:
        print(f"Writing {len(fixed_chunks)} fixed chunks to {output_file}...")
        with open(output_file, 'w', encoding='utf-8') as f:
            for chunk in fixed_chunks:
                f.write(json.dumps(chunk, ensure_ascii=False) + '\n')
    
    return stats

def main():
    parser = argparse.ArgumentParser(description="Fix chunk quality issues")
    parser.add_argument('--input', type=Path, default=Path('data/chunks/chunks.jsonl'))
    parser.add_argument('--output', type=Path, default=Path('data/chunks/chunks_fixed.jsonl'))
    parser.add_argument('--dry-run', action='store_true', help="Don't write output, just report stats")
    
    args = parser.parse_args()
    
    stats = process_chunks(args.input, args.output, args.dry_run)
    
    print("\n=== Chunk Fix Statistics ===")
    print(f"Original chunks: {stats['total_original']}")
    print(f"Fixed chunks: {stats['total_fixed']}")
    print(f"Normalized headings: {stats['normalized_headings']}")
    print(f"Merged short chunks: {stats['merged_short']}")
    print(f"Split long chunks: {stats['split_long']}")
    print(f"Dropped boilerplate: {stats['dropped_boilerplate']}")
    print(f"Deduplicated: {stats['deduplicated']}")
    print(f"Fixed metadata: {stats['metadata_fixed']}")
    print(f"Tagged tables: {stats['tagged_table']}")
    print(f"Tagged contraindications: {stats['tagged_contra']}")
    print(f"Tagged doses/settings: {stats['tagged_dose']}")
    
    if not args.dry_run:
        print(f"\nFixed chunks saved to: {args.output}")

if __name__ == "__main__":
    main()