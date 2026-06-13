from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agent.context import AnswerMemoryWriter
from app.schemas.agent import AgentRequest, AgentResponse
from app.services.memory_service import MemoryService

from .state import MemoryState


@dataclass(frozen=True)
class MemoryDeps:
    answer_memory_writer: AnswerMemoryWriter
    memory_service: MemoryService


def extract_memory_candidates(state: MemoryState, deps: MemoryDeps) -> MemoryState:
    response = AgentResponse.model_validate(state['response'])
    memory_state = dict(state.get('answer_memory_context') or {})
    memory_state.setdefault('request', state.get('request'))
    answer_memory = deps.answer_memory_writer.build(state=memory_state, response=response)
    return {'answer_memory': answer_memory.model_dump()}


def update_focus(state: MemoryState, deps: MemoryDeps) -> MemoryState:
    request = AgentRequest.model_validate(state['request'])
    response = AgentResponse.model_validate(state['response'])
    answer_memory = dict(state.get('answer_memory') or {})
    route_history = list(state.get('recent_turn_routes') or [])
    route_history.append({
        'selected_path': answer_memory.get('selected_path'),
        'answer_type': answer_memory.get('answer_type'),
        'summary': answer_memory.get('short_summary'),
    })
    turns = list(state.get('recent_turns') or [])
    turns.append({'role': 'user', 'content': request.question})
    turns.append({'role': 'assistant', 'content': response.answer or ''})
    return {
        'recent_turn_routes': route_history[-10:],
        'recent_turns': turns[-10:],
        'session_last_process_data': state.get('turn_process_data'),
    }


def write_answer_memory(state: MemoryState, deps: MemoryDeps) -> MemoryState:
    request = AgentRequest.model_validate(state['request'])
    response = AgentResponse.model_validate(state['response'])
    warnings = list(state.get('warnings') or [])
    diagnostics = dict(state.get('diagnostics') or {})
    try:
        diagnostics['memory_update'] = deps.memory_service.update_from_run(
            user_id=state.get('user_id') or request.user_id or '',
            request=request,
            response=response,
        )
    except Exception as exc:
        diagnostics['memory_update_error'] = f'{type(exc).__name__}: {exc}'
        warnings.append('Memory update failed; response generation completed without persistent memory update.')
    return {'warnings': list(dict.fromkeys(warnings)), 'diagnostics': diagnostics}


def emit_memory_output(state: MemoryState, deps: MemoryDeps) -> MemoryState:
    answer_memory = dict(state.get('answer_memory') or {})
    trace = {
        'focus': answer_memory.get('focus'),
        'recommended_action_count': len(answer_memory.get('recommended_actions') or []),
        'memory_warning_count': len(state.get('warnings') or []),
    }
    output = {
        'last_answer_memory': answer_memory,
        'recent_turn_routes': state.get('recent_turn_routes') or [],
        'recent_turns': state.get('recent_turns') or [],
        'session_last_process_data': state.get('session_last_process_data'),
        'warnings': state.get('warnings') or [],
        'diagnostics': state.get('diagnostics') or {},
        'trace': trace,
    }
    return {'trace': trace, 'output': output}
