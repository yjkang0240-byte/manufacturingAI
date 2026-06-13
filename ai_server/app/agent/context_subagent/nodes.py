from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from pydantic import ValidationError

from app.agent.context import AnswerMemory, ContextCompressor, ContextPackBuilder, ContextResolution, ContextResolver, ContextValidator
from app.schemas.agent import AgentRequest, AgentSendRequest
from app.schemas.prediction import ProcessData
from app.services.context_service import ContextService
from app.services.user_service import UserService

from .state import ContextState


@dataclass(frozen=True)
class ContextDeps:
    user_service: UserService
    context_service: ContextService
    context_resolver: ContextResolver
    context_pack_builder: ContextPackBuilder
    context_compressor: ContextCompressor
    context_validator: ContextValidator


AI4I_FEATURES = {
    'type': 'Type',
    'air_temperature_k': 'Air temperature',
    'process_temperature_k': 'Process temperature',
    'rotational_speed_rpm': 'Rotational speed',
    'torque_nm': 'Torque',
    'tool_wear_min': 'Tool wear',
}


@dataclass(frozen=True)
class ExtractedFeature:
    value: str | float | int | None
    unit: str | None = None
    ambiguous: bool = False
    invalid: bool = False


def load_request_context(state: ContextState, deps: ContextDeps) -> ContextState:
    req = AgentSendRequest.model_validate(state['send_request'])
    req.session_id = state['session_id']
    ai4i_status = _inspect_ai4i_features(req.message, mode=req.mode, provided_process_data=req.process_data)
    if not req.process_data and ai4i_status.get('process_data'):
        req = req.model_copy(update={'process_data': ProcessData(**ai4i_status['process_data'])})
    deps.user_service.validate(req.user_id)
    deps.user_service.upsert_session(
        user_id=req.user_id,
        session_id=req.session_id,
        title=req.message[:80] if req.message else None,
    )
    base_request = _to_agent_request(req, session_id=req.session_id)
    user_context = deps.context_service.build(user_id=req.user_id, session_id=req.session_id, request=base_request)
    user_context['ai4i_feature_status'] = _public_ai4i_status(ai4i_status)
    return {
        'send_request': req.model_dump(),
        'request': base_request.model_dump(),
        'user_context': user_context,
        'turn_process_data': req.process_data.model_dump() if req.process_data else None,
        'ai4i_feature_status': ai4i_status,
    }


def resolve_conversation_context(state: ContextState, deps: ContextDeps) -> ContextState:
    req = AgentSendRequest.model_validate(state['send_request'])
    last_memory = _answer_memory(state.get('last_answer_memory'))
    effective_process_data = req.process_data
    previous_turn_process_data = None
    reference_previous = False
    session_last_process_data = state.get('session_last_process_data')
    if not effective_process_data and session_last_process_data and _references_previous_process_data(req.message):
        previous_turn_process_data = session_last_process_data
        effective_process_data = ProcessData(**session_last_process_data)
        reference_previous = True

    process_policy = {
        'current_process_data_available': bool(state.get('turn_process_data')),
        'session_last_process_data_available': bool(session_last_process_data),
        'previous_turn_process_data_used': reference_previous,
        'rule': 'Previous process_data is used only for explicit current-value/current-condition follow-up questions.',
    }
    ai4i_status = dict(state.get('ai4i_feature_status') or {})
    if reference_previous and effective_process_data:
        ai4i_status = _complete_ai4i_status(effective_process_data, prediction_intent=True)
        ai4i_status['source'] = 'previous_turn_process_data'
    process_policy['ai4i_feature_status'] = _public_ai4i_status(ai4i_status)
    compressed = deps.context_compressor.compress(
        messages=list(state.get('recent_turns') or []) + [{'role': 'user', 'content': req.message}],
        previous_rolling_summary=state.get('rolling_summary') or '',
    )
    resolution = deps.context_resolver.resolve(
        current_user_message=req.message,
        last_answer_memory=last_memory,
        recent_turns=compressed.recent_turns,
        rolling_summary=compressed.rolling_summary,
    )
    return {
        'compressed_context': compressed.model_dump(),
        'context_resolution': resolution.model_dump(),
        'effective_process_data': effective_process_data.model_dump() if effective_process_data else None,
        'previous_turn_process_data': previous_turn_process_data,
        'process_data_reference_policy': process_policy,
        'ai4i_feature_status': ai4i_status,
    }


