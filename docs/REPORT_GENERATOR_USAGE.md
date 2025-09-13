# Report Generator Usage Guide

## Overview
The Report Generator allows users to create complete medical reports from brief procedure descriptions (mini-prompts).

## Access Points

### 1. Main Application UI
- **Location**: `http://localhost:7860` when running the main app
- **Tab**: "📝 Report Generator" 
- **Path**: `src/ui/enhanced_gradio_app.py`

To run the main application:
```bash
python src/ui/enhanced_gradio_app.py
```

### 2. Standalone Report Generator
- **Location**: `http://localhost:7862` when running standalone
- **Path**: `src/reporting/ui_tab.py`

To run standalone:
```bash
python src/reporting/ui_tab.py
```

### 3. Programmatic API
```python
from src.reporting.integration import generate_report_and_codes

result = generate_report_and_codes(
    miniprompt="Ion robotic bronchoscopy RLL, CBCT, 23G TBNA x5 ROSE positive",
    patient_ctx={
        "patient_name": "John Doe",
        "dod_id": "123456789",
        "date": "2024-01-15",
        "location": "OR 1",
        "physician_name": "Dr. Smith"
    }
)

print(result["report_text"])
print(result["cpt_codes"])
```

## User Input Fields

### Required Input
- **Mini-Prompt**: Brief procedure description (free text)
  - Example: "EBUS staging, stations 4R, 7, 11R, 22G x3 passes each, ROSE adequate"

### Optional Patient Information
- Patient Name
- DoD ID
- Procedure Date
- Location
- Physician Name

### Options
- **Run Quality Validators**: Check RCS-18 compliance and safety
- **Auto-fill Safe Defaults**: Fill missing non-critical fields
- **Use LLM for Structuring**: Enable AI-powered JSON structuring

## Output Sections

### 1. Report Tab
- Full synoptic report with RCS-18 compliance
- Includes all mandatory operative note fields
- Hybrid format with structured sections + narrative

### 2. JSON Tab
- Structured data in validated JSON format
- All procedure details extracted and organized
- Ready for downstream processing

### 3. CPT Codes Tab
- Professional codes (physician work)
- Technical codes (facility/equipment)
- Warnings for any coding issues

### 4. Validation Tab
- RCS-18 compliance check (18 required fields)
- Safety validations (lidocaine, complications)
- Data completeness assessment

## Example Mini-Prompts

### Robotic Navigation
```
Ion robotic bronchoscopy, RLL anterior segment, CBCT confirmation, 
23G TBNA x5 ROSE positive, 1.1mm cryo x3, minimal bleeding
```

### EBUS Staging
```
EBUS staging via ETT, stations 4R (12mm), 7 (8mm), 11R (15mm), 
all with 22G x3 passes, ROSE adequate
```

### PDT
```
PDT in ICU, bronch guided, rings 2-3, Ciaglia Blue Rhino kit, 
size 8 Shiley, no complications
```

### Ablation
```
Transbronchial microwave ablation RUL posterior, Ion navigation,
CBCT confirmation, 65W x 3 minutes, no pneumothorax
```

## Workflow

1. **Enter Mini-Prompt**: Type or paste procedure description
2. **Add Patient Info** (optional): Fill in demographics
3. **Select Options**: Choose validation and auto-fill preferences
4. **Generate**: Click "🚀 Generate Report"
5. **Review Output**: Check all tabs for results
6. **Export**: Copy report text or JSON as needed

## Integration with Coding Module

The Report Generator integrates with the Procedural Coding module:
1. Generate report → Structured JSON
2. JSON → Case object mapping
3. Case → CPT codes via deterministic rules

## Quality Assurance

The system validates:
- **RCS-18 Compliance**: All 18 mandatory operative note fields
- **Lidocaine Safety**: Dosing within safe limits (≤8 mg/kg)
- **Critical Safety**: Bleeding/PTX with interventions documented
- **EBUS Completeness**: Elastography for staging procedures
- **Imaging Consistency**: CBCT documentation when mentioned

## Evidence Base

The report generator follows evidence-based practices:
- RCS-18 criteria (Qasem et al. 2019) - 99.6% field compliance
- Synoptic + narrative hybrid approach
- Digital proformas with 63% auto-population
- Typed templates for 100% legibility

## Troubleshooting

### No output generated
- Check mini-prompt has recognizable procedure keywords
- Verify patient context fields don't have special characters

### Validation warnings
- Review RCS-18 missing fields
- Add more detail to mini-prompt for completeness

### Wrong procedure detected
- Use specific keywords (Ion, Monarch, EBUS, PDT)
- Include procedure type explicitly

## Support

For issues or enhancements:
- Check logs in console for detailed errors
- Review test fixtures in `data/fixtures/` for examples
- Run tests: `pytest src/tests/test_parser.py -v`