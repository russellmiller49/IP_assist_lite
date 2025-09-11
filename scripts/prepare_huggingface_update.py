#!/usr/bin/env python3
"""
Prepare files for Hugging Face Space update with all recent improvements.
This script collects all updated files and creates deployment instructions.
"""

import shutil
import json
from pathlib import Path
from datetime import datetime

# Create deployment directory
deploy_dir = Path("huggingface_deploy")
deploy_dir.mkdir(exist_ok=True)

print("🚀 Preparing Hugging Face deployment package...")
print("=" * 60)

# List of critical files to update
files_to_update = {
    # Core improvements
    "src/llm/gpt5_medical.py": "GPT-5 integration with 4000 token output",
    "src/retrieval/hybrid_retriever.py": "Balanced scoring for article retrieval",
    "src/retrieval/query_normalizer.py": "Query normalization for typos/abbreviations",
    "src/orchestrator/enhanced_orchestrator.py": "Smart citation system integration",
    "src/orchestrator/smart_citations.py": "Intelligent citation insertion",
    "src/ui/enhanced_gradio_app.py": "UI improvements and citation display",
    
    # Configuration files
    "configs/citation_policy.yaml": "Citation filtering policy",
    "data/citation_index.json": "Pre-built author/citation index",
    
    # Build scripts
    "scripts/build_citation_index.py": "Citation index builder",
}

# Copy files to deployment directory
print("\n📁 Collecting updated files:")
for src_file, description in files_to_update.items():
    src_path = Path(src_file)
    if src_path.exists():
        dst_path = deploy_dir / src_file
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst_path)
        print(f"  ✓ {src_file} - {description}")
    else:
        print(f"  ⚠ {src_file} not found - {description}")

# Create requirements update
requirements_additions = """
# Add these to requirements.txt if not present:
rapidfuzz>=3.0.0  # For query normalization
pyyaml>=6.0  # For configuration files
"""

with open(deploy_dir / "requirements_additions.txt", "w") as f:
    f.write(requirements_additions)

# Create deployment instructions
instructions = """
# Hugging Face Space Update Instructions

## Overview
This update includes major improvements to IP Assist Lite:
1. **Smart Citations**: Automatic citation insertion based on content matching
2. **Query Normalization**: Handles typos and medical abbreviations
3. **Better Article Retrieval**: Balanced scoring allows articles to compete with textbooks
4. **Citation Index**: Pre-built index with proper author names
5. **Improved Formatting**: Bold headers, bullets, and proper spacing
6. **Increased Output**: 4000 tokens for comprehensive responses

## Step-by-Step Deployment

### 1. Clone your Hugging Face Space
```bash
git clone https://huggingface.co/spaces/bronchmonkey2/IP_assist_lite
cd IP_assist_lite
```

### 2. Update Core Files
Copy all files from `huggingface_deploy/` to your Space repository:
```bash
cp -r huggingface_deploy/src/* src/
cp -r huggingface_deploy/configs/* configs/
cp -r huggingface_deploy/data/* data/
cp -r huggingface_deploy/scripts/* scripts/
```

### 3. Update Requirements
Add these dependencies to `requirements.txt`:
```
rapidfuzz>=3.0.0
pyyaml>=6.0
```

### 4. Environment Variables
Ensure these are set in your Space settings:
- `OPENAI_API_KEY`: Your OpenAI API key
- `IP_GPT5_MODEL`: Set to "gpt-5-mini" (default)
- `USE_RESPONSES_API`: Set to "1" for GPT-5 responses API
- `REASONING_EFFORT`: Set to "medium" (optional)

### 5. Key Changes to Verify

#### A. Citation Policy (configs/citation_policy.yaml)
- Textbooks are excluded from citations
- Only journal articles shown in references

#### B. Query Normalizer (src/retrieval/query_normalizer.py)
- Fixes typos like "fistua" → "fistula"
- Expands abbreviations: "TEF" → "tracheoesophageal fistula"

#### C. Smart Citations (src/orchestrator/smart_citations.py)
- Automatically adds numbered citations based on content
- Uses citation index for proper author names

#### D. Retrieval Balance (src/retrieval/hybrid_retriever.py)
- Reduced textbook boost: A1 (10%), A2/A3 (5%)
- Balanced scoring: precedence 45%, semantic 35%

#### E. GPT-5 Configuration (src/llm/gpt5_medical.py)
- Max output: 4000 tokens
- Default model: gpt-5-mini

### 6. Test After Deployment
Test these queries to verify improvements:
1. "management of benign TE fistua" (with typo)
   - Should normalize to "tracheoesophageal fistula"
   - Should show article citations, not textbooks

2. "TEF treatment options"
   - Should expand TEF to full term
   - Should retrieve relevant articles

3. Check citations format:
   - Should show "Schweigert et al. (2019)" not "Fistula et al."
   - References should only list journal articles

### 7. Commit and Push
```bash
git add .
git commit -m "Major update: Smart citations, query normalization, better retrieval"
git push
```

## Important Notes

1. **Citation Index**: The `data/citation_index.json` file is crucial for proper author names
2. **No Textbook Leaks**: Verify no "papoip", "BACADA" references appear in citations
3. **Formatting**: Responses should have bold headers and bullet points
4. **Performance**: Initial load may be slower due to citation index loading

## Rollback Plan
If issues occur, revert to previous commit:
```bash
git revert HEAD
git push
```

## Verification Checklist
- [ ] Query normalization working (typos/abbreviations)
- [ ] Citations show proper author names
- [ ] Only journal articles in references
- [ ] Responses have good formatting
- [ ] No textbook names leak in citations
- [ ] Output length sufficient (no cutoffs)

---
Generated: {datetime.now().isoformat()}
"""

