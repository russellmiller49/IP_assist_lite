# Medparse Integration Workspace

Comprehensive guide for developing, running, and validating the combined **IP_Assist_Lite ↔ Medparse** environment. This workspace links two repositories:

- `IP_Assist_Lite` (this repo) – LangGraph/Gradio application focused on interventional pulmonology retrieval and reasoning.
- `medparse-docling` (sidecar repo located at `/home/rjm/projects/ip_knowledge/medparse/medparse-docling`) – FastAPI service that converts PDFs into enriched medical knowledge assets and provides UMLS concept linking.

These projects communicate strictly over HTTP, letting each keep its own Python toolchain while sharing clinical enrichment data.

---

## Contents
- [High-Level Architecture](#high-level-architecture)
- [Key Directories](#key-directories)
- [Services & Ports](#services--ports)
- [Environment Variables](#environment-variables)
- [Quick Start Workflow](#quick-start-workflow)
- [Integration Data Flow](#integration-data-flow)
- [Testing Matrix](#testing-matrix)
- [Operational Playbook](#operational-playbook)
- [Reference Documents](#reference-documents)

---

## High-Level Architecture
- **Medparse sidecar (FastAPI, Python 3.11)**
  - Runs Docling + GROBID + enrichment pipeline.
  - Exposes REST endpoints: `/healthz`, `/version`, `/link`, `/extract`.
  - Optional `X-API-Key` header guard when `API_KEY` is defined in `.env`.
  - Supports stubbed mode by setting `ENABLE_PIPELINE=false` for lightweight contract tests.
- **IP_Assist_Lite application (LangGraph/Gradio, Python 3.12)**
  - Sends link/extract requests to Medparse via the async client in `src/adapters/medparse_client.py`.
  - Consumes extraction payloads to enrich graph/Qdrant stores (see `src/graph/medparse_ingest.py`).
  - Presents concept evidence counts in the Gradio UI once ingestion wiring is complete.

### Separation of Concerns
- **Data processing & linking** live entirely in the Medparse project.
- **Retrieval orchestration & UI** live in IP_Assist_Lite.
- Only the Medparse HTTP interface is assumed stable between repos, keeping upgrade paths independent.

---

## Key Directories
| Path | Description |
| --- | --- |
| `/home/rjm/projects/IP_assist_lite` | Application workspace (this repo). |
| `/home/rjm/projects/IP_assist_lite/src/adapters` | External integration clients (Medparse client lives here). |
| `/home/rjm/projects/IP_assist_lite/src/graph` | Graph utilities, including Medparse ingest helpers. |
| `/home/rjm/projects/IP_assist_lite/docs/medparse_integration` | Workspace documentation (this folder). |
| `/home/rjm/projects/ip_knowledge/medparse/medparse-docling` | Medparse FastAPI service source. |
| `/home/rjm/projects/ip_knowledge/quickumls_data` | Recommended QuickUMLS index location (build once per machine). |

---

## Services & Ports
| Service | Default Port | Notes |
| --- | --- | --- |
| Medparse FastAPI | `8099` | Configurable via `uvicorn` CLI; expects GROBID at `8070` when full pipeline enabled. |
| GROBID (optional) | `8070` | Required for full PDF metadata extraction; skip in stub mode. |
| IP_Assist_Lite Gradio UI | `7860` | Launch via `python app.py` or `./run.sh`. |
| Qdrant | `6333` | Must be running for hybrid retrieval to succeed; can be dockerized or remote. |

---

## Environment Variables

### Medparse `.env`
| Variable | Purpose |
| --- | --- |
| `UMLS_API_KEY` | Enables remote UMLS concept linking (primary path). |
| `NCBI_API_KEY`, `NCBI_EMAIL` | PubMed enrichment for references. |
| `QUICKUMLS_PATH` | Local QuickUMLS index fallback path. |
| `GROBID_URL` | GROBID server endpoint (default `http://localhost:8070`). |
| `API_TITLE`, `API_VERSION` | Metadata for `/version` route. |
| `ALLOWED_ORIGINS` | CORS whitelist (include IP_Assist_Lite host). |
| `MAX_UPLOAD_MB` | Maximum PDF upload size. |
| `ENABLE_PIPELINE` | Toggle full Docling pipeline (`true`) vs. stub mode (`false`). |
| `API_KEY` | Optional secret required in the `X-API-Key` header. |

### IP_Assist_Lite
| Variable | Purpose |
| --- | --- |
| `MEDPARSE_ENABLED` | Toggle Medparse integration (`true` by default). |
| `MEDPARSE_TRANSPORT` | Transport selection: `http` (default) or `mcp`. |
| `MEDPARSE_BASE_URL` | Base URL for the Medparse HTTP sidecar (`http://127.0.0.1:8099`). |
| `MEDPARSE_API_KEY` | Matches Medparse `API_KEY` when the sidecar is locked down. |
| `MEDPARSE_AUTH_HEADER_NAME` | Optional override when the sidecar expects a header other than `X-API-Key` (e.g., `Authorization`). |
| `MEDPARSE_TIMEOUT_SECONDS` | Overall request timeout for Medparse HTTP calls (defaults to `30`). |
| `MEDPARSE_TIMEOUT_CONNECT_SECONDS` | Socket connect timeout (defaults to `10`). |
| `MEDPARSE_TIMEOUT_READ_SECONDS` | Response read timeout (defaults to `600` for large PDFs). |
| `MEDPARSE_TIMEOUT_WRITE_SECONDS` | Upload write timeout (defaults to `600`). |
| `MEDPARSE_TIMEOUT_POOL_SECONDS` | Connection pool acquisition timeout (defaults to `600`). |
| `MEDPARSE_EXTRACT_MODE` | Force Medparse HTTP payload strategy: `auto`, `json`, or `multipart` (defaults to `auto`). |
| `MEDPARSE_MULTIPART_FIELD` | Preferred multipart field name for PDF uploads (defaults to `pdf`). |
| `MEDPARSE_MAX_RETRIES` | Number of retries for `429/5xx` responses (defaults to `3`). |
| `MEDPARSE_RETRY_BACKOFF_SECONDS` | Backoff multiplier between retries (defaults to `1`). |
| `APP_USE_NEO4J` / `APP_USE_QDRANT` | Toggle graph/vector persistence individually. |
| `APP_SHOW_EVIDENCE` | Render the UI evidence panel when `true`. |
| `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` | Connection details for Neo4j evidence graph. |
| `QDRANT_URL`, `QDRANT_API_KEY` | Qdrant endpoint and API key (defaults `http://localhost:6333`, no key). |
| `QDRANT_COLLECTION_PREFIX` | Prefix used for `{prefix}_sections`, `{prefix}_recs`, `{prefix}_figtabs`. |
| `QDRANT_HOST`, `QDRANT_PORT` | Legacy knobs used by the original retriever (defaults `localhost:6333`). |
| `QDRANT_COLLECTION_V2` | Legacy chunks collection name (defaults `ip_docs_v2`). |
| `IP_ASSIST_OFFLINE` | When set, LangGraph retrieval falls back to lightweight encoders. |

Set these variables before launching the corresponding service to avoid runtime configuration errors.

---

## Quick Start Workflow

1. **Provision prerequisites**
   - Python 3.11 for Medparse (conda recommended).
   - Python 3.12 for IP_Assist_Lite.
   - Docker (for GROBID) and QuickUMLS data bundle.

2. **Bootstrap Medparse**
   ```bash
   cd /home/rjm/projects/ip_knowledge/medparse/medparse-docling
   conda create -n medparse-py311 python=3.11 -y
   conda activate medparse-py311
   pip install -r requirements.txt
   cp .env.example .env  # populate values listed above
   docker run -d -p 8070:8070 lfoppiano/grobid:0.8.0  # optional but recommended
   uvicorn api.main:app --reload --port 8099
   ```

3. **Prepare IP_Assist_Lite**
   ```bash
   cd /home/rjm/projects/IP_assist_lite
   conda create -n ip-assist python=3.12 -y
   conda activate ip-assist
   pip install -r requirements.txt
   export MEDPARSE_URL=http://127.0.0.1:8099
   export MEDPARSE_API_KEY=<value-if-set>
   python app.py  # or ./run.sh
   ```

4. **Smoke test integration**
   ```bash
   python - <<'PY'
   import asyncio
   from src.adapters import get_client_from_env

   async def main():
       client = get_client_from_env()
       print("health:", await client.healthcheck())
       print("link sample:", await client.link("massive hemoptysis", top_k=5))

   asyncio.run(main())
   PY
   ```

6. **Ingest seed documents**
   ```bash
   ipa_ingest --path data/seed/*.pdf --doc-type guideline
   ```

5. **Run LangGraph flow**
   - Launch the Gradio UI and issue a query involving clinical terminology.
   - Inspect logs to confirm Medparse link responses are included in retrieval decisions.

## Quick QA

Run a lightweight smoke check without the sidecar by replaying existing JSON payloads and launching the UI:

```bash
make ingest-json JSON="data/extracted/*.json"
make ui
```

Set `APP_USE_NEO4J=false` / `APP_USE_QDRANT=false` if the graph services are not available locally.

## Sidecar QA

When the Medparse FastAPI service is running, use the PDF pipeline end-to-end:

1. Ensure the sidecar is live (for example `uvicorn api.main:app --port 8099`).
2. Export authentication details:
   ```bash
   export MEDPARSE_BASE_URL=http://127.0.0.1:8099
   export MEDPARSE_API_KEY=my-medparse-key
   # Optional when the sidecar expects a bearer token
   export MEDPARSE_AUTH_HEADER_NAME=Authorization
   ```
3. Ingest sample PDFs directly:
   ```bash
   make ingest-pdf PATH="tests/data/pdfs/*.pdf" DOC_TYPE=auto
   ```
4. Launch the UI (`make ui`) and confirm the new documents appear in downstream flows.

## Sidecar protocol variants

Different deployments of the Medparse sidecar expose two `/extract` contracts. IP Assist Lite auto-detects the correct variant unless you override it via `MEDPARSE_EXTRACT_MODE`.

| Variant | Request shape | Notes |
| --- | --- | --- |
| **JSON** (current default) | `POST /extract` with JSON body `{"doc_id": ..., "pdf": "<base64>"}` | Set `MEDPARSE_EXTRACT_MODE=json` to force this mode. |
| **Multipart** (legacy) | `POST /extract` with `files["pdf"]` (or `files["file"]`) containing the binary PDF and form data `doc_id=...` | Set `MEDPARSE_EXTRACT_MODE=multipart` to bypass the JSON attempt. |

Environment setup example:

```bash
export MEDPARSE_TRANSPORT=http
export MEDPARSE_BASE_URL=http://127.0.0.1:8099
export MEDPARSE_API_KEY=my-secret-medparse-key-123   # value only; do not include MEDPARSE_API_KEY=
# export MEDPARSE_AUTH_HEADER_NAME=Authorization     # uncomment if the sidecar expects bearer tokens
# export MEDPARSE_EXTRACT_MODE=json                   # optional override (auto|json|multipart)
```

## Golden Maintenance

- Regenerate the deterministic goldens when the extraction schema changes:
  ```bash
  python scripts/regenerate_goldens.py
  # or as part of pytest
  REGEN_GOLDENS=1 PYTHONPATH=src pytest tests/integration/test_structured_extractors.py
  ```
- Skip the legacy assertions locally (default in CI) with:
  ```bash
  SKIP_LEGACY_GOLDENS=1 PYTHONPATH=src pytest -q
  ```
- Regenerated files are written to `tests/golden/current/`. Review the diff and commit alongside code changes.

---

## 🚀 Automated Startup Scripts

For convenience, automated scripts are available to start all services with proper health checks and error handling.

### **Option 1: Start All Services + Application**
```bash
cd /home/rjm/projects/IP_assist_lite
./scripts/start_full_system.sh
```
This single command:
- Starts Qdrant, GROBID, and Medparse services
- Performs health checks on all services
- Launches the IP Assist Lite application
- Handles conda environment activation automatically

### **Option 2: Start Services Only**
```bash
cd /home/rjm/projects/IP_assist_lite
./scripts/start_extraction_services.sh
```
This starts all extraction services:
- **Qdrant** vector database (port 6333)
- **GROBID** PDF processor (port 8070)
- **Medparse** FastAPI service (port 8099)

Then manually start the application:
```bash
conda activate ip-assist
export MEDPARSE_URL=http://127.0.0.1:8099
python app.py
```

### **Stop All Services**
```bash
cd /home/rjm/projects/IP_assist_lite
./scripts/stop_extraction_services.sh
```

### **Check Service Status**
```bash
cd /home/rjm/projects/IP_assist_lite
./scripts/check_services_status.sh
```
This comprehensive status check will:
- ✅ Verify all service health endpoints
- ✅ Check port availability
- ✅ Show Docker container status
- ✅ Display process information
- ✅ Provide service URLs and troubleshooting guidance

### **Script Features**
- ✅ **Health checks** - Verifies all services are responding
- ✅ **Error handling** - Clear error messages and troubleshooting guidance
- ✅ **Colored output** - Easy-to-read status messages
- ✅ **PID tracking** - Clean shutdown capabilities
- ✅ **Docker management** - Automatic container lifecycle management
- ✅ **Conda integration** - Automatic environment activation

### **Prerequisites for Scripts**
- Docker installed and running
- Conda environments: `medparse-py311` and `ip-assist`
- Required dependencies installed in both environments

### **Quick Reference Commands**
```bash
# Start everything
./scripts/start_full_system.sh

# Check status
./scripts/check_services_status.sh

# Stop everything
./scripts/stop_extraction_services.sh

# Clean up containers
./scripts/cleanup_containers.sh
```

---

### Transport toggle

- `MEDPARSE_TRANSPORT=http` (default) directs calls to the FastAPI sidecar via `src/adapters/medparse_http_adapter.py`.
- `MEDPARSE_TRANSPORT=mcp` routes through the MCP client adapter. Ensure the Medparse MCP server from `ip-mcp-integration` is running locally before enabling.
- Set `MEDPARSE_ENABLED=false` to boot IP Assist Lite without attempting Medparse calls (the retriever will fall back to vector-only search).

---

## Integration Data Flow

1. **Concept Linking**
   - `src/adapters/medparse_client.MedparseClient.link()` sends JSON `{text, top_k}`.
   - Medparse returns curated and fallback UMLS concepts which feed query expansion and evidence panels.

2. **PDF Extraction**
   - `MedparseClient.extract()` uploads PDFs for full processing.
   - `src/graph/medparse_ingest.build_graph_payload()` wraps `src/normalize.merge_enrichments.extract_to_graph_payload()` to produce a unified evidence graph.
   - `jobs/ingest_documents.py` orchestrates extraction, optional raw artifact capture, and dispatch to the sinks.
   - `src/graph/sinks/neo4j_sink.Neo4jSink` upserts documents, sections, recommendations, statistics, figures, and tables into Neo4j.
   - `src/graph/sinks/qdrant_sink.QdrantSink` pushes recommendation evidence and section embeddings into dedicated Qdrant collections for UI drill-down.

3. **Error Handling**
   - `MedparseClient` retries `429/5xx` responses with exponential backoff.
   - `MedparseAuthError` surfaces misconfigured API keys quickly.
   - Fallback behavior is determined by the sidecar (`UMLS_API_KEY` primary → QuickUMLS → empty list).

---

## Testing Matrix
| Scope | Location | Command |
| --- | --- | --- |
| Medparse client contract | `IP_Assist_Lite/tests/test_medparse_client.py` | `pytest tests/test_medparse_client.py` |
| LangGraph flow (core) | `IP_Assist_Lite/tests/` | `pytest -q` |
| Medparse API smoke | `medparse-docling/tests/test_extract_smoke.py` | `pytest -q` (inside medparse env) |
| QuickUMLS fallback | `medparse-docling/tests/test_umls_linker.py` | `pytest tests/test_umls_linker.py` |
| IP Assist Lite evidence ingest | `tests/e2e/test_medparse_end_to_end.py` | `pytest tests/e2e/test_medparse_end_to_end.py` |

Use `ENABLE_PIPELINE=false` in Medparse `.env` when running tests that should avoid the heavy Docling pipeline.

---

## Operational Playbook
- **Startup Order**
  1. QuickUMLS index (ensure filesystem path accessible).
  2. GROBID docker container (if running full pipeline).
  3. Medparse FastAPI (`uvicorn api.main:app ...`).
  4. Qdrant service.
  5. IP_Assist_Lite application (`python app.py`).

- **Automated Startup (Recommended)**
  ```bash
  # Start everything with one command
  ./scripts/start_full_system.sh
  
  # Or start services only
  ./scripts/start_extraction_services.sh
  ```

- **Configuration Changes**
  - Update `MEDPARSE_URL` in IP_Assist_Lite when deploying across hosts.
  - Adjust `ALLOWED_ORIGINS` in Medparse `.env` if the UI is hosted elsewhere.

- **Troubleshooting**
- `401 Unauthorized` → verify `MEDPARSE_API_KEY` matches Medparse `API_KEY`.
- `413` from `/extract` → increase `MAX_UPLOAD_MB` or compress the PDF.
- Empty link results → check `UMLS_API_KEY` validity or QuickUMLS accessibility.
- QuickUMLS ImportError (`imp` module) → ensure Medparse is running under Python 3.11.

## Graph & Vector Stores

Runbook, schema diagrams, and validation commands live in `docs/medparse_integration/GRAPHING.md`. Consult that guide for Neo4j/Qdrant environment variables, the `make graph-up`/`make backfill` workflow, and reusable Cypher/Qdrant queries.

---

## Reference Documents
- `agent.md` – condensed integration guide referenced by QA/agents.
- `docs/medparse_integration/SETUP.md` – step-by-step environment instructions (see companion file).
- Medparse repo docs: `README.md`, `USER_GUIDE.md`, `DOCUMENTATION.md`, `TROUBLESHOOTING.md`.
- IP_Assist_Lite `README.md` – broader product overview and LangGraph architecture.

Keep this README synchronized with code changes impacting integration (client configuration, new endpoints, testing expectations).
