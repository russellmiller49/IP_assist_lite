# Graph & Vector Persistence Runbook

This guide covers the Neo4j and Qdrant graph stores that receive enriched Medparse payloads during ingestion.

## Environment Variables

| Variable | Description | Default |
| --- | --- | --- |
| `APP_USE_NEO4J` | Enable Neo4j persistence | `true` |
| `APP_USE_QDRANT` | Enable Qdrant persistence | `true` |
| `NEO4J_URI` | Bolt URI for Neo4j | `neo4j://localhost:7687` |
| `NEO4J_USER` / `NEO4J_PASSWORD` | Auth credentials | `neo4j` / *(empty)* |
| `NEO4J_DATABASE` | Target database name | `neo4j` |
| `QDRANT_URL` | Qdrant endpoint | `http://localhost:6333` |
| `QDRANT_API_KEY` | API key (when secured) | *(empty)* |
| `QDRANT_COLLECTION_PREFIX` | Prefix for evidence collections | `ip` |

The prefix generates three collections automatically:

- `{prefix}_sections`
- `{prefix}_recs`
- `{prefix}_figtabs`

## Quick Start

```bash
# Start the local Neo4j + Qdrant stack
make graph-up

# Backfill seed documents (PDF + JSON) into both stores
make backfill

# Validate the stores
make graph-validate
```

### `make graph-up`

Runs `docker compose -f docker/docker-compose.yml up -d` which starts:

- **Neo4j 5.x** on ports `7474` (HTTP) and `7687` (Bolt)
- **Qdrant 1.8.x** on ports `6333` (HTTP) and `6334` (gRPC)

### `make backfill`

Invokes `python -m src.jobs.backfill_graph` with the default seed directories (`data/seed`). The command:

1. Extracts Medparse JSON for PDFs (via the configured transport).
2. Normalises payloads using `src/normalize/merge_enrichments.py`.
3. Upserts into Neo4j (`src/graph/sinks/neo4j_sink.py`) and Qdrant (`src/graph/sinks/qdrant_sink.py`).
4. Writes `data/seed/backfill_report.csv` summarising node/edge counts per document.

### `make graph-validate`

Runs both validators:

- `python -m src.graph.validate_neo4j` – ensures the expected node labels exist and that at least one `(:Recommendation)-[:SUPPORTED_BY]->(:Stat)` edge is present.
- `python -m src.graph.validate_qdrant` – checks that the three Qdrant collections exist and contain >0 vectors.

## Data Model

**Nodes**

- `(:Document {doc_id, title, year})`
- `(:Section {id, title, page_start, page_end})`
- `(:Recommendation {id, text, grade})`
- `(:Stat {id, stat_type, value, ci_low, ci_high, p_value, unit})`
- `(:Figure {id, caption, page, bbox})`
- `(:Table {id, caption, page, bbox})`

**Relationships**

- `(Document)-[:HAS_SECTION]->(Section)`
- `(Document)-[:HAS_RECOMMENDATION]->(Recommendation)`
- `(Document)-[:HAS_STAT]->(Stat)`
- `(Document)-[:HAS_FIGURE]->(Figure)`
- `(Document)-[:HAS_TABLE]->(Table)`
- `(Recommendation)-[:SUPPORTED_BY]->(Stat)`
- `(Figure)-[:ILLUSTRATES]->(Recommendation)` *(optional)*
- `(Table)-[:SUMMARIZES]->(Stat)` *(optional)*

## Handy Cypher Queries

```cypher
// Top supported recommendations
MATCH (r:Recommendation)-[s:SUPPORTED_BY]->(:Stat)
RETURN r.text AS recommendation, count(s) AS support
ORDER BY support DESC
LIMIT 10;

// Evidence per document
MATCH (d:Document)-[:HAS_RECOMMENDATION]->(r)
OPTIONAL MATCH (r)-[:SUPPORTED_BY]->(s:Stat)
RETURN d.doc_id, d.title, r.text, count(s) AS stats;
```

## Qdrant Inspection

```python
from qdrant_client import QdrantClient
client = QdrantClient("http://localhost:6333")
for name in ["ip_sections", "ip_recs", "ip_figtabs"]:
    info = client.get_collection(name)
    print(name, info.vectors_count)
    sample = client.scroll(name, limit=1)[0]
    print(sample.payload)
```

## Troubleshooting

- **`neo4j` package missing** – install with `pip install neo4j` or set `APP_USE_NEO4J=false` when running without the graph.
- **Qdrant HTTP 404** – ensure the container is up (`docker ps`), or adjust `QDRANT_URL` when running remotely.
- **Evidence panel empty** – confirm `APP_SHOW_EVIDENCE=true` and rerun the ingestion so Neo4j/Qdrant receive fresh data.
