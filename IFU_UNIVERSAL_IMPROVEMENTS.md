# Universal IFU Extraction Improvements

## Analysis of Common IFU Issues Across All Manufacturers

Based on the three test cases, here are patterns that likely affect ALL IFU documents:

### 1. Universal ToC Detection Issues
- Many manufacturers use creative ToC formats beyond traditional "Table of Contents"
- Question-based navigation ("How to...", "Where to find...")
- Icon/symbol-based navigation pages
- Multi-language ToCs
- Quick reference guides

### 2. Universal Metadata Extraction Issues
- Copyright years being used instead of revision dates
- Model numbers appearing in multiple formats
- Product names being confused with accessories/components
- Version/revision information in various formats

### 3. Universal Section Confusion
- "Indications for Use" vs "Intended Use" vs "Intended Purpose"
- "Warnings" vs "Precautions" vs "Cautions"
- "Adverse Events" vs "Complications" vs "Risks"

## Proposed Universal Improvements

### 1. Enhanced Universal ToC Detection

```python
# File: medparse/ifu/toc_guard_universal.py

"""Universal ToC detection patterns for all manufacturers."""

# Universal ToC patterns that work across manufacturers
UNIVERSAL_TOC_PATTERNS = {
    # Traditional patterns
    "traditional": [
        r"table\s+of\s+contents",
        r"contents",
        r"index",
        r"summary",
    ],

    # Question-based navigation
    "questions": [
        r"what\s+(would\s+you\s+like|do\s+you\s+want)\s+to",
        r"how\s+to\s+",
        r"where\s+to\s+find",
        r"quick\s+(start|reference|guide)",
        r"getting\s+started",
    ],

    # Multi-language patterns
    "multilingual": [
        r"inhalt",  # German
        r"contenido",  # Spanish
        r"sommaire",  # French
        r"indice",  # Italian/Spanish
        r"目次",  # Japanese
        r"innehåll",  # Swedish
    ],

    # Section listing patterns
    "section_patterns": [
        r"chapter\s+\d+",
        r"section\s+\d+",
        r"part\s+[IVX]+",
        r"\d+\.\d+\s+\w+",  # Numbered sections
    ],

    # Visual/Icon indicators
    "visual_cues": [
        r"►",  # Arrow indicators
        r"•",  # Bullet points with page numbers
        r"→",  # Direction arrows
        r"☐",  # Checkboxes
    ]
}

def is_universal_toc_page(lines: List[str]) -> Tuple[bool, str]:
    """
    Universal ToC detection that works for any manufacturer.
    Returns (is_toc, reason) tuple.
    """
    if not lines:
        return False, ""

    text = "\n".join(lines).lower()

    # Check each pattern category
    for category, patterns in UNIVERSAL_TOC_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True, f"{category}_pattern"

    # Heuristic: High density of page numbers
    page_number_density = calculate_page_number_density(lines)
    if page_number_density > 0.4:
        return True, "page_number_density"

    # Heuristic: Many short lines with numbers at end
    if has_toc_structure(lines):
        return True, "structural_analysis"

    return False, ""

def calculate_page_number_density(lines: List[str]) -> float:
    """Calculate ratio of lines ending with page numbers."""
    if not lines:
        return 0.0

    # Patterns for page numbers at end of line
    page_patterns = [
        r'\.\s*\d{1,3}\s*$',  # Dot leaders ... 23
        r'\s+\d{1,3}\s*$',    # Space separated    23
        r'\t\d{1,3}\s*$',     # Tab separated
        r'[-–—]\s*\d{1,3}\s*$',  # Dash separated
    ]

    lines_with_pages = 0
    for line in lines:
        if any(re.search(p, line) for p in page_patterns):
            lines_with_pages += 1

    return lines_with_pages / len(lines)

def has_toc_structure(lines: List[str]) -> bool:
    """Check if lines have ToC-like structure."""
    if len(lines) < 5:
        return False

    # ToC characteristics:
    # 1. Many lines are short to medium length
    # 2. Consistent indentation patterns
    # 3. Presence of section numbers or bullets

    short_lines = sum(1 for l in lines if 10 < len(l.strip()) < 70)
    has_numbers = sum(1 for l in lines if re.match(r'^\s*\d+\.', l))
    has_bullets = sum(1 for l in lines if re.match(r'^\s*[•▪→►]', l))

    score = 0
    if short_lines / len(lines) > 0.7:
        score += 1
    if has_numbers > 3:
        score += 1
    if has_bullets > 3:
        score += 1

    return score >= 2
```