def build_context_pack(state: ContextState, deps: ContextDeps) -> ContextState:
    req = AgentSendRequest.model_validate(state['send_request'])
    session_id = state['session_id']
    resolution = ContextResolution.model_validate(state['context_resolution'])
    last_memory = _answer_memory(state.get('last_answer_memory'))
    packs = deps.context_pack_builder.build(
        current_user_message=req.message,
        context_resolution=resolution,
        compressed_context=state.get('compressed_context') or {},
        last_answer_memory=last_memory,
        recent_turn_routes=state.get('recent_turn_routes') or [],
        process_data_policy=state.get('process_data_reference_policy') or {},
    )
    turn_context = {
        'original_question': req.message,
        'standalone_query': resolution.standalone_query,
        'is_followup': resolution.is_followup,
        'followup_type': resolution.followup_type,
        'followup_target': resolution.followup_target,
        'confidence': resolution.confidence,
        'reason': resolution.reason,
    }
    user_context = dict(state.get('user_context') or {})
    user_context['turn_context'] = turn_context
    user_context['process_data_reference_policy'] = state.get('process_data_reference_policy') or {}
    user_context['ai4i_feature_status'] = _public_ai4i_status(state.get('ai4i_feature_status') or {})
    user_context['last_answer_memory'] = last_memory.model_dump() if last_memory else {}
    user_context['context_resolution'] = resolution.model_dump()
    user_context['context_packs'] = packs.model_dump()
    user_context['compressed_context'] = state.get('compressed_context') or {}
    request = _to_agent_request(
        req,
        session_id=session_id,
        user_context=user_context,
        question=resolution.standalone_query,
        process_data=ProcessData(**state['effective_process_data']) if state.get('effective_process_data') else None,
    )
    return {
        'request': request.model_dump(),
        'user_context': user_context,
        'turn_context': turn_context,
        'context_packs': packs.model_dump(),
    }


def validate_context(state: ContextState, deps: ContextDeps) -> ContextState:
    warnings = deps.context_validator.validate(
        context_resolution=state.get('context_resolution') or {},
        context_packs=state.get('context_packs') or {},
    )
    user_context = dict(state.get('user_context') or {})
    user_context['context_validation_warnings'] = warnings
    all_warnings = list(dict.fromkeys((state.get('warnings') or []) + warnings))
    return {
        'context_validation_warnings': warnings,
        'user_context': user_context,
        'warnings': all_warnings,
    }


def emit_context_output(state: ContextState, deps: ContextDeps) -> ContextState:
    trace = {
        'followup': bool((state.get('context_resolution') or {}).get('is_followup')),
        'followup_type': (state.get('context_resolution') or {}).get('followup_type'),
        'previous_process_data_used': bool((state.get('process_data_reference_policy') or {}).get('previous_turn_process_data_used')),
        'ai4i_status': (state.get('ai4i_feature_status') or {}).get('status'),
        'ai4i_prediction_intent': bool((state.get('ai4i_feature_status') or {}).get('prediction_intent')),
    }
    output = {
        'send_request': state['send_request'],
        'request': state['request'],
        'user_context': state.get('user_context') or {},
        'turn_context': state.get('turn_context') or {},
        'context_resolution': state.get('context_resolution') or {},
        'context_packs': state.get('context_packs') or {},
        'compressed_context': state.get('compressed_context') or {},
        'rolling_summary': (state.get('compressed_context') or {}).get('rolling_summary') or '',
        'context_validation_warnings': state.get('context_validation_warnings') or [],
        'warnings': state.get('warnings') or [],
        'turn_process_data': state.get('turn_process_data'),
        'previous_turn_process_data': state.get('previous_turn_process_data'),
        'process_data_reference_policy': state.get('process_data_reference_policy') or {},
        'ai4i_feature_status': _public_ai4i_status(state.get('ai4i_feature_status') or {}),
        'trace': trace,
    }
    return {'trace': trace, 'output': output}


