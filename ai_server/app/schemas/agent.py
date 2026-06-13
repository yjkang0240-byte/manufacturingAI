from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.domain import ManufacturingContext
from app.schemas.prediction import PredictionResponse, ProcessData
from app.schemas.rag import RagChunk

AgentMode = Literal['auto', 'prediction', 'knowledge_qa', 'safety_ops', 'hybrid']
AgentIntent = Literal['prediction', 'knowledge_qa', 'safety_ops', 'hybrid', 'general']
ResolvedTargetType = Literal['concept', 'equipment', 'component', 'failure_mode', 'process_condition', 'document', 'report', 'previous_answer', 'unknown']
QuestionKind = Literal['general_concept_followup', 'current_state_followup', 'document_followup', 'safety_followup', 'report_followup', 'comparison_followup', 'unknown_followup']


class ResolvedTarget(BaseModel):
    label: str
    type: ResolvedTargetType = 'unknown'
    source: str
    reference_run_id: str | None = None
    reference_session_id: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ReferenceResolutionResult(BaseModel):
    original_question: str
    resolved_question: str
    resolved: bool = False
    resolved_target: ResolvedTarget | None = None
    question_kind: QuestionKind = 'unknown_followup'
    should_use_prediction: bool = False
    should_use_rag: bool = False
    should_use_safety: bool = False
    clarification_question: str | None = None
    reason: str = ''
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class AgentRequest(BaseModel):
    user_id: str | None = Field(default=None, max_length=128)
    question: str = Field(default='', max_length=4000)
    process_data: ProcessData | None = None
    inspection_notes: str | None = Field(default=None, max_length=10000)
    top_k: int = Field(default=5, ge=1, le=20)
    session_id: str | None = Field(default=None, max_length=128)
    mode: AgentMode = 'auto'
    llm_model: str | None = Field(default=None, max_length=80)
    user_context: dict[str, Any] | None = None


class AgentSendRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    message: str = Field(default='', max_length=4000, description='사용자 메시지 또는 질문')
    session_id: str | None = Field(default=None, max_length=128)
    process_data: ProcessData | None = None
    inspection_notes: str | None = Field(default=None, max_length=10000)
    top_k: int = Field(default=5, ge=1, le=20)
    mode: AgentMode = 'auto'
    llm_model: str | None = Field(default=None, max_length=80)


class AgentTraceStep(BaseModel):
    step: str
    detail: str


class AgentLayer(BaseModel):
    name: str
    nodes: list[str]
    purpose: str


class AgentPlan(BaseModel):
    intent: AgentIntent
    confidence: float = 0.0
    prediction_required: bool = False
    rag_required: bool = False
    safety_required: bool = False
    domain_context_required: bool = True
    asset_context_required: bool = True
    process_condition_required: bool = False
    failure_mode_required: bool = False
    risk_priority_required: bool = True
    safety_gate_required: bool = False
    action_plan_required: bool = True
    required_nodes: list[str] = []
    layers: list[AgentLayer] = []
    rag_query: str = ''
    rag_filters: dict[str, Any] | None = None
    document_scope: list[str] = []
    rationale: str = ''
    supervisor_source: Literal['deterministic', 'llm_refined'] = 'deterministic'


class LLMUsageRecord(BaseModel):
    provider: str = 'openai'
    model: str
    operation: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    estimated_cost_krw: float = 0.0
    usd_krw_exchange_rate: float = 0.0
    latency_ms: float = 0.0


class LLMUsageSummary(BaseModel):
    calls: int = 0
    replan_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    estimated_cost_krw: float = 0.0
    usd_krw_exchange_rate: float = 0.0
    records: list[LLMUsageRecord] = []


class AgentResponse(BaseModel):
    run_id: str
    user_id: str | None = None
    route: list[str]
    answer: str
    prediction: PredictionResponse | None = None
    manufacturing_context: ManufacturingContext | None = None
    retrieved_documents: list[RagChunk] = []
    safety_guidance: str | None = None
    report: str | None = None
    citations: list[dict[str, Any]] = []
    warnings: list[str] = []
    trace: list[AgentTraceStep] = []
    saved: bool = False
    session_id: str | None = None
    plan: AgentPlan | None = None
    llm_used: bool = False
    llm_provider: str = 'openai'
    llm_model: str | None = None
    llm_usage: LLMUsageSummary | None = None
    llm_error: str | None = None
    context_used: dict[str, Any] | None = None
    prediction_called: bool = False
    prediction_skip_reason: Literal['missing_ai4i_features', 'ambiguous_ai4i_features', 'invalid_ai4i_features'] | None = None
    missing_features: list[str] = []
    ambiguous_features: list[str] = []
    parsed_ai4i_features: dict[str, Any] = {}
