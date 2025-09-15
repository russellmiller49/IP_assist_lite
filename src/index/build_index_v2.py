from __future__ import annotations
import os
from qdrant_client import QdrantClient
from qdrant_client.http.models import VectorParams, Distance

# ADAPT these imports to your repo
from src.index.corpus import iter_chunks      # yields (doc_id, chunk_id, text, page, source)
from src.index.embedders import medcpt_doc_encode

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLL_NAME   = os.getenv("QDRANT_COLLECTION_V2", "ip_docs_v2")
DIM         = int(os.getenv("EMB_DIM", "768"))

client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

def recreate_collection():
    client.recreate_collection(
        collection_name=COLL_NAME,
        vectors={
            "chunks":    VectorParams(size=DIM, distance=Distance.COSINE),
            "summaries": VectorParams(size=DIM, distance=Distance.COSINE),
            "quotes":    VectorParams(size=DIM, distance=Distance.COSINE),
        },
        on_disk_payload=True
    )

def upsert_points():
    batch, pid = [], 0
    for doc_id, chunk_id, text, page, source in iter_chunks():
        summary_text = text.split(". ")[0].strip()[:300]
        quote_text   = summary_text
        vec_chunk    = medcpt_doc_encode(text).tolist()
        vec_summary  = medcpt_doc_encode(summary_text).tolist()
        vec_quote    = medcpt_doc_encode(quote_text).tolist()
        batch.append({
            "id": pid,
            "vector": {"chunks": vec_chunk, "summaries": vec_summary, "quotes": vec_quote},
            "payload":{
                "doc_id": doc_id, "chunk_id": chunk_id, "text": text,
                "summary_text": summary_text, "quote_text": quote_text,
                "page": page, "source": source
            }
        }); pid += 1
        if len(batch) >= 128:
            client.upsert(collection_name=COLL_NAME, points=batch); batch.clear()
    if batch: client.upsert(collection_name=COLL_NAME, points=batch)

if __name__ == "__main__":
    recreate_collection(); upsert_points()