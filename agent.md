# Medparse ↔ IP_Assist_Lite Integration Guide

## Scope
- Documents how the IP_Assist_Lite app consumes the Medparse sidecar API and what must be in place for the cross-repo workflow to function.
- Captures the runtime requirements, configuration, request contracts, and validation steps so any maintainer or QA agent can spin up both services quickly.
- Highlights the remaining engineering work that must land inside IP_Assist_Lite before Medparse data can drive graph enrichment and UI evidence panels.

---

## Repository Layout
- **IP_Assist_Lite** (this repo): `/home/rjm/projects/IP_assist_lite`
- **Medparse sidecar**: `/home/rjm/projects/ip_knowledge/medparse/medparse-docling`
- Keep both repos on their default `main` branch unless a coordinated feature branch is in flight. The FastAPI app lives inside `medparse-docling/api` and should be treated as the source of truth for request/response models.

---

## Architecture Overview
- **Medparse (FastAPI, Python 3.10–3.11)**
  - Runs Docling + GROBID + enrichment to turn PDFs into structured JSON.
  - Provides UMLS concept linking via remote API first, falling back to QuickUMLS or scispaCy.
  - Exposes `GET /healthz`, `GET /version`, `POST /link`, and `POST /extract`; all routes are optionally protected by the `X-API-Key` header when `API_KEY` is set in `.env`.
  - Allows lightweight smoke tests by setting `ENABLE_PIPELINE=false`, returning stub payloads while keeping the HTTP contract intact.
- **IP_Assist_Lite (Gradio/LangGraph, Python 3.12)**
  - Calls Medparse over HTTP for concept seeding and full-document ingestion. All interaction happens through the REST boundary so the different Python versions never conflict.
  - Uses Medparse responses to enrich the Neo4j graph (planned), seed Qdrant, and drive evidence counters in the UI. Until the client and ingest code are added, the integration is dormant.

---

## Medparse Sidecar Setup
1. **Activate repo**
   ```bash
   cd /home/rjm/projects/ip_knowledge/medparse/medparse-docling
   ```
2. **Create environment (Python 3.11 recommended)**
   ```bash
   conda create -n medparse-py311 python=3.11 -y
   conda activate medparse-py311
   pip install -r requirements.txt  # or: pip install -e .[dev]
   ```
3. **Optional extras**
   - Install `pytesseract` if figure OCR is required.
   - Fetch the QuickUMLS data once per machine (see below).
4. **Provision `.env`**
   ```bash
   cp .env.example .env
   # edit values described in the tables below
   ```
5. **Start supporting services**
   - GROBID (recommended): `docker run -d -p 8070:8070 lfoppiano/grobid:0.8.0`
   - QuickUMLS index: ensure the folder from the build step is reachable by the sidecar.
6. **Launch the API**
   ```bash
   uvicorn api.main:app --reload --port 8099
   ```
7. **Quick verification**
   ```bash
   curl -s http://127.0.0.1:8099/healthz
   curl -s -X POST http://127.0.0.1:8099/link \
     -H 'Content-Type: application/json' \
     -H "X-API-Key: $API_KEY" \
     -d '{"text": "massive hemoptysis"}' | jq
   ```
   Expect either real UMLS hits or QuickUMLS fallbacks when `ENABLE_PIPELINE=true`. With `ENABLE_PIPELINE=false` you receive an empty-but-well-formed payload that exercises the contract without heavy processing.

---

## Configuration Reference

### Required `.env` keys (Medparse)
| Variable | Description |
| --- | --- |
| `QUICKUMLS_PATH` | Local QuickUMLS index directory; omit to skip local linking. |
| `GROBID_URL` | Endpoint for TEI parsing, e.g. `http://localhost:8070`. |
| `API_TITLE`, `API_VERSION` | Shown on `/version` and FastAPI docs. |
| `ALLOWED_ORIGINS` | CORS whitelist (include the IP_Assist_Lite UI origin, usually `http://localhost:7860`). |
| `MAX_UPLOAD_MB` | Upload cap enforced by `/extract`. |
| `ENABLE_PIPELINE` | `true` for full Docling pipeline, `false` for stubs. |
| `API_KEY` | Optional secret; when set callers must send `X-API-Key`. |

### Optional `.env` keys
| Variable | Purpose |
| --- | --- |
| `UMLS_API_KEY` | Enables remote UMLS linking (first attempt). |
| `NCBI_API_KEY`, `NCBI_EMAIL` | PubMed enrichment for references. |

### QuickUMLS Index Build (one time)
```bash
QUICKUMLS_OUT=/home/rjm/projects/ip_knowledge/quickumls_data
mkdir -p "$QUICKUMLS_OUT"
quickumls_install \
  --umls /mnt/c/UMLS/2025AA/META \
  --language ENG \
  --output_path "$QUICKUMLS_OUT"
# Use QUICKUMLS_PATH=$QUICKUMLS_OUT/2025AA_ENG in .env
```
The availability probe accepts both `cui-semtypes.db` and `cui_semtypes.db` naming schemes, matching the patches in `medparse-docling`.

---

