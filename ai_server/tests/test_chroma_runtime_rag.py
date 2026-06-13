from __future__ import annotations

import json
import sys
import types

from app.agent.heavy.citation_builder import CitationBuilder
from app.agent.heavy.evidence_filter import EvidenceFilter
from app.agent.heavy.evidence_grader import EvidenceGrader
from app.services.chroma_retriever import ChromaRetriever
from app.services.rag_service import RagService


class FakeCollection:
    def __init__(self, rows):
        self.rows = rows
        self.last_query = None

    def query(self, **kwargs):
        self.last_query = kwargs
        return {
            'ids': [[row['id'] for row in self.rows]],
            'documents': [[row['text'] for row in self.rows]],
            'metadatas': [[row['metadata'] for row in self.rows]],
            'distances': [[row.get('distance', 0.1) for row in self.rows]],
        }


def install_fake_chroma(monkeypatch, collection: FakeCollection | None = None, error: Exception | None = None):
    class FakeClient:
        def __init__(self, path):
            self.path = path

        def get_collection(self, name):
            if error:
                raise error
            return collection

    module = types.SimpleNamespace(PersistentClient=FakeClient)
    monkeypatch.setitem(sys.modules, 'chromadb', module)


def retriever(monkeypatch, rows):
    collection = FakeCollection(rows)
    install_fake_chroma(monkeypatch, collection)
    instance = ChromaRetriever(persist_dir='/tmp/chroma-test', collection_name='manufacturing_rag')
    monkeypatch.setattr(instance, '_embed', lambda text: [0.1, 0.2, 0.3])
    return instance, collection


def row(chunk_id: str, *, source: str, title: str, text: str, **metadata):
    return {
        'id': chunk_id,
        'text': text,
        'metadata': {
            'chunk_id': chunk_id,
            'source': source,
            'title': title,
            'doc_id': metadata.pop('doc_id', title.lower().replace(' ', '_')),
            'chunk_index': metadata.pop('chunk_index', 0),
            **metadata,
        },
        'distance': metadata.pop('distance', 0.1) if 'distance' in metadata else 0.1,
    }


def test_chroma_retriever_returns_loto_for_maintenance_safety_question(monkeypatch):
    instance, collection = retriever(monkeypatch, [
        row(
            'osha_loto_0001',
            source='OSHA',
            title='OSHA LOTO',
            text='lockout tagout maintenance energy control before servicing machines',
            safety_gate='loto',
            failure_modes='OSF,TWF',
            project_priority='high',
            retrieval_scope='default',
            doc_type='safety_standard',
        )
    ])

    result = instance.retrieve('maintenance safety lockout tagout', top_k=3)

    assert result.diagnostics.error is None
    assert result.chunks[0].safety_gate == 'loto'
    assert result.chunks[0].source == 'OSHA'
    assert 'query_embeddings' in collection.last_query


def test_chroma_retriever_returns_machine_guarding_for_rotating_part_question(monkeypatch):
    instance, _ = retriever(monkeypatch, [
        row(
            'osha_guarding_0001',
            source='OSHA',
            title='Machine Guarding',
            text='machine guarding point of operation rotating parts nip points',
            safety_gate='machine_guarding',
            failure_modes='OSF,TWF',
            project_priority='high',
            retrieval_scope='default',
            doc_type='safety_standard',
        )
    ])

    result = instance.retrieve('rotating part guard safety', top_k=3)

    assert result.chunks[0].safety_gate == 'machine_guarding'
    assert result.chunks[0].project_priority == 'high'


def test_chroma_retriever_returns_kosha_maintenance_for_tool_wear_question(monkeypatch):
    instance, _ = retriever(monkeypatch, [
        row(
            'kosha_maintenance_0001',
            source='KOSHA',
            title='공작기계 정비 점검 지침',
            text='공구 마모 증가 시 정비 점검과 방호장치 확인이 필요하다',
            safety_gate='maintenance_check',
            failure_modes='TWF,OSF',
            related_signals='tool_wear_min,torque_nm',
            project_priority='high',
            retrieval_scope='default',
            doc_type='korean_maintenance_guidance',
        )
    ])

    result = instance.retrieve('공구 마모 점검 정비', top_k=3)

    assert result.chunks[0].source == 'KOSHA'
    assert result.chunks[0].safety_gate == 'maintenance_check'
    assert 'TWF' in result.chunks[0].failure_modes


def test_restricted_docs_are_not_default_retrieval_results(monkeypatch):
    instance, _ = retriever(monkeypatch, [
        row(
            'restricted_0001',
            source='KOSHA',
            title='Restricted',
            text='정비 점검',
            safety_gate='maintenance_check',
            failure_modes='TWF',
            project_priority='high',
            retrieval_scope='restricted',
        ),
        row(
            'default_0001',
            source='OSHA',
            title='Default LOTO',
            text='maintenance safety lockout tagout',
            safety_gate='loto',
            failure_modes='TWF',
            project_priority='medium',
            retrieval_scope='default',
        ),
    ])
    result = instance.retrieve('정비 점검 safety', top_k=5)

    filtered = EvidenceFilter().filter(result.chunks, filters={'preferred_safety_gates': ['maintenance_check', 'loto']})

    assert [chunk.chunk_id for chunk in filtered] == ['default_0001']


def test_citation_builder_uses_chroma_metadata(monkeypatch):
    instance, _ = retriever(monkeypatch, [
        row(
            'kosha_tool_0001',
            source='KOSHA',
            title='공구 마모 정비',
            text='공구 마모 점검 정비',
            doc_id='kosha_tool',
            chunk_index=4,
            safety_gate='maintenance_check',
            failure_modes='TWF',
            project_priority='high',
            retrieval_scope='default',
            doc_type='korean_maintenance_guidance',
        )
    ])
    chunks = EvidenceFilter().filter(instance.retrieve('공구 마모 정비', top_k=1).chunks, filters={'preferred_failure_modes': ['TWF']})
    grade = EvidenceGrader().grade('공구 마모 정비', chunks)

    citation = CitationBuilder().build(chunks, grade)[0]

    assert citation['label'] == 'kosha_tool'
    assert citation['source'] == 'KOSHA'
    assert citation['doc_id'] == 'kosha_tool'
    assert citation['chunk_index'] == 4
    assert citation['safety_gate'] == 'maintenance_check'
    assert citation['failure_modes'] == 'TWF'
    assert citation['score'] is not None
    assert '공구 마모 정비' in citation['display_text']


def test_rag_runtime_degrades_gracefully_when_chroma_missing(monkeypatch, tmp_path):
    install_fake_chroma(monkeypatch, error=ValueError('collection not found'))
    instance = ChromaRetriever(persist_dir='/tmp/missing-chroma', collection_name='missing')
    monkeypatch.setattr(instance, '_embed', lambda text: [0.1])

    result = instance.retrieve('maintenance safety', top_k=3)

    assert result.chunks == []
    assert result.diagnostics.returned_chunks == 0
    assert 'collection not found' in (result.diagnostics.error or '')

    chunks_path = tmp_path / 'chunks.jsonl'
    chunks_path.write_text(json.dumps({
        'chunk_id': 'jsonl_match',
        'source': 'manual',
        'document_title': 'JSONL match',
        'text': 'maintenance safety lockout',
    }) + '\n', encoding='utf-8')
    service = RagService(chunks_path=chunks_path, chroma_retriever=instance)
    diagnostics = service.search_with_diagnostics('maintenance safety', top_k=3)

    assert diagnostics['chunks'] == []
    assert diagnostics['diagnostics']['backend'] == 'error'