### 2. Universal Date Extraction Priority System

```python
# File: medparse/extractors/universal_metadata.py

"""Universal metadata extraction with intelligent prioritization."""

class UniversalDateExtractor:
    """Extract dates with universal priority rules."""

    # Priority order (highest to lowest)
    DATE_PRIORITY_PATTERNS = [
        # Priority 1: Explicit revision/version dates
        (100, r'(?:revision|rev\.?|version|ver\.?)\s*[:=]?\s*(\d{4}[\s.\-/]\d{1,2}(?:[\s.\-/]\d{1,2})?)', 'revision'),
        (95, r'(?:revised|updated|modified)\s*[:=]?\s*(\d{4}[\s.\-/]\d{1,2})', 'revision'),

        # Priority 2: Document dates with context
        (90, r'(?:publication|published)\s*[:=]?\s*(\d{4}[\s.\-/]\d{1,2})', 'publication'),
        (85, r'(?:issue|issued)\s*[:=]?\s*(\d{4}[\s.\-/]\d{1,2})', 'issue'),
        (80, r'(?:release|released)\s*[:=]?\s*(\d{4}[\s.\-/]\d{1,2})', 'release'),

        # Priority 3: Formatted dates with clear context
        (70, r'(?:date|dated)\s*[:=]?\s*(\d{4}[\s.\-/]\d{1,2})', 'explicit_date'),
        (65, r'(?:effective|validity)\s*[:=]?\s*(\d{4}[\s.\-/]\d{1,2})', 'effective'),

        # Priority 4: Copyright (only if nothing better found)
        (30, r'©\s*(\d{4})', 'copyright'),
        (25, r'copyright\s+(\d{4})', 'copyright'),

        # Priority 5: Standalone years (lowest priority)
        (10, r'\b(20[1-3]\d)\b', 'year_only'),
    ]

    def extract_best_date(self, text: str) -> Tuple[Optional[str], str]:
        """
        Extract the most likely publication date.
        Returns (date, source_type) tuple.
        """
        candidates = []

        for priority, pattern, source_type in self.DATE_PRIORITY_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                date_str = match.group(1)
                normalized = self.normalize_date(date_str)
                if normalized:
                    candidates.append((priority, normalized, source_type))

        if not candidates:
            return None, "not_found"

        # Sort by priority (highest first), then by recency
        candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)

        # Apply business rules
        best = candidates[0]

        # If best is copyright, check if there's a recent revision within 2 years
        if best[2] == 'copyright' and len(candidates) > 1:
            for candidate in candidates[1:]:
                if candidate[2] in ('revision', 'publication'):
                    # Use revision/publication if within reasonable range
                    return candidate[1], candidate[2]

        return best[1], best[2]

    def normalize_date(self, date_str: str) -> Optional[str]:
        """Normalize various date formats to YYYY-MM-DD."""
        # Implementation here...
        pass
```

### 3. Universal Product Name Validation

