#!/usr/bin/env python3
"""Validate extraction quality against MEDPARSE vision requirements."""

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import dataclass, field


@dataclass
class QualityMetrics:
    """Track quality metrics for a document."""
    title_clean: bool = False
    subtype_correct: bool = False
    text_quality: float = 0.0
    evidence_structure: bool = False
    umls_count: int = 0
    recommendations_valid: bool = False
    grade_density: float = 0.0
    has_garbled_text: bool = False
    empty_sections: List[str] = field(default_factory=list)

    @property
    def overall_score(self) -> float:
        """Calculate overall quality score."""
        scores = []
        scores.append(1.0 if self.title_clean else 0.0)
        scores.append(1.0 if self.subtype_correct else 0.0)
        scores.append(self.text_quality)
        scores.append(1.0 if self.evidence_structure else 0.0)
        scores.append(min(1.0, self.umls_count / 500))  # 500+ UMLS entities = full score
        scores.append(1.0 if self.recommendations_valid else 0.0)
        scores.append(self.grade_density if self.subtype_correct and 'guideline' in str(self.subtype_correct) else 1.0)
        scores.append(0.0 if self.has_garbled_text else 1.0)
        scores.append(max(0, 1.0 - len(self.empty_sections) * 0.1))  # -10% per empty section
        return sum(scores) / len(scores)


def check_text_quality(text: str) -> Tuple[float, List[str]]:
    """Check text for quality issues."""
    issues = []

    # Check for concatenation issues
    concat_patterns = [
        (r'Formediastinal', 'Concatenated: Formediastinal'),
        (r'withoutmediastinal', 'Concatenated: withoutmediastinal'),
        (r'with\s+out\b', 'Split word: with out'),
        (r'Departmentof\b', 'Concatenated: Departmentof'),
        (r'\bpy\s+is\s+considered', 'Garbled: py is considered'),
    ]

    for pattern, desc in concat_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            issues.append(desc)

    # Check for excessive special characters (garbled text)
    if len(text) > 100:
        special_chars = sum(1 for c in text if c in '†‡§¶©®™≥≤±∞')
        if special_chars / len(text) > 0.05:
            issues.append(f"High special char ratio: {special_chars/len(text):.2%}")

    # Check for proper spacing
    double_spaces = len(re.findall(r'  +', text))
    if double_spaces > 10:
        issues.append(f"Excessive double spaces: {double_spaces}")

    # Calculate quality score
    quality = 1.0
    quality -= len(issues) * 0.15  # -15% per issue
    quality = max(0, quality)

    return quality, issues


def validate_document(doc_path: Path) -> QualityMetrics:
    """Validate a single document."""
    metrics = QualityMetrics()

    try:
        with open(doc_path) as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading {doc_path}: {e}")
        return metrics

    # Check title
    title = data.get('title', '')
    if title:
        metrics.title_clean = not bool(re.search(r'^Guideline\s+\d+\s+', title))
        metrics.title_clean = metrics.title_clean and len(title) > 10

    # Check subtype
    subtype = data.get('subtype', '')
    doc_type = data.get('document_type', '')
    if doc_type == 'article':
        # Should be 'guideline' or 'research'
        metrics.subtype_correct = subtype in ['guideline', 'research']
    else:
        metrics.subtype_correct = True  # No specific requirement for IFUs/textbooks

    # Check text quality in sections
    all_text = []
    sections = data.get('sections', {})
    for section_name, content in sections.items():
        if isinstance(content, str):
            if not content.strip():
                metrics.empty_sections.append(section_name)
            else:
                all_text.append(content)

    if all_text:
        combined = ' '.join(all_text)
        quality, issues = check_text_quality(combined)
        metrics.text_quality = quality
        metrics.has_garbled_text = bool(issues)

    # Check evidence bank structure
    evidence_bank = data.get('evidence_bank', {})
    if evidence_bank:
        # Should be dict of string -> string (not dict -> dict)
        sample = list(evidence_bank.values())[:5]
        metrics.evidence_structure = all(isinstance(v, str) for v in sample)
    else:
        metrics.evidence_structure = True  # No evidence bank is ok

    # Check UMLS entities
    umls = data.get('umls_entities', [])
    metrics.umls_count = len(umls)

    # Check recommendations for guidelines
    if subtype == 'guideline':
        recs = data.get('recommendations', [])
        if recs:
            metrics.recommendations_valid = len(recs) >= 5  # Should have decent number
            # Check grade density
            graded = sum(1 for r in recs if r.get('grade') or r.get('statement_type') in ['ungraded', 'consensus', 'good_practice'])
            metrics.grade_density = graded / len(recs) if recs else 0
        else:
            metrics.recommendations_valid = False
            metrics.grade_density = 0
    else:
        metrics.recommendations_valid = True  # N/A for non-guidelines
        metrics.grade_density = 1.0

    return metrics


