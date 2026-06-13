from __future__ import annotations

import json

from app.schemas.agent import AgentRequest
from app.schemas.prediction import EvidenceFeature, FailureModeScore, PredictionResponse, ProcessData
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

    service = RagService(chunks_path=chunks_path, use_chroma=False)

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

    assert {gate.gate_id for gate in context.safety_gates} >= {'loto_if_physical_maintenance', 'rotating_parts_guard_check'}

    result = SafetyValidationService.validate_answer('일반적인 점검을 수행하세요.', context)

    assert not result.passed
    assert any('필수 안전 게이트 누락' in error for error in result.errors)


def test_safety_validator_accepts_natural_language_gate_coverage_without_gate_id():
    req = AgentRequest(
        question='Haas 밀 장비에서 스핀들 이상음, 진동, 경보가 발생했을 때 우선 확인해야 할 항목을 알려줘.',
    )
    context = DomainKnowledgeService().build_context(req, prediction=None)

    assert {gate.gate_id for gate in context.safety_gates} >= {'rotating_parts_guard_check'}

    answer = (
        '회전부에는 운전 중 접근하지 말고, 커버 개방이나 물리 점검이 필요하면 '
        '먼저 설비 정지와 전원 차단 상태를 확인하세요. '
        '가드와 인터록 같은 방호장치 상태, 비상정지 장치 위치와 동작 가능 상태를 확인한 뒤 '
        '담당자가 스핀들 경보, 이상음, 진동 이력을 점검해야 합니다.'
    )

    result = SafetyValidationService.validate_answer(answer, context)

    assert result.passed
    assert 'rotating_parts_guard_check' not in answer


def test_rag_only_safety_context_does_not_use_ai4i_or_critical_risk():
    req = AgentRequest(
        question='드릴기 작업 전에 공작물 고정 상태, 방호덮개, 비상정지장치를 어떻게 확인해야 하는지 알려줘.',
    )
    context = DomainKnowledgeService().build_context(req, prediction=None)

    assert context.risk_assessment.prediction_risk is not None
    assert context.risk_assessment.prediction_risk.level == 'not_applicable'
    assert context.risk_assessment.safety_work_risk is not None
    assert context.risk_assessment.safety_work_risk.level == 'conditional'
    assert context.risk_assessment.overall_priority != 'critical'
    assert all('AI4I 예측' not in note for note in context.audit_notes)
    assert any('문서 근거 기반 안전 점검 보조' in note for note in context.audit_notes)


def test_safety_validator_allows_negated_control_disclaimer():
    answer = '본 답변은 설비를 자동으로 정지할 수 없습니다. 담당자 점검 권고만 제공합니다.'

    result = SafetyValidationService.validate_answer(answer, None)

    assert result.passed


def test_normal_prediction_keeps_maintenance_safety_separate_from_overall_risk():
    req = AgentRequest(
        question='공구 교체 전 확인해야 할 항목을 알려줘',
        process_data=ProcessData(
            type='M',
            air_temperature_k=300.2,
            process_temperature_k=309.0,
            rotational_speed_rpm=1480,
            torque_nm=34.0,
            tool_wear_min=235,
        ),
    )
    prediction = PredictionResponse(
        failure_probability=0.1154,
        predicted_failure=False,
        risk_level='Normal',
        failure_modes=[
            FailureModeScore(code='TWF', name='공구 마모 고장', probability=0.1989, predicted=False),
            FailureModeScore(code='OSF', name='과부하 고장', probability=0.01, predicted=False),
        ],
        predicted_modes=[],
        evidence_features=[
            EvidenceFeature(feature='Tool wear', direction='high', value=235, tag='tool_wear_high', reason='공구 마모 시간이 높습니다.'),
        ],
        recommended_actions=['공구 마모 상태 점검'],
        model_source='test',
        disclaimer='test',
    )

    context = DomainKnowledgeService().build_context(req, prediction)

    assert context.risk_assessment.quality.level == 'low'
    assert context.risk_assessment.safety.level == 'high'
    assert context.risk_assessment.overall_priority == 'medium'