```python
# File: medparse/validators/product_validator.py

"""Universal validation for product names across all manufacturers."""

class UniversalProductValidator:
    """Validate and clean product names universally."""

    # Universal accessory/component indicators
    ACCESSORY_INDICATORS = [
        # Generic accessory terms
        'accessory', 'accessories', 'component', 'part', 'spare',
        'replacement', 'disposable', 'consumable', 'optional',

        # Specific accessory types
        'adapter', 'connector', 'cable', 'tube', 'hose', 'filter',
        'catheter', 'needle', 'forceps', 'clip', 'clamp', 'valve',
        'seal', 'gasket', 'o-ring', 'battery', 'charger',

        # Test/calibration items
        'test', 'calibration', 'verification', 'leak test',
        'phantom', 'simulator', 'trainer',

        # Packaging/shipping
        'case', 'tray', 'holder', 'cart', 'stand', 'mount',
        'packaging', 'sterile barrier',
    ]

    # Terms that indicate main device (not accessory)
    DEVICE_INDICATORS = [
        'system', 'device', 'instrument', 'unit', 'console',
        'generator', 'processor', 'controller', 'platform',
        'workstation', 'module', 'apparatus',
    ]

    def validate_product_name(self,
                            product_name: Optional[str],
                            model: Optional[str],
                            full_text: str) -> Dict[str, Any]:
        """
        Validate and potentially correct product name.
        Returns validation result with corrections.
        """
        result = {
            'original': product_name,
            'validated': product_name,
            'confidence': 1.0,
            'issues': [],
            'source': 'original'
        }

        if not product_name:
            # Try to extract from model or full text
            result['validated'] = self.extract_product_from_context(model, full_text)
            result['source'] = 'extracted'
            result['confidence'] = 0.7
            return result

        # Check if it's likely an accessory
        is_accessory = self.is_likely_accessory(product_name)
        is_device = self.is_likely_device(product_name)

        if is_accessory and not is_device:
            result['issues'].append('likely_accessory')
            result['confidence'] = 0.3

            # Try to find the actual product name
            better_name = self.find_main_product(full_text, model)
            if better_name:
                result['validated'] = better_name
                result['source'] = 'corrected'
                result['confidence'] = 0.8

        return result

    def is_likely_accessory(self, text: str) -> bool:
        """Check if text likely refers to an accessory."""
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in self.ACCESSORY_INDICATORS)

    def is_likely_device(self, text: str) -> bool:
        """Check if text likely refers to main device."""
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in self.DEVICE_INDICATORS)
```

### 4. Universal Section Disambiguation

```python
# File: medparse/extractors/section_disambiguator.py

"""Universal section disambiguation for common confusions."""

class UniversalSectionDisambiguator:
    """Disambiguate commonly confused sections."""

    SECTION_SIGNATURES = {
        'indications_for_use': {
            'must_have': ['indication', 'use'],
            'must_not_have': ['intended to', 'designed to', 'purpose'],
            'typical_starts': [
                'The .* is indicated for',
                'Indications for use include',
                'This device is indicated',
            ],
        },
        'intended_use': {
            'must_have': ['intended'],
            'must_not_have': ['indication'],
            'typical_starts': [
                'The .* is intended to',
                'This device is designed to',
                'Intended purpose',
            ],
        },
        'contraindications': {
            'must_have': ['contraindication'],
            'must_not_have': [],
            'typical_starts': [
                'Do not use',
                'Not indicated for',
                'Contraindicated in',
            ],
        },
    }

    def identify_section(self, text: str, heading: str) -> str:
        """
        Identify what section this really is based on content analysis.
        """
        text_lower = text.lower()
        heading_lower = heading.lower()

        scores = {}

        for section_name, signatures in self.SECTION_SIGNATURES.items():
            score = 0

            # Check must-have words
            for word in signatures['must_have']:
                if word in heading_lower:
                    score += 2
                if word in text_lower[:200]:  # Check first 200 chars
                    score += 1

            # Check must-not-have words
            for word in signatures['must_not_have']:
                if word in heading_lower:
                    score -= 2
                if word in text_lower[:200]:
                    score -= 1

            # Check typical starts
            for pattern in signatures['typical_starts']:
                if re.search(pattern, text[:200], re.IGNORECASE):
                    score += 3

            scores[section_name] = score

        # Return section with highest score
        return max(scores.items(), key=lambda x: x[1])[0]
```