with open(deploy_dir / "DEPLOYMENT_INSTRUCTIONS.md", "w") as f:
    f.write(instructions)

# Create a summary of changes
changes_summary = """
# Summary of Changes

## Files Modified
1. **src/llm/gpt5_medical.py**
   - Increased max_out from 2000 to 4000 tokens
   - Better text extraction for GPT-5 responses

2. **src/retrieval/hybrid_retriever.py**
   - Added query normalization integration
   - Reduced textbook score boost (A1: 10%, A2/A3: 5%)
   - Balanced scoring weights
   - Increased retrieval volume

3. **src/retrieval/query_normalizer.py** (NEW)
   - Handles medical abbreviations and synonyms
   - Fixes typos with fuzzy matching
   - Expandable synonym dictionary

4. **src/orchestrator/enhanced_orchestrator.py**
   - Integrated smart citation system
   - Added citation filtering policy
   - Removed doc_id from prompts
   - Better formatting instructions

5. **src/orchestrator/smart_citations.py** (NEW)
   - Content-based citation matching
   - Uses citation index for author names
   - Intelligent citation placement

6. **src/ui/enhanced_gradio_app.py**
   - Fixed citation display
   - Uses 'text' field from smart citations
   - Better error handling

7. **configs/citation_policy.yaml** (NEW)
   - Defines which documents to cite
   - Excludes textbooks from references

8. **data/citation_index.json** (NEW)
   - Pre-built index of doc_id → author/year/title
   - Fixes author extraction issues

## Key Improvements
- ✅ No more "Fistula et al." - proper author names
- ✅ Textbooks hidden from citations but still used for accuracy
- ✅ Query typos and abbreviations handled automatically
- ✅ Better article retrieval with balanced scoring
- ✅ Improved response formatting with headers and bullets
- ✅ Longer responses without cutoffs
"""

with open(deploy_dir / "CHANGES_SUMMARY.md", "w") as f:
    f.write(changes_summary)

print("\n📋 Created deployment files:")
print(f"  ✓ {deploy_dir}/DEPLOYMENT_INSTRUCTIONS.md")
print(f"  ✓ {deploy_dir}/CHANGES_SUMMARY.md")
print(f"  ✓ {deploy_dir}/requirements_additions.txt")
print(f"\n✅ Deployment package ready in: {deploy_dir}/")
print("\n📌 Next steps:")
print("  1. Review DEPLOYMENT_INSTRUCTIONS.md")
print("  2. Copy files to your Hugging Face Space")
print("  3. Test the deployment")