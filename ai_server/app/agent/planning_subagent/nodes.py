from __future__ import annotations

from dataclasses import dataclass

from app.agent.context import ContextResolution
from app.agent.heavy import DiagnosticPlanner
from app.schemas.agent import AgentRequest, LLMUsageRecord

from .state import PlanningState


@dataclass(frozen=True)
class PlanningDeps:
    diagnostic_planner: DiagnosticPlanner


def build_planning_context(state: PlanningState, deps: PlanningDeps) -> PlanningState:
    request = AgentRequest.model_validate(state['request'])
    resolution = ContextResolution.model_validate(state.get('context_resolution') or {
        'is_followup': False,
        'followup_type': 'none',
        'standalone_query': request.question,
        'reason': 'no_context_resolution',
    })
    return {
        'request': request.model_dump(),
        'context_resolution': resolution.model_dump(),
    }


def run_diagnostic_planner(state: PlanningState, deps: PlanningDeps) -> PlanningState:
    usage_records: list[dict] = []

    def collect_usage(record: LLMUsageRecord) -> None:
        usage_records.append(record.model_dump())

    result = deps.diagnostic_planner.plan(
        request=AgentRequest.model_validate(state['request']),
        context_resolution=ContextResolution.model_validate(state['context_resolution']),
        intent_result=state.get('intent_gateway') or {},
        usage_callback=collect_usage,
    )
    return {
        'plan': result.agent_plan.model_dump(),
        'diagnostic_plan': result.diagnostic_plan.model_dump(),
        'route': list(result.agent_plan.required_nodes),
        'usage_records': usage_records,
    }


def validate_plan(state: PlanningState, deps: PlanningDeps) -> PlanningState:
    plan = state.get('plan') or {}
    route = list(state.get('route') or plan.get('required_nodes') or [])
    return {'route': route}


def emit_planning_output(state: PlanningState, deps: PlanningDeps) -> PlanningState:
    plan = state.get('plan') or {}
    diagnostic = state.get('diagnostic_plan') or {}
    trace = {
        'intent': plan.get('intent'),
        'prediction_required': bool(plan.get('prediction_required')),
        'rag_required': bool(plan.get('rag_required')),
        'safety_required': bool(plan.get('safety_required')),
        'requires_data': bool(diagnostic.get('requires_data')),
    }
    output = {
        'plan': plan,
        'diagnostic_plan': diagnostic,
        'route': list(state.get('route') or []),
        'usage_records': list(state.get('usage_records') or []),
        'trace': trace,
    }
    return {'trace': trace, 'output': output}
