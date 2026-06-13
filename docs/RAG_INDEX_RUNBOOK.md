# RAG Chroma Index Rebuild

Use this when a new environment has no local Chroma index, or when Chroma count
differs from `ai_server/data/processed/rag_chunks.jsonl`.

## Prerequisites

- `ai_server/data/processed/rag_chunks.jsonl` exists.
- `OPENAI_API_KEY` is set.
- Embedding model: `text-embedding-3-small`.
- Collection: `manufacturing_rag`.
- Persist dir: `ai_server/data/vector_db/chroma`.

The vector DB is git ignored, so each environment must rebuild it locally.
This command does not download sources, regenerate documents, or re-chunk the
corpus. It indexes the existing JSONL chunks into Chroma.

## Rebuild

```bash
cd ai_server
.venv/bin/python scripts/index_rag_chunks_chroma.py --reset
```

Expected summary:

```text
indexed_chunks: 727
collection: manufacturing_rag
embedding_model: text-embedding-3-small
```

## Count Check

```bash
cd ai_server
.venv/bin/python -c "import json, chromadb; from pathlib import Path; from app.config import CHROMA_COLLECTION, CHROMA_PERSIST_DIR; rows=[json.loads(x) for x in Path('data/processed/rag_chunks.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]; c=chromadb.PersistentClient(path=str(CHROMA_PERSIST_DIR)).get_collection(CHROMA_COLLECTION); print(len(rows), c.count())"
```

Expected:

```text
727 727
```

## Smoke Check

```bash
cd ai_server
.venv/bin/python -c "from app.services.rag_service import RagService; r=RagService().search_with_diagnostics('Haas spindle load tool wear troubleshooting torque', top_k=5); print(r['diagnostics'].get('backend')); [print(c.chunk_id, c.source, c.doc_type) for c in r['chunks']]"
```

Expected:

```text
chroma
haas_mill_spindle_troubleshooting_* Haas troubleshooting
```
