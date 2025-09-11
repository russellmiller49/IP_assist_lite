
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