def _to_agent_request(
    req: AgentSendRequest,
    *,
    session_id: str,
    user_context: dict[str, Any] | None = None,
    question: str | None = None,
    process_data: ProcessData | None = None,
) -> AgentRequest:
    return AgentRequest(
        user_id=req.user_id,
        question=req.message if question is None else question,
        process_data=req.process_data if process_data is None else process_data,
        inspection_notes=req.inspection_notes,
        top_k=req.top_k,
        session_id=session_id,
        mode=req.mode,
        llm_model=req.llm_model,
        user_context=user_context,
    )


def _answer_memory(value: Any) -> AnswerMemory | None:
    if isinstance(value, AnswerMemory):
        return value
    if isinstance(value, dict) and value.get('short_summary'):
        return AnswerMemory.model_validate(value)
    return None


def _references_previous_process_data(*questions: str) -> bool:
    text = ' '.join(question or '' for question in questions).lower().replace(' ', '')
    reference_terms = [
        '방금데이터',
        '방금그조건',
        '그조건',
        '이조건',
        '이데이터',
        '그데이터',
        '현재값',
        '이수치',
        '이값',
        '이토크값',
        '토크값위험',
        '위험해',
        '위험도',
        '고장확률',
        '가능성',
    ]
    concept_only_terms = ['뭐야', '무엇', '정의', '설명', '장점', '단점', '한계', '원리']
    if any(term in text for term in concept_only_terms) and not any(term in text for term in ['값', '조건', '데이터', '위험', '확률', '가능성']):
        return False
    return any(term in text for term in reference_terms)


def _inspect_ai4i_features(
    message: str,
    *,
    mode: str = 'auto',
    provided_process_data: ProcessData | None = None,
) -> dict[str, Any]:
    if provided_process_data:
        status = _complete_ai4i_status(provided_process_data, prediction_intent=True)
        status['source'] = 'request.process_data'
        return status

    text = message or ''
    parsed = _parse_ai4i_features(text)
    parsed_values = {AI4I_FEATURES[name]: feature.value for name, feature in parsed.items() if feature.value is not None}
    missing = [display for name, display in AI4I_FEATURES.items() if name not in parsed or parsed[name].value is None]
    ambiguous = [AI4I_FEATURES[name] for name, feature in parsed.items() if feature.ambiguous]
    invalid = [AI4I_FEATURES[name] for name, feature in parsed.items() if feature.invalid]
    prediction_intent = _has_ai4i_prediction_intent(text, mode=mode, parsed_any=bool(parsed_values))

    if not missing and not ambiguous and not invalid:
        try:
            process_data = ProcessData(
                type=str(parsed['type'].value),
                air_temperature_k=float(parsed['air_temperature_k'].value),
                process_temperature_k=float(parsed['process_temperature_k'].value),
                rotational_speed_rpm=int(round(float(parsed['rotational_speed_rpm'].value))),
                torque_nm=float(parsed['torque_nm'].value),
                tool_wear_min=int(round(float(parsed['tool_wear_min'].value))),
            )
        except (TypeError, ValueError, ValidationError):
            return _ai4i_status(
                status='invalid',
                prediction_intent=prediction_intent,
                skip_reason='invalid_ai4i_features' if prediction_intent else None,
                parsed=parsed_values,
                missing=[],
                ambiguous=[],
                invalid=list(AI4I_FEATURES.values()),
            )
        return _complete_ai4i_status(process_data, prediction_intent=prediction_intent or True)

    reason = None
    status = 'not_requested'
    if prediction_intent:
        if invalid:
            status = 'invalid'
            reason = 'invalid_ai4i_features'
        elif ambiguous:
            status = 'ambiguous'
            reason = 'ambiguous_ai4i_features'
        else:
            status = 'missing'
            reason = 'missing_ai4i_features'

    return _ai4i_status(
        status=status,
        prediction_intent=prediction_intent,
        skip_reason=reason,
        parsed=parsed_values,
        missing=missing if prediction_intent else [],
        ambiguous=ambiguous if prediction_intent else [],
        invalid=invalid if prediction_intent else [],
    )


