from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from app.schemas.agent import AgentRequest, AgentSendRequest


class ContextState(TypedDict, total=False):
    send_request: dict[str, Any]
    session_id: str
    recent_turns: list[dict[str, Any]]
    rolling_summary: str
    recent_turn_routes: list[dict[str, Any]]
    last_answer_memory: dict[str, Any]
    session_last_process_data: dict[str, Any] | None
    warnings: list[str]
    request: dict[str, Any]
    user_context: dict[str, Any]
    turn_context: dict[str, Any]
    context_resolution: dict[str, Any]
    context_packs: dict[str, Any]
    compressed_context: dict[str, Any]
    context_validation_warnings: list[str]
    turn_process_data: dict[str, Any] | None
    previous_turn_process_data: dict[str, Any] | None
    process_data_reference_policy: dict[str, Any]
    ai4i_feature_status: dict[str, Any]
    effective_process_data: dict[str, Any] | None
    trace: dict[str, Any]
    output: dict[str, Any]


class ContextInput(BaseModel):
    send_request: AgentSendRequest
    session_id: str
    recent_turns: list[dict[str, Any]] = Field(default_factory=list)
    rolling_summary: str = ''
    recent_turn_routes: list[dict[str, Any]] = Field(default_factory=list)
    last_answer_memory: dict[str, Any] = Field(default_factory=dict)
    session_last_process_data: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)


class ContextOutput(BaseModel):
    send_request: AgentSendRequest
    request: AgentRequest
    user_context: dict[str, Any]
    turn_context: dict[str, Any]
    context_resolution: dict[str, Any]
    context_packs: dict[str, Any]
    compressed_context: dict[str, Any]
    rolling_summary: str
    context_validation_warnings: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    turn_process_data: dict[str, Any] | None = None
    previous_turn_process_data: dict[str, Any] | None = None
    process_data_reference_policy: dict[str, Any] = Field(default_factory=dict)
    ai4i_feature_status: dict[str, Any] = Field(default_factory=dict)
    trace: dict[str, Any] = Field(default_factory=dict)


def to_state(input_data: ContextInput) -> ContextState:
    return {
        'send_request': input_data.send_request.model_dump(),
        'session_id': input_data.session_id,
        'recent_turns': list(input_data.recent_turns),
        'rolling_summary': input_data.rolling_summary,
        'recent_turn_routes': list(input_data.recent_turn_routes),
        'last_answer_memory': dict(input_data.last_answer_memory),
        'session_last_process_data': input_data.session_last_process_data,
        'warnings': list(input_data.warnings),
        'trace': {},
    }


def to_output(state: ContextState) -> ContextOutput:
    output = state.get('output') or {}
    return ContextOutput(
        send_request=AgentSendRequest.model_validate(output.get('send_request') or state['send_request']),
        request=AgentRequest.model_validate(output.get('request') or state['request']),
        user_context=dict(output.get('user_context') or state.get('user_context') or {}),
        turn_context=dict(output.get('turn_context') or state.get('turn_context') or {}),
        context_resolution=dict(output.get('context_resolution') or state.get('context_resolution') or {}),
        context_packs=dict(output.get('context_packs') or state.get('context_packs') or {}),
        compressed_context=dict(output.get('compressed_context') or state.get('compressed_context') or {}),
        rolling_summary=str(output.get('rolling_summary') or (state.get('compressed_context') or {}).get('rolling_summary') or ''),
        context_validation_warnings=list(output.get('context_validation_warnings') or state.get('context_validation_warnings') or []),
        warnings=list(output.get('warnings') or state.get('warnings') or []),
        turn_process_data=output.get('turn_process_data', state.get('turn_process_data')),
        previous_turn_process_data=output.get('previous_turn_process_data', state.get('previous_turn_process_data')),
        process_data_reference_policy=dict(output.get('process_data_reference_policy') or state.get('process_data_reference_policy') or {}),
        ai4i_feature_status=dict(output.get('ai4i_feature_status') or state.get('ai4i_feature_status') or {}),
        trace=dict(output.get('trace') or state.get('trace') or {}),
    )
