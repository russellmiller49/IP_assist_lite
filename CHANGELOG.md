# Changelog

## [2.0.0] - 2025-09-12

### Major Changes
- **Enhanced Version is Now Standard**: The enhanced Gradio app with conversation support is now the default `app.py`
- **Legacy Version Archived**: The basic version is preserved as `app_basic.py` for backward compatibility

### New Features

#### Enhanced Query Assistant
- ✅ Multi-turn conversation support with context retention
- ✅ Follow-up questions capability 
- ✅ Full AMA-style citations with journal details
- ✅ Session management for continuous dialogue
- ✅ Model selection (GPT-5, GPT-4, etc.)

#### V3 Procedural Coding Module
- ✅ Automatic CPT/HCPCS code generation from procedure reports
- ✅ Interactive Q&A about code selections ("Why this code?")
- ✅ EBUS station counting (31652 vs 31653)
- ✅ TBLB lobe tracking with add-on codes
- ✅ Sedation time calculation with proper code families
- ✅ NCCI edit checks and warnings
- ✅ OPPS packaging notes
- ✅ ICD-10-PCS suggestions
- ✅ Documentation gap detection
- ✅ Bilateral modifier (-50) support
- ✅ KB version tracking for traceability

### Enhancements

#### Knowledge Base (KB)
- ✅ Automatic fallback between `ip_coding_billing.json` and `coding_module.json`
- ✅ Code description lookups with defaults
- ✅ Bilateral eligible codes configuration
- ✅ Version info reporting (file mtime or metadata version)

#### Code Quality
- ✅ Type-safe enums for structure types
- ✅ Error handling with graceful degradation
- ✅ Parsing warnings propagation
- ✅ Named regex groups for better maintainability

#### User Experience
- ✅ Fixed Gradio API schema issues with gr.State
- ✅ Added copy-ready code strings
- ✅ KB version displayed in output
- ✅ Simplified startup with `run.sh` script

### Technical Improvements
- Replaced complex gr.State dictionaries with JSON strings to avoid API schema errors
- Enhanced pattern matching with named groups
- Added comprehensive error handling in extractors
- Improved citation deduplication

### Files Changed
- `app.py` - Now the enhanced version with all features
- `app_basic.py` - Archived basic version
- `src/coding/` - Complete V3 coding module implementation
- `src/ui/enhanced_gradio_app.py` - Enhanced interface (now copied to app.py)
- `README.md` - Updated documentation
- `run.sh` - New startup script

### Migration Guide
For users upgrading from the basic version:
1. The main `app.py` now includes all enhanced features
2. No changes needed for basic usage - just run `python app.py`
3. For legacy behavior, use `python app_basic.py`
4. Environment variables remain the same

### Known Issues Resolved
- ✅ Fixed duplicate citations in references
- ✅ Fixed CPT code extraction from reports
- ✅ Fixed Gradio API schema TypeError with complex state objects
- ✅ Fixed citation formatting to use actual metadata

## [1.0.0] - Previous Version
- Basic query interface
- Simple citation format
- V2 coding module
- Single-turn queries only