def _complete_ai4i_status(process_data: ProcessData, *, prediction_intent: bool) -> dict[str, Any]:
    parsed = {
        'Type': process_data.type,
        'Air temperature': process_data.air_temperature_k,
        'Process temperature': process_data.process_temperature_k,
        'Rotational speed': process_data.rotational_speed_rpm,
        'Torque': process_data.torque_nm,
        'Tool wear': process_data.tool_wear_min,
    }
    return _ai4i_status(
        status='complete',
        prediction_intent=prediction_intent,
        skip_reason=None,
        parsed=parsed,
        missing=[],
        ambiguous=[],
        invalid=[],
        process_data=process_data.model_dump(),
    )


def _ai4i_status(
    *,
    status: str,
    prediction_intent: bool,
    skip_reason: str | None,
    parsed: dict[str, Any],
    missing: list[str],
    ambiguous: list[str],
    invalid: list[str],
    process_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        'status': status,
        'prediction_intent': prediction_intent,
        'clarification_required': bool(prediction_intent and status in {'missing', 'ambiguous', 'invalid'}),
        'prediction_skip_reason': skip_reason,
        'missing_features': missing,
        'ambiguous_features': ambiguous,
        'invalid_features': invalid,
        'parsed_ai4i_features': parsed,
        'process_data': process_data,
        'source': 'message',
    }


def _public_ai4i_status(status: dict[str, Any]) -> dict[str, Any]:
    return {
        'status': status.get('status') or 'not_requested',
        'prediction_intent': bool(status.get('prediction_intent')),
        'clarification_required': bool(status.get('clarification_required')),
        'prediction_skip_reason': status.get('prediction_skip_reason'),
        'missing_features': list(status.get('missing_features') or []),
        'ambiguous_features': list(status.get('ambiguous_features') or []),
        'invalid_features': list(status.get('invalid_features') or []),
        'parsed_ai4i_features': dict(status.get('parsed_ai4i_features') or {}),
        'source': status.get('source') or 'message',
    }


def _parse_ai4i_features(text: str) -> dict[str, ExtractedFeature]:
    return {
        'type': _extract_type(text),
        'air_temperature_k': _extract_temperature(text, _label_pattern([
            r'air\s*temperature',
            r'air[_\s-]*temp',
            r'air[_\s-]*temperature',
            r'공기\s*온도',
            r'공기온도',
            r'대기\s*온도',
            r'대기온도',
        ]), field='air_temperature_k'),
        'process_temperature_k': _extract_temperature(text, _label_pattern([
            r'process\s*temperature',
            r'process[_\s-]*temp',
            r'process[_\s-]*temperature',
            r'공정\s*온도',
            r'공정온도',
        ]), field='process_temperature_k'),
        'rotational_speed_rpm': _extract_numeric(text, _label_pattern([
            r'rotational\s*speed',
            r'rotational[_\s-]*speed',
            r'rpm',
            r'회전\s*속도',
            r'회전속도',
            r'회전수',
        ]), field='rotational_speed_rpm'),
        'torque_nm': _extract_numeric(text, _label_pattern([
            r'torque',
            r'토크',
            r'부하\s*토크',
            r'부하토크',
        ]), field='torque_nm'),
        'tool_wear_min': _extract_numeric(text, _label_pattern([
            r'tool\s*wear',
            r'tool[_\s-]*wear',
            r'공구\s*마모\s*시간',
            r'공구마모시간',
            r'공구\s*마모',
            r'공구마모',
        ]), field='tool_wear_min'),
    }


