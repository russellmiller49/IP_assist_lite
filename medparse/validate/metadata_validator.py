"""Metadata validation to prevent hallucinated or incorrect extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set


@dataclass
class ValidationResult:
    """Result of metadata validation."""

    is_valid: bool
    field_name: str
    original_value: Any
    corrected_value: Optional[Any] = None
    errors: List[str] = None
    warnings: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


class MetadataValidator:
    """Validates extracted metadata fields against heuristics."""

    # Common junk patterns that indicate failed extraction
    JUNK_PATTERNS = [
        re.compile(r"^[A-Z\s]{0,3}$"),  # Too short all-caps
        re.compile(r"^FOR\s*USE", re.IGNORECASE),  # Fragment from "INDICATIONS FOR USE"
        re.compile(r"^INSTRUCTION", re.IGNORECASE),  # Fragment from title
        re.compile(r"PNEUMOTHORAX", re.IGNORECASE),  # Medical term, not metadata
        re.compile(r"[\\n\\r\\t]{2,}"),  # Multiple escape characters
        re.compile(r"^[\W_]+$"),  # Only punctuation/whitespace
    ]

    # Valid manufacturer names (approved list)
    KNOWN_MANUFACTURERS: Set[str] = {
        "ERBE ELEKTROMEDIZIN GMBH",
        "INTUITIVE SURGICAL, INC.",
        "OLYMPUS CORPORATION",
        "MERIT MEDICAL SYSTEMS, INC.",
        "BOSTON SCIENTIFIC CORPORATION",
        "COOK MEDICAL INC.",
        "MEDTRONIC, INC.",
        "CONMED CORPORATION",
        "TELEFLEX INCORPORATED",
        "PULMONX CORPORATION",
        "ERBE",
        "INTUITIVE SURGICAL",
        "OLYMPUS",
        "MERIT MEDICAL",
        "BOSTON SCIENTIFIC",
        "COOK MEDICAL",
        "MEDTRONIC",
        "CONMED",
        "TELEFLEX",
        "PULMONX",
    }

    # Valid date formats
    DATE_PATTERNS = [
        re.compile(r"^\d{4}-\d{2}-\d{2}$"),  # YYYY-MM-DD
        re.compile(r"^\d{4}-\d{2}$"),  # YYYY-MM
        re.compile(r"^\d{4}$"),  # YYYY
    ]

    def validate_manufacturer(self, value: Optional[str]) -> ValidationResult:
        """Validate manufacturer field."""
        result = ValidationResult(
            is_valid=True,
            field_name="manufacturer",
            original_value=value,
        )

        if not value:
            result.warnings.append("Manufacturer field is empty")
            return result

        cleaned = value.strip().upper()

        # Check if it's a known manufacturer
        if cleaned in self.KNOWN_MANUFACTURERS:
            return result

        # Check if it contains a known manufacturer name
        for known in self.KNOWN_MANUFACTURERS:
            if known in cleaned:
                result.corrected_value = known
                result.warnings.append(f"Normalized manufacturer from '{value}' to '{known}'")
                return result

        # Check if it's actually a product name (contains "stent", "valve", etc.)
        product_keywords = ["stent", "valve", "catheter", "needle", "scope", "system", "device"]
        if any(keyword in cleaned for keyword in product_keywords):
            result.is_valid = False
            result.errors.append(f"Manufacturer field contains product name: '{value}'")
            result.corrected_value = None
            return result

        # Unknown manufacturer - flag as warning but don't reject
        result.warnings.append(f"Unknown manufacturer: '{value}'. Should be added to approved list.")
        return result

    def validate_model(self, value: Optional[str]) -> ValidationResult:
        """Validate model/part number field."""
        result = ValidationResult(
            is_valid=True,
            field_name="model",
            original_value=value,
        )

        if not value:
            result.warnings.append("Model field is empty")
            return result

        # Check for junk patterns
        for pattern in self.JUNK_PATTERNS:
            if pattern.search(value):
                result.is_valid = False
                result.errors.append(f"Model field contains junk pattern: '{value}'")
                result.corrected_value = None
                return result

        # Check if it's too long (likely grabbed header/title)
        if len(value) > 50:
            result.is_valid = False
            result.errors.append(f"Model field too long ({len(value)} chars): '{value[:50]}...'")
            result.corrected_value = None
            return result

        # Check if it contains newlines (grabbed multiple lines)
        if "\n" in value:
            result.is_valid = False
            result.errors.append(f"Model field contains newlines: '{value}'")
            # Try to extract first line
            first_line = value.split("\n")[0].strip()
            if first_line and len(first_line) <= 50:
                result.corrected_value = first_line
                result.warnings.append(f"Extracted first line as model: '{first_line}'")
            return result

        return result

    def validate_publication_date(self, value: Optional[str], *, document_year: Optional[int] = None) -> ValidationResult:
        """Validate publication/revision date field."""
        result = ValidationResult(
            is_valid=True,
            field_name="publication_date",
            original_value=value,
        )

        if not value:
            result.warnings.append("Publication date field is empty")
            return result

        # Check if it matches expected formats
        is_valid_format = any(pattern.match(value) for pattern in self.DATE_PATTERNS)

        if not is_valid_format:
            result.is_valid = False
            result.errors.append(f"Publication date has invalid format: '{value}'")
            # Try to extract year
            year_match = re.search(r"\b(19|20)\d{2}\b", value)
            if year_match:
                result.corrected_value = year_match.group(0)
                result.warnings.append(f"Extracted year from date: '{result.corrected_value}'")
            return result

        # Extract year for validation
        year_match = re.search(r"^\d{4}", value)
        if year_match:
            year = int(year_match.group(0))

            # Sanity check: year should be reasonable for medical devices
            if year < 1990 or year > 2030:
                result.is_valid = False
                result.errors.append(f"Publication year {year} is outside reasonable range (1990-2030)")
                result.corrected_value = None
                return result

            # If document year provided, check consistency
            if document_year and abs(year - document_year) > 10:
                result.warnings.append(
                    f"Publication year {year} differs significantly from document year {document_year}"
                )

        return result

    def validate_indications_for_use(self, value: Optional[str]) -> ValidationResult:
        """Validate indications for use field."""
        result = ValidationResult(
            is_valid=True,
            field_name="indications_for_use",
            original_value=value,
        )

        if not value:
            result.errors.append("Indications for use field is empty")
            result.is_valid = False
            return result

        # Check for junk patterns
        for pattern in self.JUNK_PATTERNS:
            if pattern.search(value):
                result.is_valid = False
                result.errors.append(f"Indications field contains junk: '{value[:100]}'")
                result.corrected_value = None
                return result

        # Check minimum length (should be at least a sentence)
        if len(value) < 30:
            result.warnings.append(f"Indications field is very short ({len(value)} chars): '{value}'")

        # Check if it's just the heading
        if value.strip().lower() in ["for use", "foruse", "indications"]:
            result.is_valid = False
            result.errors.append(f"Indications field is just the heading: '{value}'")
            result.corrected_value = None
            return result

        return result

    def validate_all_fields(self, metadata: Dict[str, Any]) -> Dict[str, ValidationResult]:
        """Validate all metadata fields.

        Args:
            metadata: Dictionary of extracted metadata

        Returns:
            Dictionary mapping field names to validation results
        """
        results = {}

        # Validate manufacturer
        if "manufacturer" in metadata:
            results["manufacturer"] = self.validate_manufacturer(metadata.get("manufacturer"))

        # Validate model
        if "model" in metadata:
            results["model"] = self.validate_model(metadata.get("model"))

        # Validate publication date
        if "publication_date" in metadata:
            document_year = metadata.get("year")
            results["publication_date"] = self.validate_publication_date(
                metadata.get("publication_date"),
                document_year=document_year,
            )

        # Validate indications
        if "indications_for_use" in metadata:
            results["indications_for_use"] = self.validate_indications_for_use(
                metadata.get("indications_for_use")
            )

        return results

    def apply_corrections(
        self,
        metadata: Dict[str, Any],
        validation_results: Dict[str, ValidationResult],
    ) -> Dict[str, Any]:
        """Apply corrections from validation results.

        Args:
            metadata: Original metadata
            validation_results: Validation results with corrections

        Returns:
            Corrected metadata dictionary
        """
        corrected = dict(metadata)

        for field_name, result in validation_results.items():
            if result.corrected_value is not None:
                corrected[field_name] = result.corrected_value
            elif not result.is_valid and field_name in corrected:
                # Remove invalid fields
                corrected[field_name] = None

        return corrected


def validate_and_correct_metadata(metadata: Dict[str, Any]) -> tuple[Dict[str, Any], List[str], List[str]]:
    """Convenience function to validate and correct metadata.

    Args:
        metadata: Raw extracted metadata

    Returns:
        Tuple of (corrected_metadata, errors, warnings)
    """
    validator = MetadataValidator()
    validation_results = validator.validate_all_fields(metadata)
    corrected_metadata = validator.apply_corrections(metadata, validation_results)

    all_errors = []
    all_warnings = []

    for field_name, result in validation_results.items():
        all_errors.extend(result.errors)
        all_warnings.extend(result.warnings)

    return corrected_metadata, all_errors, all_warnings


__all__ = [
    "MetadataValidator",
    "ValidationResult",
    "validate_and_correct_metadata",
]