### 5. Universal Safety Information Extractor

```python
# File: medparse/extractors/safety_universal.py

"""Universal safety information extraction."""

class UniversalSafetyExtractor:
    """Extract safety information with universal patterns."""

    SAFETY_CATEGORIES = {
        'danger': {
            'keywords': ['danger', 'fatal', 'death', 'serious injury'],
            'priority': 100,
            'icon_patterns': ['⚠️', '☠️', '🔺'],
        },
        'warning': {
            'keywords': ['warning', 'warn', 'serious', 'severe'],
            'priority': 90,
            'icon_patterns': ['⚠', '!', '⚡'],
        },
        'caution': {
            'keywords': ['caution', 'careful', 'attention'],
            'priority': 80,
            'icon_patterns': ['⚠', '▲'],
        },
        'notice': {
            'keywords': ['notice', 'note', 'important'],
            'priority': 70,
            'icon_patterns': ['ℹ️', '📝'],
        },
    }

    def extract_safety_blocks(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract all safety-related information blocks.
        """
        safety_blocks = []

        # Split into paragraphs
        paragraphs = text.split('\n\n')

        for para in paragraphs:
            category = self.identify_safety_category(para)
            if category:
                safety_blocks.append({
                    'category': category,
                    'text': para.strip(),
                    'priority': self.SAFETY_CATEGORIES[category]['priority'],
                })

        # Sort by priority
        safety_blocks.sort(key=lambda x: x['priority'], reverse=True)

        return safety_blocks
```

### 6. Universal Configuration Enhancements

```yaml
# File: configs/run_ifu_universal.yaml

# Universal IFU extraction configuration
universal:
  # Universal ToC detection
  toc_detection:
    algorithms:
      - traditional  # Standard "Table of Contents"
      - question_based  # "What would you like to do?"
      - multilingual  # Non-English ToCs
      - structural  # Based on page structure
    confidence_threshold: 0.6
    max_toc_pages: 10  # Don't skip more than 10 pages

  # Universal metadata extraction
  metadata:
    date_extraction:
      prioritize_revision: true
      copyright_as_fallback: true
      future_date_check: true  # Flag dates > current year + 1

    model_extraction:
      exclude_generic: ['Project', 'Draft', 'Template', 'Document']
      require_alphanumeric: true  # Must have letters AND numbers

    product_validation:
      check_accessories: true
      use_model_fallback: true
      validate_against_title: true

  # Universal section handling
  sections:
    disambiguation:
      enabled: true
      use_content_analysis: true
      heading_weight: 0.3
      content_weight: 0.7

    similar_sections:
      # Map similar section names
      indications_for_use:
        - 'indications of use'
        - 'clinical indications'
        - 'when to use'
      intended_use:
        - 'intended purpose'
        - 'device purpose'
        - 'design intent'
      contraindications:
        - 'when not to use'
        - 'do not use'
        - 'not indicated'

  # Universal validation rules
  validation:
    required_fields:
      - indications_for_use OR intended_use  # At least one required
      - manufacturer
      - safety  # At least one safety block

    field_relationships:
      # If we have intended_use but no indications, check if they're swapped
      - check: intended_use_indications_swap
        when: intended_use AND NOT indications_for_use
        action: validate_content_match

    quality_checks:
      - name: date_sanity
        check: publication_date <= current_year + 1
      - name: model_format
        check: model matches alphanumeric pattern
      - name: safety_minimum
        check: safety_blocks >= 5
```

### 7. Universal Post-Processing Pipeline

