from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from app.schemas.agent import AgentRequest, AgentResponse


class MemoryState(TypedDict, total=False):
    request: dict[str, Any]
    response: dict[str, Any]
    answer_memory_context: dict[str, Any]
    recent_turns: list[dict[str, Any]]
    recent_turn_routes: list[dict[str, Any]]
    turn_process_data: dict[str, Any] | None
    user_id: str
    answer_memory: dict[str, Any]
    session_last_process_data: dict[str, Any] | None
    warnings: list[str]
    diagnostics: dict[str, Any]
    trace: dict[str, Any]
    output: dict[str, Any]


class MemoryInput(BaseModel):
    request: AgentRequest
    response: AgentResponse
    answer_memory_context: dict[str, Any] = Field(default_factory=dict)
    recent_turns: list[dict[str, Any]] = Field(default_factory=list)
    recent_turn_routes: list[dict[str, Any]] = Field(default_factory=list)
    turn_process_data: dict[str, Any] | None = None
    user_id: str


class MemoryOutput(BaseModel):
    last_answer_memory: dict[str, Any] = Field(default_factory=dict)
    recent_turn_routes: list[dict[str, Any]] = Field(default_factory=list)
    recent_turns: list[dict[str, Any]] = Field(default_factory=list)
    session_last_process_data: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    trace: dict[str, Any] = Field(default_factory=dict)


def to_state(input_data: MemoryInput) -> MemoryState:
    return {
        'request': input_data.request.model_dump(),
        'response': input_data.response.model_dump(),
        'answer_memory_context': dict(input_data.answer_memory_context),
        'recent_turns': list(input_data.recent_turns),
        'recent_turn_routes': list(input_data.recent_turn_routes),
        'turn_process_data': input_data.turn_process_data,
        'user_id': input_data.user_id,
        'warnings': [],
        'diagnostics': {},
        'trace': {},
    }


def to_output(state: MemoryState) -> MemoryOutput:
    output = state.get('output') or {}
    return MemoryOutput(
        last_answer_memory=dict(output.get('last_answer_memory') or state.get('answer_memory') or {}),
        recent_turn_routes=list(output.get('recent_turn_routes') or state.get('recent_turn_routes') or []),
        recent_turns=list(output.get('recent_turns') or state.get('recent_turns') or []),
        session_last_process_data=output.get('session_last_process_data', state.get('session_last_process_data')),
        warnings=list(output.get('warnings') or state.get('warnings') or []),
        diagnostics=dict(output.get('diagnostics') or state.get('diagnostics') or {}),
        trace=dict(output.get('trace') or state.get('trace') or {}),
    )