def _label_pattern(labels: list[str]) -> str:
    return r'(?:' + '|'.join(labels) + r')'


def _extract_type(text: str) -> ExtractedFeature:
    label = _label_pattern([r'type', r'제품\s*유형', r'제품유형', r'장비\s*유형', r'장비유형'])
    match = re.search(rf'{label}\s*(?:\[[^\]]+\])?\s*(?:[:=]|은|는|이|가)?\s*([A-Za-z])\b', text, re.I)
    if not match:
        return ExtractedFeature(None)
    value = match.group(1).upper()
    return ExtractedFeature(value if value in {'L', 'M', 'H'} else value, invalid=value not in {'L', 'M', 'H'})


def _extract_temperature(text: str, label: str, *, field: str) -> ExtractedFeature:
    raw = _extract_labeled_number(text, label)
    if not raw:
        return ExtractedFeature(None)
    value, unit = raw
    unit_key = _unit_key(unit)
    if unit_key in {'c', 'celsius'}:
        normalized = value + 273.15
    else:
        normalized = value
    ambiguous = unit_key is None and 0 <= value <= 100
    invalid = field == 'air_temperature_k' and not (250 <= normalized <= 350)
    invalid = invalid or (field == 'process_temperature_k' and not (250 <= normalized <= 400))
    return ExtractedFeature(round(normalized, 3), unit=unit, ambiguous=ambiguous, invalid=invalid and not ambiguous)


def _extract_numeric(text: str, label: str, *, field: str) -> ExtractedFeature:
    raw = _extract_labeled_number(text, label)
    if not raw:
        return ExtractedFeature(None)
    value, unit = raw
    if field == 'rotational_speed_rpm':
        invalid = not (1 <= value <= 10000)
        normalized: int | float = int(round(value))
    elif field == 'torque_nm':
        invalid = not (0 <= value <= 1000)
        normalized = round(value, 3)
    else:
        invalid = not (0 <= value <= 100000)
        normalized = int(round(value))
    return ExtractedFeature(normalized, unit=unit, invalid=invalid)


def _extract_labeled_number(text: str, label: str) -> tuple[float, str | None] | None:
    unit = r'(k|kelvin|℃|°c|celsius|c|rpm|n\s*m|nm|min|minute|minutes|분)?'
    pattern = rf'{label}\s*(?:\[[^\]]+\])?\s*(?:[:=]|은|는|이|가)?\s*([-+]?\d+(?:\.\d+)?)\s*{unit}'
    match = re.search(pattern, text, re.I)
    if not match:
        return None
    try:
        value = float(match.group(1))
    except (TypeError, ValueError):
        return None
    return value, match.group(2)


def _unit_key(unit: str | None) -> str | None:
    if not unit:
        return None
    compact = unit.lower().replace(' ', '')
    if compact in {'℃', '°c', 'c', 'celsius'}:
        return 'c'
    if compact in {'k', 'kelvin'}:
        return 'k'
    return compact


def _has_ai4i_prediction_intent(text: str, *, mode: str, parsed_any: bool) -> bool:
    compact = (text or '').lower().replace(' ', '')
    if mode == 'prediction':
        return True
    intent_terms = [
        'ai4i',
        '예측',
        '고장확률',
        '고장가능성',
        '고장모드',
        'failureprobability',
        'prediction',
        'predict',
        'twf',
        'osf',
        'hdf',
        'pwf',
    ]
    if any(term in compact for term in intent_terms):
        return True
    if parsed_any and any(term in compact for term in ['이조건', '현재조건', '위험도', '위험해', '위험한']):
        return True
    return False
