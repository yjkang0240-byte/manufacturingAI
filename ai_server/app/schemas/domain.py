from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

RiskLevel = Literal['low', 'medium', 'high', 'critical', 'unknown', 'not_applicable', 'conditional']


class AssetContext(BaseModel):
    equipment_type: str = 'GeneralMachine'
    equipment_label_ko: str = '일반 설비'
    inferred_subsystems: list[str] = []
    inferred_components: list[str] = []
    hazards: list[str] = []
    confidence: float = 0.0
    rationale: str = ''


class ProcessCondition(BaseModel):
    tag: str
    label_ko: str
    severity: RiskLevel = 'unknown'
    source_feature: str | None = None
    value: float | int | str | None = None
    explanation: str = ''


class FailureModeDetail(BaseModel):
    code: str
    name_ko: str
    description_ko: str
    confidence: float = 0.0
    related_features: list[str] = []
    related_subsystems: list[str] = []
    recommended_checks: list[str] = []
    safety_gates: list[str] = []
    source: str = 'catalog'


class RiskAxis(BaseModel):
    axis: str
    level: RiskLevel
    rationale: str


class RiskAssessment(BaseModel):
    quality: RiskAxis
    equipment: RiskAxis
    safety: RiskAxis
    production: RiskAxis
    document_confidence: RiskAxis
    prediction_risk: RiskAxis | None = None
    safety_work_risk: RiskAxis | None = None
    overall_priority: RiskLevel
    escalation_required: bool = False
    rationale: str = ''


class SafetyGateResult(BaseModel):
    gate_id: str
    name_ko: str
    severity: RiskLevel
    description_ko: str
    required_checks: list[str]
    forbidden_agent_actions: list[str]
    escalation: str | None = None
    triggered_by: list[str] = []
    document_search_terms: list[str] = []


class ActionStep(BaseModel):
    action_id: str
    label_ko: str
    description_ko: str
    output_phrase: str
    priority: RiskLevel = 'medium'
    related_failure_modes: list[str] = []
    related_subsystems: list[str] = []
    requires_machine_stop: bool = False
    requires_loto: bool | str = False
    requires_authorized_person: bool = True
    safety_gate_ids: list[str] = []


class ManufacturingContext(BaseModel):
    asset_context: AssetContext
    process_conditions: list[ProcessCondition] = []
    failure_modes: list[FailureModeDetail] = []
    risk_assessment: RiskAssessment
    safety_gates: list[SafetyGateResult] = []
    action_plan: list[ActionStep] = []
    document_search_terms: list[str] = []
    audit_notes: list[str] = []
