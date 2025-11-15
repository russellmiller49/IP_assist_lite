"""Universal metadata extraction with intelligent prioritization."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple


class UniversalDateExtractor:
    """Extract dates with universal priority rules."""

    # Priority order (highest to lowest)
    DATE_PRIORITY_PATTERNS = [
        # Priority 1: Explicit revision/version dates
        (100, r'(?:revision|rev\.?|version|ver\.?)\s*[:=]?\s*(\d{4}[\s.\-/]\d{1,2}(?:[\s.\-/]\d{1,2})?)', 'revision'),
        (95, r'(?:revised|updated|modified)\s*[:=]?\s*(\d{4}[\s.\-/]\d{1,2})', 'revision'),
        (92, r'(?:revision|rev\.?)\s*date\s*[:=]?\s*(\d{4}[\s.\-/]\d{1,2})', 'revision_date'),

        # Priority 2: Document dates with context
        (90, r'(?:publication|published)\s*[:=]?\s*(\d{4}[\s.\-/]\d{1,2})', 'publication'),
        (85, r'(?:issue|issued)\s*[:=]?\s*(\d{4}[\s.\-/]\d{1,2})', 'issue'),
        (80, r'(?:release|released)\s*[:=]?\s*(\d{4}[\s.\-/]\d{1,2})', 'release'),
        (75, r'(?:approval|approved)\s*[:=]?\s*(\d{4}[\s.\-/]\d{1,2})', 'approval'),

        # Priority 3: Formatted dates with clear context
        (70, r'(?:date|dated)\s*[:=]?\s*(\d{4}[\s.\-/]\d{1,2})', 'explicit_date'),
        (65, r'(?:effective|validity)\s*[:=]?\s*(\d{4}[\s.\-/]\d{1,2})', 'effective'),

        # Priority 4: Month Year format
        (60, r'\b((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember))\s+\d{4})\b', 'month_year'),

        # Priority 5: Date formats without context
        (50, r'\b(\d{4}[\s.\-/]\d{2}[\s.\-/]\d{2})\b', 'iso_date'),  # YYYY-MM-DD
        (48, r'\b(\d{2}[\s.\-/]\d{2}[\s.\-/]\d{4})\b', 'us_eu_date'),  # MM/DD/YYYY or DD/MM/YYYY
        (45, r'\b(\d{4}[\s.\-/]\d{2})\b', 'year_month'),  # YYYY-MM

        # Priority 6: Copyright (only if nothing better found)
        (30, r'©\s*(\d{4})', 'copyright'),
        (28, r'[Cc]opyright\s+(\d{4})', 'copyright'),
        (25, r'©\s*(\d{4})\s*-\s*(\d{4})', 'copyright_range'),  # Use the later year

        # Priority 7: Standalone years (lowest priority)
        (10, r'\b(20[1-3]\d)\b', 'year_only'),
    ]

    def extract_best_date(self, text: str, pages_to_check: int = 5) -> Tuple[Optional[str], str, float]:
        """
        Extract the most likely publication date.
        Returns (date, source_type, confidence) tuple.
        """
        candidates = []

        # Only check first N pages worth of text (approximately)
        text_to_check = text[:pages_to_check * 3000] if pages_to_check else text

        for priority, pattern, source_type in self.DATE_PRIORITY_PATTERNS:
            matches = re.finditer(pattern, text_to_check, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                if source_type == 'copyright_range':
                    # For copyright ranges, use the later year
                    date_str = match.group(2) if len(match.groups()) > 1 else match.group(1)
                else:
                    date_str = match.group(1)

                normalized = self.normalize_date(date_str)
                if normalized:
                    # Calculate confidence based on priority and validation
                    confidence = self.calculate_confidence(priority, normalized, source_type)
                    candidates.append((priority, normalized, source_type, confidence))

        if not candidates:
            return None, "not_found", 0.0

        # Sort by priority (highest first), then by recency, then by confidence
        candidates.sort(key=lambda x: (x[0], x[1], x[3]), reverse=True)

        # Apply business rules
        best = self.select_best_candidate(candidates)

        return best[1], best[2], best[3]

    def select_best_candidate(self, candidates: List[Tuple]) -> Tuple:
        """Apply business rules to select the best date candidate."""
        if not candidates:
            return None, "not_found", 0.0

        best = candidates[0]

        # If best is copyright, check if there's a recent revision within 2 years
        if best[2] == 'copyright' and len(candidates) > 1:
            copyright_year = int(best[1][:4])
            for candidate in candidates[1:]:
                if candidate[2] in ('revision', 'publication', 'revision_date'):
                    candidate_year = int(candidate[1][:4])
                    # Use revision/publication if within 5 years of copyright
                    if abs(copyright_year - candidate_year) <= 5:
                        return candidate

        # If best is year_only, try to find something more specific
        if best[2] == 'year_only' and len(candidates) > 1:
            for candidate in candidates[1:]:
                if candidate[2] != 'year_only':
                    # Use more specific date if confidence is reasonable
                    if candidate[3] >= 0.5:
                        return candidate

        return best

    def normalize_date(self, date_str: str) -> Optional[str]:
        """Normalize various date formats to YYYY-MM-DD."""
        if not date_str:
            return None

        date_str = date_str.strip()

        # Already in YYYY-MM-DD format
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            return date_str

        # YYYY.MM.DD or YYYY/MM/DD
        match = re.match(r'^(\d{4})[.\-/](\d{2})[.\-/](\d{2})$', date_str)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

        # DD.MM.YYYY or DD/MM/YYYY (European format)
        match = re.match(r'^(\d{2})[.\-/](\d{2})[.\-/](\d{4})$', date_str)
        if match:
            day, month, year = match.groups()
            # Validate day/month ranges
            if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                return f"{year}-{month}-{day}"

        # MM/DD/YYYY (US format) - harder to distinguish from DD/MM/YYYY
        # Will need context to determine

        # YYYY-MM or YYYY.MM
        match = re.match(r'^(\d{4})[.\-/\s](\d{2})$', date_str)
        if match:
            return f"{match.group(1)}-{match.group(2)}-01"

        # Month Year format
        month_names = {
            'january': '01', 'jan': '01',
            'february': '02', 'feb': '02',
            'march': '03', 'mar': '03',
            'april': '04', 'apr': '04',
            'may': '05',
            'june': '06', 'jun': '06',
            'july': '07', 'jul': '07',
            'august': '08', 'aug': '08',
            'september': '09', 'sep': '09', 'sept': '09',
            'october': '10', 'oct': '10',
            'november': '11', 'nov': '11',
            'december': '12', 'dec': '12',
        }

        # Try to match "Month Year" or "Month, Year"
        match = re.match(r'^([A-Za-z]+),?\s+(\d{4})$', date_str)
        if match:
            month_str = match.group(1).lower()
            year = match.group(2)
            if month_str in month_names:
                return f"{year}-{month_names[month_str]}-01"

        # Just a year
        if re.match(r'^\d{4}$', date_str):
            return f"{date_str}-01-01"

        return None

    def calculate_confidence(self, priority: int, date: str, source_type: str) -> float:
        """Calculate confidence score for a date candidate."""
        confidence = priority / 100.0  # Base confidence from priority

        # Adjust based on date validity
        try:
            year = int(date[:4])
            current_year = datetime.now().year

            # Penalize future dates
            if year > current_year + 1:
                confidence *= 0.3

            # Penalize very old dates
            age = current_year - year
            if age > 20:
                confidence *= 0.5
            elif age > 10:
                confidence *= 0.8

            # Boost confidence for revision/publication dates
            if source_type in ('revision', 'publication', 'revision_date'):
                confidence *= 1.2

            # Penalize copyright and year_only
            if source_type == 'copyright':
                confidence *= 0.7
            elif source_type == 'year_only':
                confidence *= 0.5

        except (ValueError, IndexError):
            confidence *= 0.5

        return min(1.0, confidence)  # Cap at 1.0


class UniversalModelExtractor:
    """Extract model information with universal rules."""

    # Patterns that indicate invalid model values
    INVALID_MODELS = [
        'project', 'draft', 'template', 'document', 'example',
        'sample', 'test', 'demo', 'placeholder', 'tbd', 'n/a',
        'xxx', 'todo', 'pending', 'unknown'
    ]

    MODEL_PATTERNS = [
        # Explicit model patterns
        (100, r'\bModel\s*[:=#]?\s*([A-Z0-9][A-Z0-9\s\-_]{2,20}[A-Z0-9])\b', 'explicit'),
        (95, r'\bModel\s+(?:No|Number|#)\s*[:=]?\s*([A-Z0-9][A-Z0-9\s\-_]{2,20}[A-Z0-9])\b', 'model_number'),
        (90, r'\bCatalog\s*(?:No|Number|#)\s*[:=]?\s*([A-Z0-9][A-Z0-9\s\-_]{2,20}[A-Z0-9])\b', 'catalog'),

        # Product-specific patterns (requires both letters and numbers)
        (80, r'\b([A-Z]{2,4}[\s\-]?\d{3,5}[A-Z]?)\b', 'alphanumeric'),
        (75, r'\b([A-Z0-9]{2,3}[\s\-]\d{4,6})\b', 'product_code'),

        # System/device patterns
        (70, r'\b([A-Z][A-Za-z]+\s+(?:System|Device|Unit|Platform)\s+[A-Z0-9]+)\b', 'system_name'),
    ]

    def extract_model(self, text: str, manufacturer: Optional[str] = None) -> Tuple[Optional[str], float]:
        """
        Extract model information.
        Returns (model, confidence) tuple.
        """
        candidates = []

        # Only check first few pages
        text_to_check = text[:10000]

        for priority, pattern, source_type in self.MODEL_PATTERNS:
            matches = re.finditer(pattern, text_to_check, re.IGNORECASE)
            for match in matches:
                model = match.group(1).strip()
                if self.is_valid_model(model):
                    confidence = priority / 100.0
                    candidates.append((model, confidence, source_type))

        if not candidates:
            return None, 0.0

        # Sort by confidence
        candidates.sort(key=lambda x: x[1], reverse=True)

        # Apply manufacturer-specific rules if available
        if manufacturer:
            candidates = self.apply_manufacturer_rules(candidates, manufacturer)

        return candidates[0][0], candidates[0][1]

    def is_valid_model(self, model: str) -> bool:
        """Check if model string is valid."""
        if not model:
            return False

        model_lower = model.lower()

        # Check against invalid patterns
        for invalid in self.INVALID_MODELS:
            if invalid in model_lower:
                return False

        # Must have both letters and numbers (typical for medical devices)
        has_letter = any(c.isalpha() for c in model)
        has_number = any(c.isdigit() for c in model)

        if not (has_letter and has_number):
            # Some exceptions: pure alphabetic system names might be valid
            if len(model) >= 3 and model.isalpha() and model.isupper():
                return True
            return False

        # Length constraints
        if len(model) < 2 or len(model) > 30:
            return False

        return True

    def apply_manufacturer_rules(self, candidates: List[Tuple], manufacturer: str) -> List[Tuple]:
        """Apply manufacturer-specific model extraction rules."""
        # This would contain manufacturer-specific logic
        # For now, just return candidates as-is
        return candidates