from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.config import (
    CHROMA_COLLECTION,
    CHROMA_PERSIST_DIR,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_ORG_ID,
    OPENAI_PROJECT_ID,
    RAG_EMBEDDING_MODEL,
    RAG_EMBEDDING_PROVIDER,
)
from app.schemas.rag import RagChunk
from app.services.local_embedding import hash_text_embeddings


class ChromaRetrievalDiagnostics(BaseModel):
    query: str
    requested_top_k: int
    returned_chunks: int = 0
    collection: str = CHROMA_COLLECTION
    persist_dir: str = str(CHROMA_PERSIST_DIR)
    embedding_provider: str = RAG_EMBEDDING_PROVIDER
    error: str | None = None


class ChromaRetrievalResult(BaseModel):
    chunks: list[RagChunk] = Field(default_factory=list)
    diagnostics: ChromaRetrievalDiagnostics


class ChromaRetriever:
    """Runtime Chroma retriever for manufacturing RAG evidence."""

    def __init__(
        self,
        *,
        persist_dir: Path | str = CHROMA_PERSIST_DIR,
        collection_name: str = CHROMA_COLLECTION,
        embedding_provider: str = RAG_EMBEDDING_PROVIDER,
        embedding_model: str = RAG_EMBEDDING_MODEL,
    ):
        self.persist_dir = str(persist_dir)
        self.collection_name = collection_name
        self.embedding_provider = embedding_provider
        self.embedding_model = embedding_model

    def retrieve(self, query: str, *, top_k: int, filters: dict[str, Any] | None = None) -> ChromaRetrievalResult:
        diagnostics = ChromaRetrievalDiagnostics(
            query=query,
            requested_top_k=top_k,
            collection=self.collection_name,
            persist_dir=self.persist_dir,
            embedding_provider=self.embedding_provider,
        )
        try:
            collection = self._collection()
            query_kwargs: dict[str, Any] = {
                'query_texts': [query],
                'n_results': max(top_k, 1),
                'include': ['documents', 'metadatas', 'distances'],
            }
            if self.embedding_provider == 'openai':
                query_kwargs.pop('query_texts')
                query_kwargs['query_embeddings'] = [self._embed(query)]
            elif self.embedding_provider == 'local-hash':
                query_kwargs.pop('query_texts')
                query_kwargs['query_embeddings'] = hash_text_embeddings([query])
            if filters:
                where = self._where(filters)
                if where:
                    query_kwargs['where'] = where
            response = collection.query(**query_kwargs)
            chunks = self._chunks(response)
            diagnostics.returned_chunks = len(chunks)
            return ChromaRetrievalResult(chunks=chunks, diagnostics=diagnostics)
        except Exception as exc:
            diagnostics.error = f'{type(exc).__name__}: {exc}'
            return ChromaRetrievalResult(chunks=[], diagnostics=diagnostics)

    def _collection(self):
        try:
            import chromadb
        except Exception as exc:
            raise RuntimeError('chromadb is not installed') from exc
        client = chromadb.PersistentClient(path=self.persist_dir)
        return client.get_collection(self.collection_name)

    def collection_count(self) -> tuple[int | None, str | None]:
        try:
            return int(self._collection().count()), None
        except Exception as exc:
            return None, f'{type(exc).__name__}: {exc}'

    def metadata_search(self, terms: list[str], *, top_k: int, allow_restricted: bool = False) -> ChromaRetrievalResult:
        query = ' '.join(terms)
        diagnostics = ChromaRetrievalDiagnostics(
            query=query,
            requested_top_k=top_k,
            collection=self.collection_name,
            persist_dir=self.persist_dir,
            embedding_provider='metadata',
        )
        try:
            response = self._collection().get(include=['documents', 'metadatas'])
            ranked: list[tuple[float, RagChunk]] = []
            normalized_terms = {self._normalize_term(term) for term in terms if self._normalize_term(term)}
            metadata_rows = response.get('metadatas') or []
            for index, chunk in enumerate(self._chunks_from_get(response)):
                scope = (chunk.retrieval_scope or '').strip().lower()
                if scope == 'emergency_only':
                    continue
                if scope == 'restricted' and not allow_restricted:
                    continue
                raw_meta = metadata_rows[index] if index < len(metadata_rows) and isinstance(metadata_rows[index], dict) else {}
                blob = self._metadata_blob(chunk, raw_meta)
                hits = sum(1 for term in normalized_terms if term in blob)
                if hits < 2:
                    continue
                priority = {'high': 3, 'medium': 2, 'low': 1}.get((chunk.project_priority or '').strip().lower(), 0)
                ranked.append((hits * 10 + priority, chunk))
            ranked.sort(key=lambda item: item[0], reverse=True)
            chunks = [chunk.model_copy(update={'score': round(score / 100.0, 4)}) for score, chunk in ranked[:top_k]]
            diagnostics.returned_chunks = len(chunks)
            return ChromaRetrievalResult(chunks=chunks, diagnostics=diagnostics)
        except Exception as exc:
            diagnostics.error = f'{type(exc).__name__}: {exc}'
            return ChromaRetrievalResult(chunks=[], diagnostics=diagnostics)

    def _embed(self, text: str) -> list[float]:
        if self.embedding_provider != 'openai':
            raise RuntimeError(f'unsupported embedding provider: {self.embedding_provider}')
        try:
            from openai import OpenAI
        except Exception as exc:
            raise RuntimeError('openai is not installed') from exc
        if not OPENAI_API_KEY:
            raise RuntimeError('OPENAI_API_KEY is missing')
        kwargs: dict[str, Any] = {'api_key': OPENAI_API_KEY}
        if OPENAI_BASE_URL:
            kwargs['base_url'] = OPENAI_BASE_URL
        if OPENAI_ORG_ID:
            kwargs['organization'] = OPENAI_ORG_ID
        if OPENAI_PROJECT_ID:
            kwargs['project'] = OPENAI_PROJECT_ID
        response = OpenAI(**kwargs).embeddings.create(model=self.embedding_model, input=[text])
        return response.data[0].embedding

    @staticmethod
    def _where(filters: dict[str, Any]) -> dict[str, Any]:
        supported: dict[str, Any] = {}
        internal = {'preferred_failure_modes', 'preferred_safety_gates', 'include_restricted', 'include_emergency_only'}
        for key, value in filters.items():
            if key in internal:
                continue
            if value is None or isinstance(value, (list, tuple, set, dict)):
                continue
            supported[key] = value
        if len(supported) == 1:
            key, value = next(iter(supported.items()))
            return {key: {'$eq': value}}
        if supported:
            return {'$and': [{key: {'$eq': value}} for key, value in supported.items()]}
        return {}

    @staticmethod
    def _chunks(response: dict[str, Any]) -> list[RagChunk]:
        ids = (response.get('ids') or [[]])[0] or []
        documents = (response.get('documents') or [[]])[0] or []
        metadatas = (response.get('metadatas') or [[]])[0] or []
        distances = (response.get('distances') or [[]])[0] or []
        chunks: list[RagChunk] = []
        for index, chunk_id in enumerate(ids):
            metadata = dict(metadatas[index] or {}) if index < len(metadatas) else {}
            text = documents[index] if index < len(documents) else metadata.get('text', '')
            distance = float(distances[index]) if index < len(distances) and distances[index] is not None else None
            score = None if distance is None else round(1.0 / (1.0 + max(distance, 0.0)), 4)
            title = metadata.get('title') or metadata.get('document_title') or metadata.get('techGdlnNm') or 'Untitled document'
            chunks.append(RagChunk(
                chunk_id=str(metadata.get('chunk_id') or chunk_id),
                source=str(metadata.get('source') or 'unknown'),
                document_title=str(title),
                title=str(title),
                text=str(text or ''),
                doc_id=ChromaRetriever._optional_str(metadata.get('doc_id')),
                chunk_index=ChromaRetriever._optional_int(metadata.get('chunk_index')),
                doc_type=ChromaRetriever._optional_str(metadata.get('doc_type')),
                equipment_type=ChromaRetriever._optional_str(metadata.get('equipment_type')),
                safety_gate=ChromaRetriever._optional_str(metadata.get('safety_gate')),
                failure_modes=metadata.get('failure_modes'),
                related_signals=metadata.get('related_signals'),
                project_priority=ChromaRetriever._optional_str(metadata.get('project_priority')),
                retrieval_scope=ChromaRetriever._optional_str(metadata.get('retrieval_scope')),
                section=ChromaRetriever._optional_str(metadata.get('section')),
                language=ChromaRetriever._optional_str(metadata.get('language')),
                url=ChromaRetriever._optional_str(metadata.get('url') or metadata.get('fileDownlUrl')),
                score=score,
                distance=distance,
            ))
        return chunks

    @staticmethod
    def _chunks_from_get(response: dict[str, Any]) -> list[RagChunk]:
        ids = response.get('ids') or []
        documents = response.get('documents') or []
        metadatas = response.get('metadatas') or []
        query_like = {
            'ids': [ids],
            'documents': [documents],
            'metadatas': [metadatas],
            'distances': [[]],
        }
        return ChromaRetriever._chunks(query_like)

    @staticmethod
    def _metadata_blob(chunk: RagChunk, metadata: dict[str, Any]) -> str:
        values = [
            chunk.document_title,
            chunk.title or '',
            chunk.doc_id or '',
            chunk.doc_type or '',
            chunk.safety_gate or '',
            chunk.source or '',
            str(metadata.get('use_case') or ''),
        ]
        return ChromaRetriever._normalize_term(' '.join(values))

    @staticmethod
    def _normalize_term(value: Any) -> str:
        return str(value or '').lower().replace('_', ' ').replace('-', ' ').strip()

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None or value == '':
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
