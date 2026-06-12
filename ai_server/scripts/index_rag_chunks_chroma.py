from __future__ import annotations

import argparse
import json
from typing import Any

from rag_pipeline_utils import RAG_CHUNKS_PATH, RAG_DATA_DIR, env_value, read_jsonl


def _openai_client():
    try:
        from openai import OpenAI
    except Exception as exc:
        raise SystemExit('openai is not installed. Install requirements before OpenAI embedding indexing.') from exc

    kwargs: dict[str, Any] = {'api_key': env_value('OPENAI_API_KEY')}
    base_url = env_value('OPENAI_BASE_URL')
    org_id = env_value('OPENAI_ORG_ID')
    project_id = env_value('OPENAI_PROJECT_ID')
    if base_url:
        kwargs['base_url'] = base_url
    if org_id:
        kwargs['organization'] = org_id
    if project_id:
        kwargs['project'] = project_id
    if not kwargs['api_key']:
        raise SystemExit('OPENAI_API_KEY is missing. Add it to .env before OpenAI embedding indexing.')
    return OpenAI(**kwargs)


def _batches(rows: list[Any], batch_size: int) -> list[list[Any]]:
    return [rows[index:index + batch_size] for index in range(0, len(rows), batch_size)]


def _embed_openai(texts: list[str], *, model: str, batch_size: int) -> list[list[float]]:
    client = _openai_client()
    embeddings: list[list[float]] = []
    for batch in _batches(texts, batch_size):
        response = client.embeddings.create(model=model, input=batch)
        ordered = sorted(response.data, key=lambda item: item.index)
        embeddings.extend([item.embedding for item in ordered])
    return embeddings


def _metadata_value(value: Any) -> str | int | float | bool | None:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return ','.join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _metadata(row: dict[str, Any]) -> dict[str, str | int | float | bool]:
    metadata: dict[str, str | int | float | bool] = {}
    for key, value in row.items():
        if key == 'text':
            continue
        normalized = _metadata_value(value)
        if normalized is not None:
            metadata[key] = normalized
    return metadata


def index_chunks(
    *,
    persist_dir: str | None = None,
    collection_name: str = 'manufacturing_rag',
    embedding_provider: str = 'openai',
    embedding_model: str | None = None,
    batch_size: int = 64,
    reset: bool = False,
) -> dict[str, Any]:
    try:
        import chromadb
    except Exception as exc:
        raise SystemExit('chromadb is not installed. Install requirements before Chroma indexing.') from exc

    chunks = read_jsonl(RAG_CHUNKS_PATH)
    directory = persist_dir or env_value('CHROMA_PERSIST_DIR') or str(RAG_DATA_DIR / 'vector_db' / 'chroma')
    collection_name = collection_name or env_value('CHROMA_COLLECTION', 'manufacturing_rag')
    client = chromadb.PersistentClient(path=directory)
    if reset:
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass
    collection = client.get_or_create_collection(name=collection_name)
    ids = [row['chunk_id'] for row in chunks]
    documents = [row['text'] for row in chunks]
    metadatas = [_metadata(row) for row in chunks]
    if ids:
        if embedding_provider == 'openai':
            model = embedding_model or env_value('RAG_EMBEDDING_MODEL', 'text-embedding-3-small')
            embeddings = _embed_openai(documents, model=model, batch_size=batch_size)
            for id_batch, doc_batch, meta_batch, embedding_batch in zip(
                _batches(ids, batch_size),
                _batches(documents, batch_size),
                _batches(metadatas, batch_size),
                _batches(embeddings, batch_size),
            ):
                collection.upsert(ids=id_batch, documents=doc_batch, metadatas=meta_batch, embeddings=embedding_batch)
        elif embedding_provider == 'chroma-default':
            for id_batch, doc_batch, meta_batch in zip(_batches(ids, batch_size), _batches(documents, batch_size), _batches(metadatas, batch_size)):
                collection.upsert(ids=id_batch, documents=doc_batch, metadatas=meta_batch)
        else:
            raise SystemExit(f'Unsupported embedding provider: {embedding_provider}')
    return {
        'indexed_chunks': len(ids),
        'collection': collection_name,
        'persist_dir': directory,
        'embedding_provider': embedding_provider,
        'embedding_model': embedding_model or env_value('RAG_EMBEDDING_MODEL', 'text-embedding-3-small'),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Index rag_chunks.jsonl into Chroma.')
    parser.add_argument('--persist-dir')
    parser.add_argument('--collection', default=env_value('CHROMA_COLLECTION', 'manufacturing_rag'))
    parser.add_argument('--embedding-provider', choices=['openai', 'chroma-default'], default=env_value('RAG_EMBEDDING_PROVIDER', 'openai'))
    parser.add_argument('--embedding-model', default=env_value('RAG_EMBEDDING_MODEL', 'text-embedding-3-small'))
    parser.add_argument('--batch-size', type=int, default=64)
    parser.add_argument('--reset', action='store_true', help='Delete and recreate the Chroma collection before indexing.')
    args = parser.parse_args()
    summary = index_chunks(
        persist_dir=args.persist_dir,
        collection_name=args.collection,
        embedding_provider=args.embedding_provider,
        embedding_model=args.embedding_model,
        batch_size=args.batch_size,
        reset=args.reset,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
