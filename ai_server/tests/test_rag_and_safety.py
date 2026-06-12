from __future__ import annotations

import json

from app.schemas import AgentRequest, ProcessData
from app.services.domain_service import DomainKnowledgeService
from app.services.rag_service import RagService
from app.services.safety_validation_service import SafetyValidationService


def test_rag_returns_empty_when_no_query_terms_match(tmp_path):
    chunks_path = tmp_path / 'chunks.jsonl'
    chunks = [
        {
            'chunk_id': 'c1',
            'source': 'manual',
            'document_title': 'Coolant pump maintenance',
            'text': 'coolant pump filter replacement',
        }
    ]
    chunks_path.write_text('\n'.join(json.dumps(c) for c in chunks), encoding='utf-8')

    service = RagService(chunks_path=chunks_path)

    assert service.search('unrelated aerospace welding', top_k=3) == []


def test_safety_validator_requires_triggered_gate_content():
    req = AgentRequest(
        question='토크가 높고 공구 마모가 큰데 정비 전 안전 절차를 알려줘',
        process_data=ProcessData(
            type='L',
            air_temperature_k=302.1,
            process_temperature_k=311.3,
            rotational_speed_rpm=1380,
            torque_nm=58.2,
            tool_wear_min=210,
        ),
    )
    context = DomainKnowledgeService().build_context(req, prediction=None)

    result = SafetyValidationService.validate_answer('일반적인 점검을 수행하세요.', context)

    assert not result.passed
    assert any('필수 안전 게이트 누락' in error for error in result.errors)