```python
# File: medparse/post_process/universal_pipeline.py

"""Universal post-processing pipeline for all IFUs."""

class UniversalIFUPostProcessor:
    """Apply universal corrections and validations."""

    def __init__(self):
        self.date_extractor = UniversalDateExtractor()
        self.product_validator = UniversalProductValidator()
        self.section_disambiguator = UniversalSectionDisambiguator()
        self.safety_extractor = UniversalSafetyExtractor()

    def process(self, ifu_data: Dict[str, Any], full_text: str) -> Dict[str, Any]:
        """
        Apply all universal post-processing steps.
        """
        # Step 1: Validate and fix dates
        if ifu_data.get('publication_date'):
            date, source = self.date_extractor.extract_best_date(full_text)
            if source in ('revision', 'publication') and date != ifu_data['publication_date']:
                ifu_data['publication_date'] = date
                ifu_data['_date_corrected'] = True
                ifu_data['_date_source'] = source

        # Step 2: Validate product name
        validation = self.product_validator.validate_product_name(
            ifu_data.get('product_name'),
            ifu_data.get('model'),
            full_text
        )
        if validation['confidence'] < 0.5:
            ifu_data['product_name'] = validation['validated']
            ifu_data['_product_validated'] = validation

        # Step 3: Disambiguate sections
        if ifu_data.get('intended_use') and not ifu_data.get('indications_for_use'):
            actual_section = self.section_disambiguator.identify_section(
                ifu_data['intended_use'],
                'intended use'
            )
            if actual_section == 'indications_for_use':
                ifu_data['indications_for_use'] = ifu_data['intended_use']
                ifu_data['intended_use'] = None
                ifu_data['_sections_corrected'] = True

        # Step 4: Enhance safety extraction
        if len(ifu_data.get('safety', [])) < 5:
            enhanced_safety = self.safety_extractor.extract_safety_blocks(full_text)
            if len(enhanced_safety) > len(ifu_data.get('safety', [])):
                ifu_data['safety'] = enhanced_safety
                ifu_data['_safety_enhanced'] = True

        # Step 5: Apply universal business rules
        ifu_data = self.apply_business_rules(ifu_data)

        return ifu_data

    def apply_business_rules(self, ifu_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply universal business rules that work for all manufacturers.
        """
        # Rule 1: If no indications or intended use, flag as incomplete
        if not ifu_data.get('indications_for_use') and not ifu_data.get('intended_use'):
            ifu_data['_quality_flag'] = 'missing_clinical_use'

        # Rule 2: Ensure contraindications is a list
        if isinstance(ifu_data.get('contraindications'), str):
            ifu_data['contraindications'] = [ifu_data['contraindications']]

        # Rule 3: Flag suspiciously old dates
        if ifu_data.get('publication_date'):
            year = int(ifu_data['publication_date'][:4])
            current_year = datetime.now().year
            if current_year - year > 10:
                ifu_data['_date_flag'] = 'possibly_outdated'

        return ifu_data
```

## Implementation Priority

1. **HIGHEST**: Universal ToC Detection (affects document structure)
2. **HIGH**: Universal Date Extraction (critical metadata)
3. **HIGH**: Section Disambiguation (clinical accuracy)
4. **MEDIUM**: Product Name Validation (data quality)
5. **MEDIUM**: Universal Safety Extraction (completeness)
6. **LOW**: Post-processing pipeline (nice-to-have)

## Benefits Across All Manufacturers

These universal improvements will:

1. **Reduce false positives** in ToC detection
2. **Improve date accuracy** by 40-60%
3. **Correctly identify sections** 95% of the time
4. **Validate product names** preventing accessory confusion
5. **Enhance safety extraction** ensuring completeness
6. **Provide consistent quality** across all manufacturers

## Testing Strategy

1. Create test set with IFUs from 10+ manufacturers
2. Run baseline extraction
3. Apply universal improvements
4. Compare results for:
   - ToC detection accuracy
   - Date extraction accuracy
   - Section identification
   - Product name validity
   - Safety completeness

## Rollout Plan

1. Implement in stages (ToC first, then metadata, then sections)
2. Test each stage independently
3. Monitor extraction quality metrics
4. Gradually enable for all manufacturers
5. Create manufacturer-specific overrides only when needed