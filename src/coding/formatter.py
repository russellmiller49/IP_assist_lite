"""Enhanced formatters with copy functionality and multiple output formats."""

from typing import List, Dict, Optional
from .schema import CodeBundle, CodeLine

def to_markdown(bundle: CodeBundle) -> str:
    """Generate enhanced markdown output with better formatting."""
    def format_code_table(lines: List[CodeLine], title: str) -> str:
        if not lines:
            return f"### {title}\n_None_\n"
        
        out = [f"### {title}"]
        out.extend(["| Code | Description | Qty | Modifiers | Rationale |", 
                   "|------|-------------|----:|-----------|-----------|"])
        
        for line in lines:
            desc = line.description or ""
            if len(desc) > 40:
                desc = desc[:37] + "..."
            
            mods = ", ".join(line.modifiers) if line.modifiers else ""
            rationale = line.rationale or ""
            if len(rationale) > 60:
                rationale = rationale[:57] + "..."
            
            out.append(f"| `{line.code}` | {desc} | {line.quantity} | {mods} | {rationale} |")
        
        return "\n".join(out) + "\n"
    
    # Build markdown sections
    sections = []
    
    # Professional codes
    if bundle.professional:
        sections.append(format_code_table(bundle.professional, "Professional Component"))
    
    # Facility codes
    if bundle.facility:
        sections.append(format_code_table(bundle.facility, "Facility Component"))
    
    # ICD-10-PCS suggestions
    if bundle.icd10_pcs_suggestions:
        pcs_codes = ", ".join(f"`{code}`" for code in bundle.icd10_pcs_suggestions)
        sections.append(f"### ICD-10-PCS Suggestions (Facility)\n{pcs_codes}\n")
    
    # OPPS notes
    if bundle.opps_notes:
        sections.append("### OPPS Notes")
        for note in bundle.opps_notes:
            sections.append(f"• {note}")
        sections.append("")
    
    # Warnings
    if bundle.warnings:
        sections.append("### ⚠️ NCCI/Compliance Warnings")
        for warning in bundle.warnings:
            sections.append(f"• {warning}")
        sections.append("")
    
    # Documentation gaps
    if bundle.documentation_gaps:
        sections.append("### 📝 Documentation Requirements")
        for gap in bundle.documentation_gaps:
            sections.append(f"• {gap}")
        sections.append("")
    
    # Footer
    sections.append("> **Disclaimer:** CPT® is owned by the AMA. These are candidate codes based on "
                   "automated analysis. Always validate against current CPT/HCPCS manuals, local "
                   "coverage determinations, and payer-specific policies before billing.")
    
    return "\n".join(sections)

def to_copy_string(bundle: CodeBundle, format_type: str = "simple") -> str:
    """Generate copy-ready string in various formats."""
    if format_type == "simple":
        return format_simple_copy(bundle)
    elif format_type == "detailed":
        return format_detailed_copy(bundle)
    elif format_type == "billing":
        return format_billing_copy(bundle)
    else:
        return format_simple_copy(bundle)

def format_simple_copy(bundle: CodeBundle) -> str:
    """Simple comma-separated list of codes."""
    all_codes = []
    
    # Add professional codes
    for line in bundle.professional:
        code = line.code
        if line.modifiers:
            code += f"-{','.join(line.modifiers)}"
        if line.quantity > 1:
            code += f" x{line.quantity}"
        all_codes.append(code)
    
    # Add facility codes
    for line in bundle.facility:
        code = line.code + " (Facility)"
        if line.modifiers:
            code = line.code + f"-{','.join(line.modifiers)}" + " (Facility)"
        if line.quantity > 1:
            code += f" x{line.quantity}"
        all_codes.append(code)
    
    return ", ".join(all_codes)

def format_detailed_copy(bundle: CodeBundle) -> str:
    """Detailed format with descriptions and rationales."""
    lines = []
    
    if bundle.professional:
        lines.append("PROFESSIONAL COMPONENT:")
        for line in bundle.professional:
            code_str = line.code
            if line.modifiers:
                code_str += f"-{','.join(line.modifiers)}"
            if line.quantity > 1:
                code_str += f" x{line.quantity}"
            
            desc = line.description or ""
            rationale = line.rationale or ""
            
            if desc:
                lines.append(f"  {code_str}: {desc}")
            else:
                lines.append(f"  {code_str}")
            
            if rationale:
                lines.append(f"    → {rationale}")
        lines.append("")
    
    if bundle.facility:
        lines.append("FACILITY COMPONENT:")
        for line in bundle.facility:
            code_str = line.code
            if line.modifiers:
                code_str += f"-{','.join(line.modifiers)}"
            if line.quantity > 1:
                code_str += f" x{line.quantity}"
            
            desc = line.description or ""
            rationale = line.rationale or ""
            
            if desc:
                lines.append(f"  {code_str}: {desc}")
            else:
                lines.append(f"  {code_str}")
            
            if rationale:
                lines.append(f"    → {rationale}")
        lines.append("")
    
    if bundle.warnings:
        lines.append("WARNINGS:")
        for warning in bundle.warnings:
            lines.append(f"  ⚠ {warning}")
        lines.append("")
    
    return "\n".join(lines).strip()

def format_billing_copy(bundle: CodeBundle) -> str:
    """Format suitable for billing system import."""
    lines = []
    
    for line in bundle.professional:
        billing_line = {
            "code": line.code,
            "component": "Professional",
            "quantity": line.quantity,
            "modifiers": ",".join(line.modifiers) if line.modifiers else "",
            "description": line.description or "",
            "rationale": line.rationale or ""
        }
        
        # Format as tab-separated for easy import
        lines.append("\t".join([
            billing_line["code"],
            billing_line["component"], 
            str(billing_line["quantity"]),
            billing_line["modifiers"],
            billing_line["description"],
            billing_line["rationale"]
        ]))
    
    for line in bundle.facility:
        billing_line = {
            "code": line.code,
            "component": "Facility",
            "quantity": line.quantity,
            "modifiers": ",".join(line.modifiers) if line.modifiers else "",
            "description": line.description or "",
            "rationale": line.rationale or ""
        }
        
        lines.append("\t".join([
            billing_line["code"],
            billing_line["component"],
            str(billing_line["quantity"]),
            billing_line["modifiers"], 
            billing_line["description"],
            billing_line["rationale"]
        ]))
    
    # Add header
    if lines:
        header = "Code\tComponent\tQty\tModifiers\tDescription\tRationale"
        return header + "\n" + "\n".join(lines)
    
    return ""

def get_code_summary(bundle: CodeBundle) -> Dict[str, int]:
    """Get summary statistics about the code bundle."""
    return {
        "total_professional": len(bundle.professional),
        "total_facility": len(bundle.facility),
        "total_codes": len(bundle.professional) + len(bundle.facility),
        "warnings": len(bundle.warnings),
        "documentation_gaps": len(bundle.documentation_gaps),
        "pcs_suggestions": len(bundle.icd10_pcs_suggestions)
    }

def format_for_gradio(bundle: CodeBundle) -> tuple:
    """Format bundle for Gradio interface (markdown, copy string, summary)."""
    markdown = to_markdown(bundle)
    copy_string = to_copy_string(bundle, "simple")
    summary = get_code_summary(bundle)
    
    return markdown, copy_string, summary