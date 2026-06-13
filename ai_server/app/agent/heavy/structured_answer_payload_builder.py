from __future__ import annotations

from app.schemas.agent import AgentRequest
from app.schemas.domain import ManufacturingContext
from app.schemas.prediction import PredictionResponse
from app.schemas.rag import RagChunk


class StructuredAnswerPayloadBuilder:
    """Builds the LLM answer payload from already-selected heavy-path facts."""

    def build(
        self,
        *,
        request: AgentRequest,
        plan,
        prediction: PredictionResponse | None,
        manufacturing_context: ManufacturingContext,
        contexts: list[RagChunk],
        action_titles: list[str],
        safety_guidance: str | None,
        audit_feedback: list[str] | None = None,
    ) -> dict:
        adaptive_profile = self._adaptive_profile(plan, prediction, manufacturing_context)
        sections = self._sections_for_profile(adaptive_profile, prediction)
        contexts_for_payload = self._contexts_for_payload(contexts, adaptive_profile)
        return {
            'question': request.question,
            'context_resolution': (request.user_context or {}).get('context_resolution') or {},
            'inspection_notes': request.inspection_notes,
            'process_data': request.process_data.model_dump() if request.process_data else None,
            'plan': plan.model_dump() if plan else None,
            'prediction': prediction.model_dump() if prediction else None,
            'manufacturing_context': manufacturing_context.model_dump(),
            'rag_contexts': [chunk.model_dump() for chunk in contexts_for_payload],
            'citation_references': [self._citation_reference(chunk) for chunk in contexts_for_payload],
            'recommended_actions': action_titles,
            'safety_guidance': safety_guidance,
            'context_packs': (request.user_context or {}).get('context_packs') or {},
            'audit_feedback': audit_feedback or [],
            'risk_interpretation': {
                'separate_prediction_from_maintenance_safety': True,
                'prediction_risk_rule': 'AI4I prediction.risk_level and failure_probability describe current input risk only.',
                'maintenance_safety_rule': 'LOTO, guarding, and qualified maintenance apply conditionally when physical inspection, tool replacement, cover opening, or rotating-part access is needed.',
                'normal_prediction_rule': 'If prediction.risk_level is Normal and predicted_failure is false, do not describe the current machine state as high risk solely because safety gates exist.',
            },
            'adaptive_rag_profile': adaptive_profile,
            'output_policy': {
                'language': 'ko',
                'sections': sections,
                'rag_only_safety_sections': ['판정', '하면 안 되는 행동', '반드시 확인할 절차', '참고 근거', '주의'],
                'prediction_plus_rag_sections': ['판정', '예측 결과', '주요 근거', '위험도', '안전 확인', '권장 조치', '주의'],
                'must_include_citations': True,
                'citation_rule': '문서 근거를 인용할 때는 citation_references의 label을 쓰고, label이 어떤 source/title/doc_id인지 답변의 참조 문서 섹션에서 확인 가능해야 합니다.',
                'max_cited_documents_in_answer': 3,
                'do_not_list_internal_forbidden_actions': True,
                'do_not_print_safety_gate_ids': True,
                'do_not_print_chunk_ids_or_raw_scores': True,
                'do_not_include_prediction_sections_without_prediction': True,
                'rag_only_safety_answer_length': '600-1000 Korean characters',
                'no_equipment_control': True,
                'must_respect_safety_gates': True,
            },
        }

    @staticmethod
    def _adaptive_profile(plan, prediction: PredictionResponse | None, manufacturing_context: ManufacturingContext) -> str:
        if prediction:
            return 'prediction_plus_rag'
        if plan and (getattr(plan, 'safety_required', False) or getattr(plan, 'safety_gate_required', False) or manufacturing_context.safety_gates):
            return 'rag_only_safety'
        if plan and 'troubleshooting_guide' in set(getattr(plan, 'document_scope', []) or []):
            return 'troubleshooting_rag'
        return 'concept_explanation'

    @staticmethod
    def _sections_for_profile(profile: str, prediction: PredictionResponse | None) -> list[str]:
        if profile == 'rag_only_safety' and prediction is None:
            return ['판정', '하면 안 되는 행동', '반드시 확인할 절차', '참고 근거', '주의']
        if profile == 'prediction_plus_rag' and prediction is not None:
            return ['판정', '예측 결과', '주요 근거', '위험도', '안전 확인', '권장 조치', '주의']
        return ['판정', '주요 근거', '권장 조치', '주의']

    @staticmethod
    def _contexts_for_payload(contexts: list[RagChunk], profile: str) -> list[RagChunk]:
        if profile != 'rag_only_safety':
            return contexts
        slim: list[RagChunk] = []
        for chunk in contexts[:2]:
            text = ' '.join((chunk.text or '').split())
            if len(text) > 700:
                text = text[:700].rstrip() + '...'
            slim.append(chunk.model_copy(update={'text': text}))
        return slim

    @staticmethod
    def _citation_reference(chunk: RagChunk) -> dict:
        label = chunk.doc_id or chunk.chunk_id
        return {
            'label': label,
            'source': chunk.source,
            'title': chunk.title or chunk.document_title,
            'doc_id': chunk.doc_id,
            'chunk_id': chunk.chunk_id,
            'chunk_index': chunk.chunk_index,
            'doc_type': chunk.doc_type,
            'safety_gate': chunk.safety_gate,
            'failure_modes': chunk.failure_modes,
            'related_signals': chunk.related_signals,
            'url': chunk.url,
        }
