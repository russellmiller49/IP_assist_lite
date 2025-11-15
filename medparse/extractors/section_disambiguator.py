"""Universal section disambiguation for commonly confused sections."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple


class UniversalSectionDisambiguator:
    """Disambiguate commonly confused sections in IFU documents."""

    # Section signatures with patterns and keywords
    SECTION_SIGNATURES = {
        'indications_for_use': {
            'must_have': ['indication'],
            'should_have': ['use', 'indicated', 'treatment', 'diagnostic', 'therapeutic'],
            'must_not_have': ['intended to', 'designed to', 'purpose of this'],
            'typical_starts': [
                r'The .* is indicated for',
                r'Indications for use include',
                r'This (?:device|system) is indicated',
                r'Use .* for the following indications',
                r'Clinical indications',
                r'The .* should be used for',
            ],
            'content_keywords': [
                'diagnosis', 'treatment', 'therapy', 'procedure',
                'patient', 'clinical', 'medical condition', 'disease'
            ]
        },
        'intended_use': {
            'must_have': ['intended'],
            'should_have': ['purpose', 'designed', 'meant'],
            'must_not_have': ['indication', 'clinical indication', 'medical condition'],
            'typical_starts': [
                r'The .* is intended to',
                r'This (?:device|system) is designed to',
                r'Intended purpose',
                r'The purpose of .* is to',
                r'This .* is meant to',
                r'General purpose',
            ],
            'content_keywords': [
                'function', 'operation', 'capability', 'feature',
                'designed', 'engineered', 'purpose', 'goal'
            ]
        },
        'contraindications': {
            'must_have': ['contraindication'],
            'should_have': ['not', 'do not use', 'must not', 'should not'],
            'must_not_have': [],
            'typical_starts': [
                r'Do not use',
                r'Not indicated for',
                r'Contraindicated in',
                r'The .* is contraindicated',
                r'Absolute contraindications',
                r'Relative contraindications',
                r'Must not be used',
            ],
            'content_keywords': [
                'contraindicated', 'prohibited', 'not suitable',
                'incompatible', 'dangerous', 'risk', 'avoid'
            ]
        },
        'warnings': {
            'must_have': ['warning'],
            'should_have': ['danger', 'serious', 'death', 'injury'],
            'must_not_have': ['caution', 'notice'],
            'typical_starts': [
                r'Warning[:\s]',
                r'⚠\s*WARNING',
                r'DANGER',
                r'Serious injury',
                r'Death or serious',
            ],
            'content_keywords': [
                'fatal', 'death', 'serious injury', 'permanent damage',
                'life-threatening', 'severe', 'critical'
            ]
        },
        'precautions': {
            'must_have': ['precaution', 'caution'],
            'should_have': ['careful', 'attention', 'avoid'],
            'must_not_have': ['warning', 'danger'],
            'typical_starts': [
                r'Precaution[:\s]',
                r'Caution[:\s]',
                r'Take care',
                r'Be careful',
                r'Exercise caution',
            ],
            'content_keywords': [
                'careful', 'attention', 'prevent', 'avoid',
                'minimize', 'reduce risk', 'safety measure'
            ]
        },
        'adverse_events': {
            'must_have': ['adverse', 'complication'],
            'should_have': ['event', 'reaction', 'effect', 'risk'],
            'must_not_have': [],
            'typical_starts': [
                r'Adverse events',
                r'Complications',
                r'Potential risks',
                r'Side effects',
                r'Undesired effects',
            ],
            'content_keywords': [
                'complication', 'adverse reaction', 'side effect',
                'unintended', 'negative outcome', 'risk of'
            ]
        }
    }

    # Common section name variations
    SECTION_ALIASES = {
        'indications_for_use': [
            'indications of use',
            'clinical indications',
            'when to use',
            'indicated uses',
            'therapeutic indications',
        ],
        'intended_use': [
            'intended purpose',
            'device purpose',
            'design intent',
            'purpose of device',
            'general use',
        ],
        'contraindications': [
            'when not to use',
            'do not use',
            'not indicated',
            'restrictions',
            'prohibited uses',
        ],
        'warnings': [
            'danger',
            'safety warnings',
            'critical safety',
            'important warnings',
        ],
        'precautions': [
            'cautions',
            'safety precautions',
            'important precautions',
            'safety measures',
        ],
        'adverse_events': [
            'complications',
            'side effects',
            'adverse reactions',
            'potential complications',
            'risks and complications',
        ]
    }

    def identify_section(self, text: str, heading: str) -> Tuple[str, float]:
        """
        Identify what section this really is based on content analysis.
        Returns (section_name, confidence) tuple.
        """
        if not text and not heading:
            return 'unknown', 0.0

        text_lower = text.lower() if text else ""
        heading_lower = heading.lower() if heading else ""

        # First check if heading matches known aliases
        for section_name, aliases in self.SECTION_ALIASES.items():
            if heading_lower in [alias.lower() for alias in aliases]:
                return section_name, 0.9
            # Partial match
            for alias in aliases:
                if alias.lower() in heading_lower or heading_lower in alias.lower():
                    return section_name, 0.7

        # Score each section based on content
        scores = {}

        for section_name, signatures in self.SECTION_SIGNATURES.items():
            score = 0.0

            # Check must-have words (in heading is stronger signal)
            for word in signatures['must_have']:
                if word in heading_lower:
                    score += 3.0
                elif word in text_lower[:500]:  # Check first 500 chars of content
                    score += 1.5

            # Check should-have words
            for word in signatures.get('should_have', []):
                if word in heading_lower:
                    score += 1.5
                elif word in text_lower[:500]:
                    score += 0.5

            # Check must-not-have words (negative signal)
            for word in signatures['must_not_have']:
                if word in heading_lower:
                    score -= 3.0
                elif word in text_lower[:500]:
                    score -= 1.5

            # Check typical starts
            for pattern in signatures['typical_starts']:
                if re.search(pattern, text[:300], re.IGNORECASE):
                    score += 2.5

            # Check content keywords
            keyword_count = sum(1 for keyword in signatures.get('content_keywords', [])
                              if keyword in text_lower[:1000])
            score += min(keyword_count * 0.3, 2.0)  # Cap at 2.0

            scores[section_name] = max(0, score)  # Don't go negative

        # If no strong signal, return unknown
        if max(scores.values()) < 1.0:
            return 'unknown', 0.0

        # Return section with highest score
        best_section = max(scores.items(), key=lambda x: x[1])

        # Calculate confidence based on score
        confidence = min(best_section[1] / 10.0, 1.0)  # Normalize to 0-1

        return best_section[0], confidence

    def validate_section_placement(self, sections: Dict[str, str]) -> List[Dict[str, str]]:
        """
        Validate that sections are correctly identified and not swapped.
        Returns list of potential issues.
        """
        issues = []

        # Check if indications and intended use might be swapped
        if 'indications_for_use' in sections and 'intended_use' in sections:
            ind_content = sections['indications_for_use'].lower()
            int_content = sections['intended_use'].lower()

            # Check for swapped content
            if 'intended to' in ind_content and 'indicated for' in int_content:
                issues.append({
                    'type': 'possible_swap',
                    'sections': ['indications_for_use', 'intended_use'],
                    'reason': 'Content patterns suggest sections may be swapped'
                })

        # Check for missing critical sections
        if 'indications_for_use' not in sections and 'intended_use' not in sections:
            issues.append({
                'type': 'missing_critical',
                'sections': ['indications_for_use', 'intended_use'],
                'reason': 'No clinical use information found'
            })

        # Check for duplicate content
        if 'indications_for_use' in sections and 'intended_use' in sections:
            if sections['indications_for_use'] == sections['intended_use']:
                issues.append({
                    'type': 'duplicate_content',
                    'sections': ['indications_for_use', 'intended_use'],
                    'reason': 'Identical content in both sections'
                })

        return issues

    def suggest_correction(self, section_name: str, content: str) -> Optional[str]:
        """
        Suggest the correct section name based on content analysis.
        """
        identified, confidence = self.identify_section(content, section_name)

        if confidence > 0.7 and identified != section_name:
            return identified

        return None

    def merge_similar_sections(self, sections: Dict[str, str]) -> Dict[str, str]:
        """
        Merge sections that are variations of the same content.
        """
        merged = {}

        for section_name, content in sections.items():
            # Find canonical name
            canonical = None
            for canon, aliases in self.SECTION_ALIASES.items():
                if section_name.lower() == canon or section_name.lower() in [a.lower() for a in aliases]:
                    canonical = canon
                    break

            if not canonical:
                canonical = section_name

            # Merge content if section already exists
            if canonical in merged:
                # Avoid duplicating identical content
                if content not in merged[canonical]:
                    merged[canonical] = merged[canonical] + "\n\n" + content
            else:
                merged[canonical] = content

        return merged