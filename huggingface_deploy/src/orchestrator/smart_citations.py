"""Smart citation insertion based on content matching."""

import re
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

# Load citation index
_citation_index: Optional[Dict] = None

def load_citation_index() -> Dict:
    """Load the pre-built citation index."""
    global _citation_index
    if _citation_index is None:
        index_path = Path("data/citation_index.json")
        if index_path.exists():
            with open(index_path, 'r') as f:
                _citation_index = json.load(f)
                logger.info(f"Loaded citation index with {len(_citation_index)} entries")
        else:
            _citation_index = {}
            logger.warning("Citation index not found at data/citation_index.json")
    return _citation_index


def insert_smart_citations(response_text: str, 
                          article_sources: List[Any],
                          max_citations: int = 6) -> Tuple[str, List[Dict[str, str]]]:
    """
    Intelligently insert numbered citations based on content matching.
    
    Returns:
        Tuple of (response_with_citations, citation_list)
    """
    if not article_sources:
        return response_text, []
    
    # Key medical concepts to match
    concept_patterns = [
        # Procedures
        (r'\b(surgical repair|primary repair|surgery|resection)\b', 'surgical'),
        (r'\b(stent|stenting|covered stent|metallic stent|SEMS)\b', 'stent'),
        (r'\b(endoscopic|bronchoscop|esophagoscop)\b', 'endoscopic'),
        (r'\b(closure|seal|occlusion|clips?|OTSC)\b', 'closure'),
        
        # Conditions
        (r'\b(fistula|TEF|tracheoesophageal|tracheo-esophageal)\b', 'fistula'),
        (r'\b(benign|non-?malignant|acquired)\b', 'benign'),
        (r'\b(malignant|cancer|tumor|neoplastic)\b', 'malignant'),
        
        # Management
        (r'\b(management|treatment|therapy|intervention)\b', 'management'),
        (r'\b(outcomes?|prognosis|survival|mortality)\b', 'outcomes'),
        (r'\b(complications?|adverse|risks?)\b', 'complications'),
        
        # Specific techniques
        (r'\b(double stenting|combined stent|dual stent)\b', 'double_stent'),
        (r'\b(muscle flap|tissue interposition|flap)\b', 'flap'),
        (r'\b(NPO|nutrition|feeding|jejunostomy|parenteral)\b', 'nutrition'),
    ]
    
    # Score each article based on concept matches
    article_scores = []
    for article in article_sources:
        score = 0
        matched_concepts = set()
        
        article_text = (article.text[:1000] + " " + getattr(article, 'doc_id', '')).lower()
        response_lower = response_text.lower()
        
        for pattern, concept in concept_patterns:
            if re.search(pattern, response_lower, re.I):
                # Concept appears in response
                if re.search(pattern, article_text, re.I):
                    # Article discusses this concept
                    score += 2
                    matched_concepts.add(concept)
        
        # Bonus for year relevance (prefer recent for procedures)
        year = getattr(article, 'year', 2020)
        if year >= 2020:
            score += 1
        elif year >= 2015:
            score += 0.5
            
        article_scores.append({
            'article': article,
            'score': score,
            'concepts': matched_concepts
        })
    
    # Sort by score and select top articles
    article_scores.sort(key=lambda x: x['score'], reverse=True)
    selected = article_scores[:max_citations]
    
    # Filter out zero-score articles
    selected = [a for a in selected if a['score'] > 0]
    
    if not selected:
        # No good matches, just return top articles
        selected = article_scores[:min(3, len(article_scores))]
    
    # Load citation index
    citation_index = load_citation_index()
    
    # Create citation list
    citations = []
    citation_map = {}
    
    for i, item in enumerate(selected, 1):
        article = item['article']
        doc_id = getattr(article, 'doc_id', '')
        
        # Look up in citation index first
        if doc_id in citation_index:
            indexed = citation_index[doc_id]
            author = indexed.get('author', 'Unknown')
            year = indexed.get('year', 2024)
            title = indexed.get('title', '')
        else:
            # Fallback to extraction if not in index
            author = extract_author_name(doc_id)
            year = getattr(article, 'year', 2024)
            title = ''
        
        # Clean up author name
        if author and author != 'Unknown':
            citation_text = f"{author} et al. ({year})"
        else:
            citation_text = f"Study ({year})"
        
        citation = {
            'number': str(i),
            'text': citation_text,
            'doc_id': doc_id,
            'title': title,
            'concepts': list(item['concepts'])
        }
        citations.append(citation)
        citation_map[i] = citation
    
    # Insert citations strategically in the response
    response_with_citations = add_citation_numbers(
        response_text, 
        citations, 
        concept_patterns
    )
    
    return response_with_citations, citations