## API Contract & Authentication
- **Authentication**: When `API_KEY` is empty the API is open. When defined, every request must include `X-API-Key: <value>`; missing or mismatched keys return `401`.
- **Endpoints**
| Method | Path | Body | Response |
| --- | --- | --- | --- |
| `GET` | `/healthz` | None | `{ "ok": true }` on success. |
| `GET` | `/version` | None | `{ "title": ..., "version": ... }` from settings. |
| `POST` | `/link` | JSON `{ "text": str, "top_k": int=20 }` | `LinkResponse` with `umls_links` list. |
| `POST` | `/extract` | Multipart form with fields `pdf` (file) and `doc_id` (string) | `ExtractionResult` containing metadata, concept links, statistics, figures, tables, validation. |

### Example responses
```json
POST /link → {
  "doc_id": null,
  "umls_links": [
    {
      "cui": "C0019079",
      "text": "massive hemoptysis",
      "tui": ["T046"],
      "score": 0.93,
      "preferred_name": "Hemoptysis",
      "source": "QuickUMLS"
    }
  ]
}

POST /extract → {
  "doc_id": "AMPLE2",
  "metadata": {"title": "Sample Document"},
  "references_enriched": [],
  "umls_links": [...],
  "umls_links_local": [...],
  "statistics": [{"kind": "p_value", "value": 0.012, "sentence": "..."}],
  "figures": [{"kind": "figure", "caption": "Figure 1."}],
  "tables": [{"kind": "table", "caption": "Table 1."}],
  "validation": {"completeness_score": 87, "issues": []}
}
```

---

## IP_Assist_Lite Integration Work
- **Configuration surface**
  - Add `MEDPARSE_URL` and `MEDPARSE_API_KEY` (if used) to the IP_Assist_Lite environment handling. A simple approach is to extend the existing config loader to read from `os.environ` or a `.env` file.
- **HTTP client**
  - Create a lightweight async client (recommended location: `src/adapters/medparse_client.py` or a new `src/integrations` package).
  - Responsibilities: `link(text: str, top_k: int = 20)` returning Medparse concepts, `extract(pdf_path: Path, doc_id: str)` streaming multipart uploads, header injection for `X-API-Key`, retries/backoff on `429/5xx` via `httpx.AsyncClient`.
- **Graph & retrieval bridge**
  - Define a translator that turns `ExtractionResult` payloads into the graph schema (Neo4j) and Qdrant metadata. Capture counts for statistics/figures/tables for the UI. Proposed location: new module under `src/graph/medparse_ingest.py`.
  - When only linking is needed, add a hook in the retrieval pipeline (e.g., `src/retrieval` nodes) to merge returned CUIs into the query expansion logic.
- **UI exposure**
  - Surface Medparse-derived evidence counts in the Gradio interface once the backend stores them. Ensure CORS coverage (`ALLOWED_ORIGINS`) matches the UI origin.
- **Testing**
  - Add contract tests that spin up the FastAPI app with `ENABLE_PIPELINE=false` to validate client wiring.
  - Include regression coverage for the fallback order (UMLS → QuickUMLS → empty) so integration remains predictable.

Until these items land, Medparse will run independently without impacting the current LangGraph flow.

---

## Local Development Workflow
- Start Medparse as described above (port `8099` by default).
- Export `MEDPARSE_URL=http://127.0.0.1:8099` (and `MEDPARSE_API_KEY` if required) before launching IP_Assist_Lite via `run.sh` or `app.py` so the future client picks up the configuration.
- Use `ENABLE_PIPELINE=false` for fast feedback during UI work, then re-enable for end-to-end validation.
- For batch ingestion, run Medparse scripts (`python scripts/process_one.py ...`) and drop the JSON into the graph ingest path used by IP_Assist_Lite.

---

## Operational Checklist
- [ ] Medparse `uvicorn` process healthy on the expected host/port.
- [ ] `.env` in Medparse configured with `QUICKUMLS_PATH` and `API_KEY` (if protecting the service).
- [ ] IP_Assist_Lite environment exposes `MEDPARSE_URL` (and `MEDPARSE_API_KEY` when applicable).
- [ ] `/link` verified for UMLS + QuickUMLS fallback behavior.
- [ ] `/extract` validated against a sample PDF; confirm figures/tables/statistics arrive.
- [ ] Optional: run `pytest -q` inside `medparse-docling` to exercise QuickUMLS fallback tests.

---

## Troubleshooting
- **401 Invalid API key**: Ensure IP_Assist_Lite sends `X-API-Key` matching Medparse `API_KEY`.
- **413 Payload Too Large**: Increase `MAX_UPLOAD_MB` or compress the PDF before retrying.
- **415 Unsupported Media Type**: The upload must be `application/pdf`.
- **Empty `/link` results**: Confirm `UMLS_API_KEY` or `QUICKUMLS_PATH` availability; inspect Medparse logs.
- **CORS errors**: Update `ALLOWED_ORIGINS` so the Gradio host is permitted.
- **QuickUMLS ImportError (`imp` module)**: Re-run the sidecar from Python 3.11; QuickUMLS fails on Python 3.12+.

---

## Change Log Highlights
- Added explicit repo paths and local workflow notes for `medparse-docling` (2025-09).
- Documented `X-API-Key` authentication expectations and recommended IP_Assist_Lite client responsibilities.
- Clarified remaining integration work (HTTP client, graph ingest, UI wiring) so future changes have a checklist.

---

## Contact Points
- **Medparse maintainers**: See `/home/rjm/projects/ip_knowledge/medparse/medparse-docling/README.md` for up-to-date contacts.
- **IP_Assist_Lite maintainers**: Refer to `README.md` in this repo.

For integration issues, reproduce against the Medparse HTTP boundary first (via `curl` or the FastAPI docs) before tracing through LangGraph components.
