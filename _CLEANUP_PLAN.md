# Documentation Cleanup Plan

## Files to KEEP (Essential)

1. **README.md** - Main project readme
2. **CHANGELOG.md** - Project changelog
3. **QUICK_START.md** - Quick start guide (needs update)
4. **SETUP_SUMMARY.md** - Current setup summary (needs update)
5. **docs/** folder - Keep existing docs
6. **documentation/** folder - Keep existing docs

## Files to CONSOLIDATE (These will be merged)

### Environment Setup (Merge into SETUP_SUMMARY.md)
- ENVIRONMENT_SETUP_COMPLETE.md
- ENV_LOADING_FIXED.md
- ENV_LOADING_GUIDE.md
- FINAL_VERIFICATION_COMPLETE.md
- CONDA_INIT_FIX.md
- SETUP_COMPLETE_SUMMARY.md
- INSTALLATION_COMPLETE.md
- QUICKUMLS_SETUP.md
- QUICKUMLS_STATUS.md
- UMLS_COPY_COMPLETE.md
- WORKAROUND_SOLUTION.md
- SIMPLE_SOLUTION.md
- FIX_EMPTY_ENVIRONMENT.md
- FIX_MEDPARSE_PY311.md
- ENVIRONMENT_CLEANUP.md
- CURRENT_STATUS.md
- FINAL_STATUS.md

### Batch Extraction (Merge into one file)
- BATCH_EXTRACTION_READY.md
- ENVIRONMENT_CLARIFICATION.md

### Old/Temporary Files (DELETE)
- ENVIRONMENT_CLARIFICATION.md
- HANDOFF_NEXT_SESSION.md
- MIGRATION_NOTES.md
- PATCH_STATUS.md
- IMPLEMENTATION_COMPLETE.md
- IMPLEMENTATION_STATUS.md
- IMPLEMENTATION_SUMMARY.md
- DEPENDENCIES.md

## Final Structure

Keep only these files:
```
IP_assist_lite/
├── README.md                          # Main readme
├── QUICK_START.md                     # Updated quick start
├── SETUP_SUMMARY.md                   # Consolidated setup info
├── BATCH_EXTRACTION.md                # Batch extraction guide
├── CHANGELOG.md                       # Keep as-is
├── docs/                              # Keep as-is
├── documentation/                     # Keep as-is
└── scripts/
    ├── env_setup_guide.md             # Keep
    └── ... (other scripts)
```

## Action Plan

1. Create new consolidated files
2. Update QUICK_START.md with current info
3. Create updated SETUP_SUMMARY.md
4. Create BATCH_EXTRACTION.md
5. Delete old/temporary files
6. Verify README.md is up to date

