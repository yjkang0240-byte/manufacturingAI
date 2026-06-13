from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from app.schemas.agent import AgentPlan, AgentRequest, LLMUsageRecord


class PlanningState(TypedDict, total=False):
    request: dict[str, Any]
    context_resolution: dict[str, Any]
    intent_gateway: dict[str, Any]
    plan: dict[str, Any]
    diagnostic_plan: dict[str, Any]
    route: list[str]
    usage_records: list[dict[str, Any]]
    trace: dict[str, Any]
    output: dict[str, Any]


class PlanningInput(BaseModel):
    request: AgentRequest
    context_resolution: dict[str, Any] = Field(default_factory=dict)
    intent_gateway: dict[str, Any] = Field(default_factory=dict)


class PlanningOutput(BaseModel):
    plan: AgentPlan
    diagnostic_plan: dict[str, Any]
    route: list[str] = Field(default_factory=list)
    usage_records: list[LLMUsageRecord] = Field(default_factory=list)
    trace: dict[str, Any] = Field(default_factory=dict)


def to_state(input_data: PlanningInput) -> PlanningState:
    return {
        'request': input_data.request.model_dump(),
        'context_resolution': dict(input_data.context_resolution),
        'intent_gateway': dict(input_data.intent_gateway),
        'usage_records': [],
        'trace': {},
    }


def to_output(state: PlanningState) -> PlanningOutput:
    output = state.get('output') or {}
    return PlanningOutput(
        plan=AgentPlan.model_validate(output.get('plan') or state['plan']),
        diagnostic_plan=dict(output.get('diagnostic_plan') or state.get('diagnostic_plan') or {}),
        route=list(output.get('route') or state.get('route') or []),
        usage_records=[LLMUsageRecord.model_validate(item) for item in output.get('usage_records') or state.get('usage_records') or []],
        trace=dict(output.get('trace') or state.get('trace') or {}),
    )
