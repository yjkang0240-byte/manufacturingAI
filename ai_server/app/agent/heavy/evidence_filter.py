from __future__ import annotations

from app.schemas.rag import RagChunk


class EvidenceFilter:
    """Filters retrieval output without assigning final relevance grades."""

    BLOCKED_DEFAULT_SCOPES = {'restricted', 'emergency_only'}
    PRIORITY_WEIGHT = {'high': 30, 'medium': 15, 'low': 0}

    def filter(self, chunks: list[RagChunk], filters: dict | None = None) -> list[RagChunk]:
        filters = filters or {}
        preferred_modes = self._as_set(filters.get('preferred_failure_modes'))
        preferred_gates = self._as_set(filters.get('preferred_safety_gates'))
        required_terms = self._as_set(filters.get('required_context_terms'))
        allow_restricted = bool(filters.get('include_restricted'))
        allow_emergency = bool(filters.get('include_emergency_only'))
        seen: set[str] = set()
        filtered: list[RagChunk] = []
        for chunk in chunks or []:
            if not chunk.text.strip():
                continue
            scope = (chunk.retrieval_scope or '').strip().lower()
            if scope == 'emergency_only' and not allow_emergency:
                continue
            if scope == 'restricted' and not allow_restricted:
                continue
            if not self._contextually_allowed(chunk, required_terms=required_terms):
                continue
            key = chunk.chunk_id or f'{chunk.source}:{chunk.document_title}:{chunk.text[:80]}'
            if key in seen:
                continue
            seen.add(key)
            filtered.append(chunk)
        return sorted(
            filtered,
            key=lambda chunk: self._rank_score(chunk, preferred_modes=preferred_modes, preferred_gates=preferred_gates),
            reverse=True,
        )

    def _rank_score(self, chunk: RagChunk, *, preferred_modes: set[str], preferred_gates: set[str]) -> float:
        score = float(chunk.score or 0.0)
        priority = (chunk.project_priority or '').strip().lower()
        score += self.PRIORITY_WEIGHT.get(priority, 5)
        modes = self._as_set(chunk.failure_modes)
        if preferred_modes and modes.intersection(preferred_modes):
            score += 25
        gate = (chunk.safety_gate or '').strip()
        if preferred_gates and gate in preferred_gates:
            score += 20
        if (chunk.retrieval_scope or '').strip().lower() == 'default':
            score += 5
        return score

    def _contextually_allowed(self, chunk: RagChunk, *, required_terms: set[str]) -> bool:
        if not required_terms:
            return True
        blob = ' '.join([
            chunk.document_title or '',
            chunk.title or '',
            chunk.doc_type or '',
            chunk.safety_gate or '',
            (chunk.text or '')[:1200],
        ]).lower().replace('_', ' ')
        return any(term.lower().replace('_', ' ') in blob for term in required_terms)

    @staticmethod
    def _as_set(value: object) -> set[str]:
        if value is None:
            return set()
        if isinstance(value, str):
            return {item.strip() for item in value.replace(';', ',').split(',') if item.strip()}
        if isinstance(value, (list, tuple, set)):
            return {str(item).strip() for item in value if str(item).strip()}
        return {str(value).strip()} if str(value).strip() else set()
