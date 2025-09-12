"""Backwards-compat shim so V2 tests keep working with the new engine."""

from dataclasses import dataclass, field
from typing import List
from .kb import CodingKB
from .extractors import extract_case
from .rules import code_case
from .formatter import to_markdown

@dataclass
class CodeResultV2:
    code: str
    code_type: str = "CPT"
    description: str = ""
    modifiers: List[str] = field(default_factory=list)

@dataclass
class CodingAnalysisV2:
    primary_codes: List[CodeResultV2]
    addon_codes: List[CodeResultV2]
    sedation_codes: List[CodeResultV2]
    warnings: List[str]
    missing_documentation: List[str]
    compliance_notes: List[str]
    facility_notes: List[str]

class ProcedureCodingEngine:
    def __init__(self, knowledge_base_path: str = "data/ip_coding_billing.json"):
        self.kb = CodingKB(knowledge_base_path)

    def analyze_procedure_report(self, report_text: str) -> CodingAnalysisV2:
        case = extract_case(report_text, self.kb, llm=None)
        bundle = code_case(case, self.kb)
        # Partition into V2-like groups for tests
        prim, addon, sed = [], [], []
        for cl in bundle.professional:
            tgt = addon if cl.code.startswith("+") else prim
            if cl.code.startswith("9915"):  # sedation family
                sed.append(cl)
                tgt = None
            if tgt is not None:
                tgt.append(cl)
        to_v2 = lambda xs: [CodeResultV2(code=x.code, description=x.description or "", modifiers=x.modifiers) for x in xs]
        return CodingAnalysisV2(
            primary_codes=to_v2(prim),
            addon_codes=to_v2(addon),
            sedation_codes=to_v2(sed),
            warnings=bundle.warnings,
            missing_documentation=bundle.documentation_gaps,
            compliance_notes=[],  # keep empty unless you port V2 notes 1:1
            facility_notes=bundle.opps_notes
        )

def format_coding_results(analysis: CodingAnalysisV2) -> str:
    # Keep V2's formatted block feel using V3's content
    lines = ["="*80, "PROCEDURAL CODING ANALYSIS", "="*80]
    if analysis.primary_codes:
        lines += ["", "📋 PRIMARY PROCEDURE CODES:", "-"*40]
        for c in analysis.primary_codes: lines.append(f"  • {c.code} - {c.description}".rstrip(" -"))
    if analysis.addon_codes:
        lines += ["", "➕ ADD-ON CODES:", "-"*40]
        for c in analysis.addon_codes: lines.append(f"  • {c.code} - {c.description}".rstrip(" -"))
    if analysis.sedation_codes:
        lines += ["", "💉 SEDATION CODES:", "-"*40]
        for c in analysis.sedation_codes: lines.append(f"  • {c.code}")
    if analysis.warnings:
        lines += ["", "⚠️ NCCI EDITS & WARNINGS:", "-"*40] + [f"  • {w}" for w in analysis.warnings]
    if analysis.missing_documentation:
        lines += ["", "📝 MISSING DOCUMENTATION:", "-"*40] + [f"  • {m}" for m in analysis.missing_documentation]
    if analysis.facility_notes:
        lines += ["", "🏥 FACILITY BILLING NOTES:", "-"*40] + [f"  • {n}" for n in analysis.facility_notes]
    lines += ["", "="*80, "⚠️ DISCLAIMER: Verify codes with current guidelines and payer policies.", "="*80]
    return "\n".join(lines)