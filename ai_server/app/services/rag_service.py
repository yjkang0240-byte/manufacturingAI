from __future__ import annotations
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any
from app.config import CHUNKS_PATH, RAG_MIN_NORMALIZED_SCORE
from app.errors import RagIndexUnavailableError
from app.schemas.rag import RagChunk
from app.services.chroma_retriever import ChromaRetriever

TOKEN_RE = re.compile(r'[가-힣A-Za-z0-9_+#.-]+')

class RagService:
    """Runtime RAG service.

    Chroma is the runtime evidence store. The local JSONL lexical index is used
    only when Chroma is explicitly disabled for local tests or development.
    """
    def __init__(
        self,
        chunks_path: Path | None = None,
        chroma_retriever: ChromaRetriever | None = None,
        use_chroma: bool = True,
    ):
        self.chunks_path = chunks_path or CHUNKS_PATH
        self.chroma_retriever = chroma_retriever or ChromaRetriever()
        self.use_chroma = use_chroma
        self.chunks: list[dict] = []
        self._doc_tokens: list[Counter[str]] = []
        self._doc_lengths: list[int] = []
        self._avg_doc_length = 1.0
        self._idf: dict[str, float] = {}
        if not self.use_chroma:
            self.load()

    def load(self) -> bool:
        if not self.chunks_path.exists():
            return False
        try:
            self.chunks = [json.loads(x) for x in self.chunks_path.read_text(encoding='utf-8').splitlines() if x.strip()]
        except (OSError, json.JSONDecodeError) as exc:
            raise RagIndexUnavailableError('RAG index cannot be loaded') from exc
        self._build_memory_index()
        return True

    def build(self, chunks: list[dict]) -> None:
        self.chunks_path.parent.mkdir(parents=True, exist_ok=True)
        self.chunks = chunks
        self.chunks_path.write_text('\n'.join(json.dumps(c, ensure_ascii=False) for c in chunks), encoding='utf-8')
        self._build_memory_index()

    def _build_memory_index(self) -> None:
        self._doc_tokens = [Counter(self._tokenize(' '.join([c.get('text',''), c.get('document_title',''), c.get('source',''), c.get('doc_type','') or '', c.get('section','') or '', str(c.get('metadata') or {})]))) for c in self.chunks]
        self._doc_lengths = [sum(toks.values()) for toks in self._doc_tokens]
        self._avg_doc_length = sum(self._doc_lengths) / max(len(self._doc_lengths), 1)
        df: Counter[str] = Counter()
        for toks in self._doc_tokens:
            df.update(toks.keys())
        n = max(len(self._doc_tokens), 1)
        self._idf = {t: math.log((n - freq + 0.5) / (freq + 0.5) + 1) for t, freq in df.items()}

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [t.lower() for t in TOKEN_RE.findall(text or '') if len(t.strip()) >= 1]

    def search(self, query: str, top_k: int = 5, filters: dict | None = None) -> list[RagChunk]:
        if self.use_chroma:
            result = self.chroma_retriever.retrieve(query, top_k=top_k, filters=filters)
            return result.chunks
        return self._search_jsonl(query, top_k=top_k, filters=filters)

    def search_with_diagnostics(self, query: str, top_k: int = 5, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.use_chroma:
            result = self.chroma_retriever.retrieve(query, top_k=top_k, filters=filters)
            diagnostics = result.diagnostics.model_dump()
            diagnostics['backend'] = 'error' if result.diagnostics.error else 'chroma'
            return {'chunks': result.chunks, 'diagnostics': diagnostics}
        chunks = self._search_jsonl(query, top_k=top_k, filters=filters)
        return {
            'chunks': chunks,
            'diagnostics': {
                'requested_top_k': top_k,
                'returned_chunks': len(chunks),
                'backend': 'jsonl_dev',
                'error': None,
            },
        }

    def corpus_health(self) -> dict[str, Any]:
        if not self.use_chroma:
            return {'backend': 'jsonl_dev', 'chroma_count': None, 'error': None}
        count, error = self.chroma_retriever.collection_count()
        return {'backend': 'chroma' if error is None else 'error', 'chroma_count': count, 'error': error}

    def metadata_search(self, terms: list[str], top_k: int = 5, *, allow_restricted: bool = False) -> dict[str, Any]:
        if not self.use_chroma:
            return {
                'chunks': [],
                'diagnostics': {
                    'requested_top_k': top_k,
                    'returned_chunks': 0,
                    'backend': 'jsonl_dev',
                    'error': None,
                },
            }
        result = self.chroma_retriever.metadata_search(terms, top_k=top_k, allow_restricted=allow_restricted)
        diagnostics = result.diagnostics.model_dump()
        diagnostics['backend'] = 'metadata_error' if result.diagnostics.error else 'chroma_metadata'
        return {'chunks': result.chunks, 'diagnostics': diagnostics}

    def _search_jsonl(self, query: str, top_k: int = 5, filters: dict | None = None) -> list[RagChunk]:
        if not self.chunks:
            if not self.load():
                raise RagIndexUnavailableError('RAG JSONL dev index is unavailable')
        filters = filters or {}
        q_tokens = Counter(self._tokenize(query))
        if not q_tokens:
            q_tokens = Counter({'maintenance': 1, 'safety': 1})
        ranked: list[tuple[int, float]] = []
        k1 = 1.5
        b = 0.75
        for idx, doc_tokens in enumerate(self._doc_tokens):
            raw = self.chunks[idx]
            if filters and any(raw.get(k) != v for k, v in filters.items() if v is not None):
                continue
            score = 0.0
            for token, qtf in q_tokens.items():
                if token in doc_tokens:
                    tf = doc_tokens[token]
                    doc_len = self._doc_lengths[idx] or 1
                    denom = tf + k1 * (1 - b + b * doc_len / max(self._avg_doc_length, 1.0))
                    score += self._idf.get(token, 0.0) * ((tf * (k1 + 1)) / denom) * (1 + math.log(qtf))
            # Small source/title boost for exact source or doc_type mentions.
            lower_blob = ' '.join([raw.get('source',''), raw.get('doc_type','') or '', raw.get('section','') or '']).lower()
            for token in q_tokens:
                if token in lower_blob:
                    score += 0.5
            if score > 0:
                ranked.append((idx, score))
        ranked.sort(key=lambda x: x[1], reverse=True)
        if not ranked:
            return []
        max_score = max([s for _, s in ranked] or [1.0]) or 1.0
        results: list[RagChunk] = []
        for idx, raw_score in ranked[:top_k]:
            normalized = float(raw_score / max_score)
            if normalized < RAG_MIN_NORMALIZED_SCORE:
                continue
            raw = dict(self.chunks[idx])
            raw.setdefault('document_title', raw.get('title') or raw.get('doc_id') or 'Untitled document')
            raw['score'] = round(normalized, 4)
            results.append(RagChunk(**raw))
        return results
