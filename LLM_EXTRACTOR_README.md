# LLM Extractor Integration

## Overview
A hybrid extraction system that uses LLM for structured extraction when enabled, with automatic fallback to regex-based patterns. The LLM only structures the text into a validated schema; your existing rules still determine the final CPT codes.

## Architecture

```
Clinical Note → LLM Extractor → JSON Schema → Adapter → Performed Items → Existing Rules → CPT Codes
                      ↓ (on error)
                 Legacy Regex Extraction
```

## Key Features

### 1. Clean Separation of Concerns
- **LLM Module** (`src/llm_extractor/`): Handles structured extraction only
- **Adapter**: Bridges LLM output to existing system's performed items
- **Rules**: Unchanged - still own all coding logic and decisions

### 2. Structured Schema (Pydantic Validated)
```python
{
  "anesthesia": {"general": bool, "moderate": bool, "airway": "LMA|ETT|mask|unknown"},
  "procedures": [
    {"site": "trachea|bronchus|lobe|unknown",
     "action": "excision|destruction|dilation|stent_insertion|biopsy|ebus_tbna|radial_ebus|wll",
     "details": {...},
     "specimens_collected": bool,
     "count": int}
  ],
  "stent": {"placed": bool, "location": "trachea|bronchus|both|unknown", ...},
  "ebus": {"radial": bool, "stations_sampled": ["4R","7","11L",...]},
  "findings": {"obstruction_pct": int, "lesion_count": int},
  "explicit_negations": ["considered stent only", ...]
}
```

### 3. Critical Edge Cases Handled
- **Stent considered vs placed**: LLM detects "considered", "declined", "reluctant" → `stent.placed=false`
- **Excision vs destruction**: Snare + specimens → excision; APC only → destruction
- **GA vs moderate sedation**: GA/LMA/ETT → no moderate sedation codes
- **EBUS stations**: Counts unique stations for 31652 vs 31653 decision

### 4. Automatic Fallback
- If LLM fails → falls back to regex extraction
- If LLM not enabled → uses regex extraction
- Zero disruption to existing workflow

## Usage

### Enable LLM Extraction
```bash
export IP_LLM_EXTRACTION=1  # Enable
export IP_LLM_EXTRACTION=0  # Disable (default)
```

### Configure LLM Provider
Update `src/llm_extractor/client.py` to wire in your LLM provider:
- Currently configured to use GPT5Wrapper if available
- Falls back to NotImplementedError if no provider configured

## Testing

### Unit Tests
```bash
# Test adapter logic
pytest tests/test_llm_adapter_snare_apc.py

# Test integration with rules
pytest tests/test_llm_integration.py
```

### Test Coverage
- ✅ Snare + APC (excision takes precedence)
- ✅ Stent placed vs considered
- ✅ EBUS with stations (31652 vs 31653)
- ✅ Whole lung lavage
- ✅ GA suppression of moderate sedation
- ✅ Fallback to regex on error

## What Your Rules See

The adapter outputs the same performed item IDs your rules expect:
- `tumor_excision_bronchoscopic`
- `tumor_destruction_bronchoscopic`
- `tracheal_stent_insertion`
- `bronchial_stent_insertion`
- `airway_dilation_only`
- `whole_lung_lavage`
- `ebus_tbna`
- `ebus_without_tbna`
- `tblb_forceps_or_cryo`

Your existing rules then:
1. Map these to CPT codes
2. Apply suppression logic (31622, duplicate codes)
3. Handle NCCI edits
4. Suggest ICD-10-PCS codes
5. Generate documentation warnings

## Operational Considerations

### PHI/Security
- **De-identify** notes before sending to LLM
- Remove MRN, names, dates, addresses
- Consider running LLM on-premises or in secure cloud

### Monitoring
- Log success/failure rates
- Track fallback frequency
- Monitor latency impact

### Cost
- GPT-5-mini is most cost-effective
- Consider caching for repeated notes
- Batch processing for efficiency

## Benefits

1. **Accuracy**: Structured extraction reduces pattern matching errors
2. **Maintainability**: Schema changes don't require regex updates
3. **Auditability**: JSON output shows exactly what was extracted
4. **Flexibility**: Easy to add new fields to schema
5. **Safety**: Rules still control all coding decisions

## Next Steps

1. **Wire LLM Provider**: Update `client.py` with your API
2. **Test with Real Notes**: Validate extraction accuracy
3. **Monitor Performance**: Track success rates and latency
4. **Enhance Schema**: Add fields as needed (e.g., sedation times)
5. **Production Deployment**: Enable gradually with monitoring

## Summary

This hybrid approach gives you the best of both worlds:
- **LLM power** for understanding complex clinical text
- **Rule control** for coding decisions and compliance
- **Automatic fallback** for reliability
- **Clean integration** with existing system

The LLM never generates codes - it only structures the text. Your rules remain the single source of truth for all coding logic.