"""Validate and fix metadata extraction issues."""

from typing import Dict, Optional, Any
import re
from datetime import datetime

from src.contracts.schema import ExtractionResult

# We don't have the full SecondPassContext from the old system, 
# so we define a simplified localized version or adapt the logic.

class IFUMetadataValidator:
    def run(self, result: ExtractionResult) -> ExtractionResult:
        """
        Validate and fix common metadata extraction errors in place.
        """
        self._fix_publication_date(result)
        self._fix_model_name(result)
        self._fix_indications_vs_intended(result)
        return result

    def _fix_publication_date(self, result: ExtractionResult):
        # 1. Validate publication_date isn't just a copyright year
        if result.metadata.publication_date:
            date_str = result.metadata.publication_date
            # Check if it's just a year (suspicious)
            if re.match(r'^\d{4}$', date_str):
                # Attempt to find a better date in the first few text blocks
                new_date = self._scan_for_date(result)
                if new_date:
                    result.metadata.publication_date = new_date

    def _scan_for_date(self, result: ExtractionResult) -> Optional[str]:
        # Scan first 10 nodes
        count = 0
        stack = list(reversed(result.content_hierarchy))
        while stack and count < 20:
            node = stack.pop()
            count += 1
            text = node.content or node.title
            # Look for revision dates: 2024-08, 2024.08, etc.
            match = re.search(r'(?:Revision|Rev\.?|Version)\s*:?\s*(\d{4}[\s.-]\d{2})', text, re.IGNORECASE)
            if match:
                clean = match.group(1).replace('.', '-').replace(' ', '-')
                return f"{clean}-01" # Default to first of month
            if node.children:
                stack.extend(reversed(node.children))
        return None

    def _fix_model_name(self, result: ExtractionResult):
        # 2. Validate model isn't "Project" or similar
        # Assuming model is stored in metadata.other['model']
        model = result.metadata.other.get("model")
        if model:
            invalid_models = ["Project", "Draft", "Template", "Document"]
            if model in invalid_models:
                new_model = self._scan_for_model(result)
                if new_model:
                    result.metadata.other["model"] = new_model

    def _scan_for_model(self, result: ExtractionResult) -> Optional[str]:
        count = 0
        stack = list(reversed(result.content_hierarchy))
        while stack and count < 20:
            node = stack.pop()
            count += 1
            text = node.content or node.title
            # Look for Model: XYZ
            match = re.search(r'\bModel\s*:?\s*([A-Z]{1,3}\s?\d{3,4})', text)
            if match:
                return match.group(1)
            if node.children:
                stack.extend(reversed(node.children))
        return None

    def _fix_indications_vs_intended(self, result: ExtractionResult):
        # 3. Ensure indications_for_use is not intended_use
        # These might be stored in metadata or specific sections.
        # For now, we'll check if we can identify them in the hierarchy and tag them.
        pass
