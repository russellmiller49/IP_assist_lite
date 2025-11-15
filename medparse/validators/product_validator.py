"""Universal validation for product names across all manufacturers."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


class UniversalProductValidator:
    """Validate and clean product names universally."""

    # Universal accessory/component indicators
    ACCESSORY_INDICATORS = [
        # Generic accessory terms
        'accessory', 'accessories', 'component', 'part', 'spare',
        'replacement', 'disposable', 'consumable', 'optional',
        'supplemental', 'auxiliary', 'add-on', 'attachment',

        # Specific accessory types - Medical
        'adapter', 'connector', 'cable', 'tube', 'hose', 'filter',
        'catheter', 'needle', 'forceps', 'clip', 'clamp', 'valve',
        'seal', 'gasket', 'o-ring', 'battery', 'charger', 'electrode',
        'trocar', 'cannula', 'sheath', 'guidewire', 'stent',
        'balloon', 'brush', 'snare', 'basket', 'dilator',

        # Test/calibration items
        'test', 'calibration', 'verification', 'leak test',
        'phantom', 'simulator', 'trainer', 'practice', 'demo',

        # Packaging/support items
        'case', 'tray', 'holder', 'cart', 'stand', 'mount',
        'packaging', 'sterile barrier', 'cover', 'drape',
        'bracket', 'clamp', 'fixture', 'jig',

        # Cleaning/maintenance
        'cleaning', 'disinfectant', 'lubricant', 'maintenance',
        'service', 'repair', 'tool', 'kit',
    ]

    # Terms that indicate main device (not accessory)
    DEVICE_INDICATORS = [
        'system', 'device', 'instrument', 'unit', 'console',
        'generator', 'processor', 'controller', 'platform',
        'workstation', 'module', 'apparatus', 'machine',
        'station', 'tower', 'base unit', 'main unit',
        'equipment', 'analyzer', 'monitor', 'recorder',
    ]

    # Manufacturer-specific accessory prefixes
    ACCESSORY_PREFIXES = [
        'MAJ-',  # Olympus accessories
        'REF-',  # Reference/accessory prefix
        'CAT-',  # Catalog items (often accessories)
        'PN-',   # Part numbers (could be accessories)
        'SN-',   # Serial numbers
        'ACC-',  # Accessory prefix
        'OPT-',  # Optional items
    ]

    def validate_product_name(self,
                             product_name: Optional[str],
                             model: Optional[str],
                             manufacturer: Optional[str] = None,
                             full_text: str = "") -> Dict[str, Any]:
        """
        Validate and potentially correct product name.
        Returns validation result with corrections.
        """
        result = {
            'original': product_name,
            'validated': product_name,
            'confidence': 1.0,
            'issues': [],
            'source': 'original',
            'corrections_applied': []
        }

        if not product_name:
            # Try to extract from model or full text
            extracted = self.extract_product_from_context(model, manufacturer, full_text)
            if extracted:
                result['validated'] = extracted
                result['source'] = 'extracted'
                result['confidence'] = 0.7
                result['corrections_applied'].append('extracted_from_context')
            return result

        # Check if it's likely an accessory
        is_accessory, accessory_reasons = self.is_likely_accessory(product_name)
        is_device, device_reasons = self.is_likely_device(product_name)

        if is_accessory and not is_device:
            result['issues'].append('likely_accessory')
            result['confidence'] = 0.3

            # Log why we think it's an accessory
            for reason in accessory_reasons:
                result['issues'].append(f'accessory_indicator: {reason}')

            # Try to find the actual product name
            better_name = self.find_main_product(full_text, model, manufacturer)
            if better_name and better_name != product_name:
                result['validated'] = better_name
                result['source'] = 'corrected'
                result['confidence'] = 0.8
                result['corrections_applied'].append('replaced_accessory_name')

        # Clean up the product name
        cleaned = self.clean_product_name(result['validated'], manufacturer)
        if cleaned != result['validated']:
            result['validated'] = cleaned
            result['corrections_applied'].append('cleaned_formatting')

        # Validate against known patterns
        if not self.is_valid_product_name_format(result['validated']):
            result['issues'].append('unusual_format')
            result['confidence'] *= 0.8

        return result

    def is_likely_accessory(self, text: str) -> tuple[bool, List[str]]:
        """Check if text likely refers to an accessory."""
        if not text:
            return False, []

        text_lower = text.lower()
        reasons = []

        # Check for accessory keywords
        for indicator in self.ACCESSORY_INDICATORS:
            if indicator in text_lower:
                reasons.append(indicator)

        # Check for accessory prefixes
        for prefix in self.ACCESSORY_PREFIXES:
            if text.upper().startswith(prefix):
                reasons.append(f'prefix_{prefix}')

        # Check for part number patterns (e.g., "123-456-789")
        if re.match(r'^\d{3,}-\d{3,}(?:-\d{3,})?$', text):
            reasons.append('part_number_pattern')

        return len(reasons) > 0, reasons

    def is_likely_device(self, text: str) -> tuple[bool, List[str]]:
        """Check if text likely refers to main device."""
        if not text:
            return False, []

        text_lower = text.lower()
        reasons = []

        for indicator in self.DEVICE_INDICATORS:
            if indicator in text_lower:
                reasons.append(indicator)

        # Check for typical device name patterns
        if re.search(r'\b(?:series|model|version|gen(?:eration)?)\s+[A-Z0-9]+', text, re.IGNORECASE):
            reasons.append('device_version_pattern')

        return len(reasons) > 0, reasons

    def extract_product_from_context(self,
                                    model: Optional[str],
                                    manufacturer: Optional[str],
                                    full_text: str) -> Optional[str]:
        """Extract product name from available context."""
        # First, try using the model if available
        if model and not self.is_likely_accessory(model)[0]:
            # Add manufacturer prefix if not present
            if manufacturer and manufacturer.lower() not in model.lower():
                return f"{manufacturer} {model}"
            return model

        # Try to extract from title or first page
        if full_text:
            # Look for patterns like "XYZ System Instructions for Use"
            title_match = re.search(
                r'^([A-Z][A-Za-z0-9\s\-]+(?:System|Device|Platform|Unit))\s*\n',
                full_text[:1000],
                re.MULTILINE
            )
            if title_match:
                candidate = title_match.group(1).strip()
                if not self.is_likely_accessory(candidate)[0]:
                    return candidate

        return None

    def find_main_product(self,
                         full_text: str,
                         model: Optional[str],
                         manufacturer: Optional[str]) -> Optional[str]:
        """Find the main product name in the document."""
        candidates = []

        # Search for device indicators in the first part of the document
        search_text = full_text[:5000] if full_text else ""

        # Pattern 1: "The [Product Name] is..."
        matches = re.finditer(
            r'\bThe\s+([A-Z][A-Za-z0-9\s\-]+(?:System|Device|Platform|Unit|Console|Generator))\s+is\b',
            search_text
        )
        for match in matches:
            candidate = match.group(1).strip()
            if not self.is_likely_accessory(candidate)[0]:
                candidates.append((candidate, 0.9))

        # Pattern 2: Product name in title/header
        matches = re.finditer(
            r'^#+\s*([A-Z][A-Za-z0-9\s\-]+(?:System|Device|Platform))',
            search_text,
            re.MULTILINE
        )
        for match in matches:
            candidate = match.group(1).strip()
            if not self.is_likely_accessory(candidate)[0]:
                candidates.append((candidate, 0.8))

        # Use model as fallback
        if model and not self.is_likely_accessory(model)[0]:
            candidates.append((model, 0.7))

        # Sort by confidence and return best
        if candidates:
            candidates.sort(key=lambda x: x[1], reverse=True)
            best = candidates[0][0]

            # Add manufacturer prefix if appropriate
            if manufacturer and manufacturer.lower() not in best.lower():
                return f"{manufacturer} {best}"
            return best

        return None

    def clean_product_name(self, name: Optional[str], manufacturer: Optional[str]) -> Optional[str]:
        """Clean and normalize product name."""
        if not name:
            return name

        # Remove extra whitespace
        cleaned = ' '.join(name.split())

        # Remove trailing punctuation
        cleaned = cleaned.rstrip('.,;:')

        # Remove quotes
        cleaned = cleaned.strip('"\'')

        # Remove "Instructions for Use" or similar suffixes
        suffixes_to_remove = [
            'instructions for use',
            'instruction manual',
            'user manual',
            'operator manual',
            'service manual',
            'ifu',
        ]
        cleaned_lower = cleaned.lower()
        for suffix in suffixes_to_remove:
            if cleaned_lower.endswith(suffix):
                cleaned = cleaned[:-len(suffix)].strip()

        # Ensure manufacturer prefix if specified
        if manufacturer and manufacturer.lower() not in cleaned.lower():
            # Only add if it makes sense
            if not cleaned.lower().startswith('the '):
                cleaned = f"{manufacturer} {cleaned}"

        return cleaned

    def is_valid_product_name_format(self, name: Optional[str]) -> bool:
        """Check if product name has a valid format."""
        if not name:
            return False

        # Too short or too long
        if len(name) < 3 or len(name) > 100:
            return False

        # Should have at least one letter
        if not any(c.isalpha() for c in name):
            return False

        # Shouldn't be all numbers
        if name.replace('-', '').replace(' ', '').isdigit():
            return False

        # Shouldn't be a file path or URL
        if any(char in name for char in ['/', '\\', 'http:', 'https:', 'www.']):
            return False

        return True