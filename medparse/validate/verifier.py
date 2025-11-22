from typing import List
from src.contracts.schema import ExtractionResult

class ValidationFailure(Exception):
    pass

class Verifier:
    """
    Sanity checks for extraction results before DB insertion.
    """
    
    def __init__(self):
        pass
        
    def verify(self, result: ExtractionResult):
        """
        Runs all checks. Raises ValidationFailure on error.
        """
        self._check_zero_content(result)
        self._check_hierarchy(result)
        self._check_gibberish(result)
        
    def _check_zero_content(self, result: ExtractionResult):
        """Does the document have < 100 words?"""
        total_text = ""
        # Aggregate text from hierarchy
        stack = list(result.content_hierarchy)
        while stack:
            node = stack.pop()
            total_text += node.content
            stack.extend(node.children)
            
        word_count = len(total_text.split())
        if word_count < 100:
            raise ValidationFailure(f"Zero-Content Check Failed: Document {result.doc_id} has only {word_count} words.")

    def _check_hierarchy(self, result: ExtractionResult):
        """Does the document have at least one 'Header'?"""
        if not result.content_hierarchy:
            raise ValidationFailure(f"Hierarchy Check Failed: Document {result.doc_id} has no detected structure/headers.")

    def _check_gibberish(self, result: ExtractionResult):
        """Is the character-to-token ratio abnormal?"""
        total_text = ""
        stack = list(result.content_hierarchy)
        while stack:
            node = stack.pop()
            total_text += node.content
            stack.extend(node.children)
            
        if not total_text:
             # Handled by zero content
             return 
             
        char_count = len(total_text)
        token_count = len(total_text.split()) # Approximation
        
        if token_count == 0:
            return

        ratio = char_count / token_count
        
        # Normal English is around 4.5 - 6 chars per word.
        # If it's > 20 (garbage encoding) or < 2 (spaces missing), flag it.
        if ratio > 25 or ratio < 1.5:
             # Only a warning in some systems, but here we fail for review
             raise ValidationFailure(f"Gibberish Check Failed: Abnormal char/token ratio ({ratio:.2f}). Possible encoding error.")
