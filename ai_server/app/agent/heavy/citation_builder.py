from __future__ import annotations

from typing import Any

from app.agent.heavy.rag_schemas import EvidenceGrade
from app.schemas.rag import RagChunk


class CitationBuilder:
    """Builds citation metadata from already-filtered and graded evidence."""

    def build(self, chunks: list[RagChunk], grade: EvidenceGrade | None = None) -> list[dict[str, Any]]:
        if grade is not None and not grade.usable:
            return []
        citations: list[dict[str, Any]] = []
        for chunk in chunks or []:
            label = chunk.doc_id or chunk.chunk_id
            title = chunk.title or chunk.document_title
            citations.append({
                'label': label,
                'source': chunk.source,
                'document': chunk.document_title,
                'title': title,
                'doc_id': chunk.doc_id,
                'chunk_id': chunk.chunk_id,
                'chunk_index': chunk.chunk_index,
                'doc_type': chunk.doc_type,
                'safety_gate': chunk.safety_gate,
                'failure_modes': chunk.failure_modes,
                'project_priority': chunk.project_priority,
                'retrieval_scope': chunk.retrieval_scope,
                'section': chunk.section,
                'url': chunk.url,
                'score': chunk.score,
                'distance': chunk.distance,
                'display_text': self._display_text(label=label, source=chunk.source, title=title, doc_type=chunk.doc_type),
                'reason': 'graded_evidence' if grade else 'retrieved_evidence',
            })
        return citations

    @staticmethod
    def _display_text(*, label: str, source: str, title: str, doc_type: str | None) -> str:
        parts = [f'[{label}]', source, title]
        if doc_type:
            parts.append(doc_type)
        return ' · '.join(str(part) for part in parts if part)