def add_citation_numbers(text: str, 
                         citations: List[Dict], 
                         concept_patterns: List[Tuple]) -> str:
    """Add citation numbers at the end of relevant sentences."""
    
    if not citations:
        return text
    
    # Split into sentences
    sentences = re.split(r'(\. |\.\n|\? |\?\n|! |!\n)', text)
    
    modified_sentences = []
    citations_used = set()
    
    for i, sentence in enumerate(sentences):
        if not sentence.strip():
            modified_sentences.append(sentence)
            continue
            
        # Check if this sentence discusses concepts from any citation
        sentence_lower = sentence.lower()
        relevant_citations = []
        
        for citation in citations:
            for concept in citation.get('concepts', []):
                # Find pattern for this concept
                for pattern, pattern_concept in concept_patterns:
                    if pattern_concept == concept:
                        if re.search(pattern, sentence_lower, re.I):
                            if citation['number'] not in relevant_citations:
                                relevant_citations.append(citation['number'])
                            break
        
        # Add citations at end of sentence
        if relevant_citations and i % 2 == 0:  # Even indices are sentences
            # Don't add if sentence already has citations
            if not re.search(r'\[\d+\]', sentence):
                # Add before period if exists
                if sentence.rstrip().endswith('.'):
                    sentence = sentence.rstrip()[:-1] + f" [{', '.join(relevant_citations)}]."
                elif sentence.rstrip().endswith(')'):
                    sentence = sentence.rstrip() + f" [{', '.join(relevant_citations)}]"
                else:
                    sentence = sentence + f" [{', '.join(relevant_citations)}]"
                
                for num in relevant_citations:
                    citations_used.add(num)
        
        modified_sentences.append(sentence)
    
    result = ''.join(modified_sentences)
    
    # Ensure all citations are used at least once
    unused = [c['number'] for c in citations if c['number'] not in citations_used]
    if unused and len(unused) <= 2:
        # Add remaining citations to the last substantial paragraph
        paragraphs = result.split('\n\n')
        if paragraphs:
            last_para = paragraphs[-1]
            if len(last_para) > 50:  # Substantial paragraph
                if last_para.rstrip().endswith('.'):
                    paragraphs[-1] = last_para.rstrip()[:-1] + f" [{', '.join(unused)}]."
                else:
                    paragraphs[-1] = last_para + f" [{', '.join(unused)}]"
                result = '\n\n'.join(paragraphs)
    
    return result


def extract_author_name(doc_id: str) -> str:
    """Extract author name from doc_id."""
    # Common patterns in doc_ids:
    # "Schweigert-2019-[Interventional treatment of t..."
    # "Kim-2020-Management of tracheo-oesophageal fis..."
    # "author_year_title.pdf"
    
    # Remove file extension
    doc_id = re.sub(r'\.pdf$', '', doc_id, flags=re.I)
    
    # Pattern 1: Author-Year-Title format
    match = re.match(r'^([A-Za-z]+)[-_](\d{4})[-_]', doc_id)
    if match:
        author = match.group(1)
        return author.capitalize()
    
    # Pattern 2: Author_Year_Title format
    match = re.match(r'^([A-Za-z]+)_(\d{4})_', doc_id)
    if match:
        author = match.group(1)
        return author.capitalize()
    
    # Pattern 3: Just take first part before delimiter
    for delimiter in ['-', '_', ' ']:
        if delimiter in doc_id:
            parts = doc_id.split(delimiter)
            if parts[0] and parts[0].replace('.', '').isalpha():
                return parts[0].capitalize()
    
    # Last resort - clean up and use what we have
    author = re.sub(r'[^A-Za-z].*', '', doc_id)
    if author:
        return author.capitalize()
    
    return "Study"