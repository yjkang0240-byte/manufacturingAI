from __future__ import annotations

from dataclasses import dataclass

from app.agent.heavy import RecommendationBuilder, SafetyGateBuilder
from app.schemas.agent import AgentRequest
from app.schemas.domain import ManufacturingContext
from app.schemas.prediction import PredictionResponse
from app.schemas.rag import RagChunk
from app.services.domain_service import DomainKnowledgeService

from .state import SafetyState


@dataclass(frozen=True)
class SafetyDeps:
    domain_service: DomainKnowledgeService
    recommendation_builder: RecommendationBuilder
    safety_gate_builder: SafetyGateBuilder


def build_safety_context(state: SafetyState, deps: SafetyDeps) -> SafetyState:
    request = AgentRequest.model_validate(state['request'])
    prediction = PredictionResponse.model_validate(state['prediction']) if state.get('prediction') else None
    context = ManufacturingContext.model_validate(state['manufacturing_context']) if state.get('manufacturing_context') else None
    if not context:
        doc_count = len([RagChunk.model_validate(item) for item in state.get('retrieved_documents') or []])
        context = deps.domain_service.build_context(request, prediction, doc_count=doc_count)
    return {'manufacturing_context': context.model_dump()}


def apply_safety_policy(state: SafetyState, deps: SafetyDeps) -> SafetyState:
    context = ManufacturingContext.model_validate(state['manufacturing_context'])
    prediction = PredictionResponse.model_validate(state['prediction']) if state.get('prediction') else None
    actions = deps.recommendation_builder.to_action_dicts(deps.recommendation_builder.collect_action_phrases(prediction, context))
    payload = dict(state.get('structured_answer_payload') or {})
    payload['recommended_actions'] = actions
    return {
        'structured_answer_payload': payload,
        'safety_guidance': deps.safety_gate_builder.safety_guidance(context) if context.safety_gates else None,
        'safety_warnings': deps.safety_gate_builder.warnings(context),
    }


def validate_safety_output(state: SafetyState, deps: SafetyDeps) -> SafetyState:
    warnings = list(dict.fromkeys(state.get('safety_warnings') or []))
    return {'safety_warnings': warnings}


def emit_safety_output(state: SafetyState, deps: SafetyDeps) -> SafetyState:
    context = ManufacturingContext.model_validate(state['manufacturing_context'])
    actions = (state.get('structured_answer_payload') or {}).get('recommended_actions') or []
    trace = {
        'safety_gate_count': len(context.safety_gates),
        'recommended_action_count': len(actions),
        'warning_count': len(state.get('safety_warnings') or []),
    }
    output = {
        'manufacturing_context': context.model_dump(),
        'structured_answer_payload': state.get('structured_answer_payload') or {},
        'safety_guidance': state.get('safety_guidance'),
        'safety_warnings': state.get('safety_warnings') or [],
        'trace': trace,
    }
    return {'trace': trace, 'output': output}