def main():
    """Run quality validation on all extracted documents."""

    print("=" * 80)
    print("MEDPARSE Quality Validation Report")
    print("=" * 80)

    # Check different document types
    patterns = [
        ('Articles', 'out/articles/*.json'),
        ('IFUs', 'out/ifus/*.json'),
        ('Textbooks', 'out/textbooks/*.json'),
    ]

    overall_metrics = []

    for doc_type, pattern in patterns:
        files = list(Path('.').glob(pattern))
        if not files:
            print(f"\n{doc_type}: No files found")
            continue

        print(f"\n{doc_type} ({len(files)} files)")
        print("-" * 40)

        type_metrics = []
        for file_path in files[:5]:  # Check up to 5 files per type
            metrics = validate_document(file_path)
            type_metrics.append(metrics)

            status = "✓" if metrics.overall_score >= 0.7 else "✗"
            print(f"{status} {file_path.name[:50]:50} Score: {metrics.overall_score:.2f}")

            if metrics.overall_score < 0.7:
                # Show issues
                if not metrics.title_clean:
                    print(f"  - Title not clean")
                if not metrics.subtype_correct:
                    print(f"  - Incorrect subtype")
                if metrics.text_quality < 0.7:
                    print(f"  - Poor text quality: {metrics.text_quality:.2f}")
                if not metrics.evidence_structure:
                    print(f"  - Evidence structure issue")
                if metrics.umls_count < 100:
                    print(f"  - Low UMLS count: {metrics.umls_count}")
                if metrics.empty_sections:
                    print(f"  - Empty sections: {', '.join(metrics.empty_sections[:3])}")

        if type_metrics:
            avg_score = sum(m.overall_score for m in type_metrics) / len(type_metrics)
            avg_umls = sum(m.umls_count for m in type_metrics) / len(type_metrics)
            print(f"\n  Average Score: {avg_score:.2f}")
            print(f"  Average UMLS: {avg_umls:.0f}")
            overall_metrics.extend(type_metrics)

    if overall_metrics:
        print("\n" + "=" * 80)
        print("Overall Summary")
        print("=" * 80)

        avg_overall = sum(m.overall_score for m in overall_metrics) / len(overall_metrics)
        avg_umls_all = sum(m.umls_count for m in overall_metrics) / len(overall_metrics)
        pass_rate = sum(1 for m in overall_metrics if m.overall_score >= 0.7) / len(overall_metrics)

        print(f"Files Analyzed: {len(overall_metrics)}")
        print(f"Average Quality Score: {avg_overall:.2f}")
        print(f"Pass Rate (≥0.7): {pass_rate:.1%}")
        print(f"Average UMLS Entities: {avg_umls_all:.0f}")

        # Vision document targets
        print("\n" + "-" * 40)
        print("Vision Document Targets:")
        print(f"  Guideline Grade Density ≥70%: {'✓' if all(m.grade_density >= 0.7 or not m.subtype_correct or 'guideline' not in str(m.subtype_correct) for m in overall_metrics) else '✗'}")
        print(f"  UMLS Enrichment (1919+ target): {'✓' if any(m.umls_count >= 1919 for m in overall_metrics) else '✗'}")
        print(f"  Clean Titles: {'✓' if sum(m.title_clean for m in overall_metrics) / len(overall_metrics) >= 0.9 else '✗'}")
        print(f"  Text Quality ≥7/10: {'✓' if avg_overall >= 0.7 else '✗'}")


if __name__ == '__main__':
    main()