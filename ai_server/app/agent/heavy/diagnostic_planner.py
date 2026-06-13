from __future__ import annotations

from typing import Callable

from pydantic import BaseModel, Field

from app.config import AGENT_SUPERVISOR_LLM_REFINEMENT
from app.agent.context.schemas import ContextResolution
from app.schemas.agent import AgentPlan, AgentRequest, LLMUsageRecord
from app.services.supervisor_service import SupervisorService


SAFETY_KEYWORDS = ['안전', '비상', '대피', 'loto', 'lockout', 'tagout', '방호', '가드', '회전부', '인터록', '정비 전', '위험', '보호구', '비상정지', '전기', '제어반']
PREDICTION_KEYWORDS = ['토크', '공구', '마모', '온도', '회전수', 'rpm', '불량', '고장', '고장모드', '위험도', '예측', '공정 데이터', 'air temperature', 'torque', 'tool wear']
KNOWLEDGE_KEYWORDS = ['매뉴얼', '문서', '기술문서', '도면', 'p&id', 'pid', 'g-code', 'm-code', '설정', '트러블슈팅', '예방정비', '점검', '절차']
ASSET_KEYWORDS = ['cnc', '스핀들', 'spindle', 'tool changer', '공구교환', '냉각', '냉각수', '펌프', '제어반', '서보', '모터', '인터록', '비상정지']
MAINTENANCE_KEYWORDS = ['정비', '점검', '교체', '수리', '분해', 'maintenance', 'repair', 'replace']
CONDITION_JUDGMENT_KEYWORDS = ['이 조건', '현재 조건', '현재 값', '이 값', '이 데이터', '공정 데이터', '위험해', '위험한', '이상해', '고장 가능']


class DiagnosticPlan(BaseModel):
    """Structured diagnostic planning contract for the heavy manufacturing path."""

    requires_data: bool = False
    requires_rag: bool = False
    requires_safety: bool = False
    requires_prediction: bool = False
    requires_knowledge: bool = False
    requires_asset_context: bool = True
    requires_process_condition: bool = False
    requires_failure_mode: bool = False
    requires_safety_gate: bool = False
    requires_action_plan: bool = True
    missing_data_requirements: list[str] = Field(default_factory=list)
    document_scope: list[str] = Field(default_factory=list)
    rag_query: str = ''
    rag_reason: str = ''
    confidence: float = 0.82
    reason: str = ''
    source: str = 'deterministic'


class PlanningResult(BaseModel):
    diagnostic_plan: DiagnosticPlan
    agent_plan: AgentPlan


class DeterministicDiagnosticPolicy:
    """Deterministic MVP policy isolated behind DiagnosticPlanner.

    This keeps keyword planning out of root_graph and other callers.
    It produces a small structured DiagnosticPlan; callers should not inspect
    individual keyword matches.
    """

    def plan(
        self,
        req: AgentRequest,
        *,
        context_resolution: ContextResolution | None = None,
        intent_result: dict | None = None,
    ) -> DiagnosticPlan:
        q = (req.question or '').lower()
        prediction_required = self._requires_prediction(req, q, context_resolution, intent_result)
        safety_required = self._requires_safety(req, q, context_resolution, intent_result)
        knowledge_required = self._requires_knowledge(req, q, intent_result)
        asset_context_required = self._requires_asset_context(req, q, prediction_required, safety_required, knowledge_required)
        process_condition_required = prediction_required and bool(req.process_data)
        failure_mode_required = prediction_required
        safety_gate_required = self._requires_safety_gate(req, q, prediction_required, safety_required)
        action_plan_required = self._requires_action_plan(prediction_required, safety_required, knowledge_required)
        rag_required, rag_reason = self._requires_rag(req, q, prediction_required, safety_required, knowledge_required, intent_result)
        missing = ['process_data'] if prediction_required and not req.process_data else []
        document_scope = self._document_scope(prediction_required, safety_required, knowledge_required)
        return DiagnosticPlan(
            requires_data=bool(prediction_required),
            requires_rag=rag_required,
            requires_safety=safety_required,
            requires_prediction=prediction_required,
            requires_knowledge=knowledge_required,
            requires_asset_context=asset_context_required,
            requires_process_condition=process_condition_required,
            requires_failure_mode=failure_mode_required,
            requires_safety_gate=safety_gate_required,
            requires_action_plan=action_plan_required,
            missing_data_requirements=missing,
            document_scope=document_scope,
            rag_query=self._build_query(req, document_scope),
            rag_reason=rag_reason,
            reason='DeterministicDiagnosticPolicy가 제조 heavy path의 data/RAG/safety/prediction 요구사항을 구조화했습니다.',
        )

    @staticmethod
    def _contains(question: str, terms: list[str]) -> bool:
        return any(term.lower() in question for term in terms)

    def _requires_prediction(self, req: AgentRequest, q: str, context_resolution: ContextResolution | None, intent_result: dict | None) -> bool:
        if intent_result and intent_result.get('requires_prediction') is not None:
            return bool(intent_result.get('requires_prediction'))
        if context_resolution and context_resolution.followup_type == 'ambiguous':
            return False
        return bool(req.process_data) or req.mode == 'prediction' or self._contains(q, PREDICTION_KEYWORDS) or self._contains(q, CONDITION_JUDGMENT_KEYWORDS)

    def _requires_safety(self, req: AgentRequest, q: str, context_resolution: ContextResolution | None, intent_result: dict | None) -> bool:
        if intent_result and intent_result.get('requires_safety') is not None:
            return bool(intent_result.get('requires_safety'))
        if context_resolution and context_resolution.followup_type == 'ambiguous':
            return False
        return req.mode == 'safety_ops' or self._contains(q, SAFETY_KEYWORDS) or self._contains(q, MAINTENANCE_KEYWORDS)

    def _requires_knowledge(self, req: AgentRequest, q: str, intent_result: dict | None) -> bool:
        if intent_result and intent_result.get('requires_rag') and not intent_result.get('requires_prediction'):
            return True
        return req.mode == 'knowledge_qa' or self._contains(q, KNOWLEDGE_KEYWORDS)

    def _requires_asset_context(self, req: AgentRequest, q: str, prediction: bool, safety: bool, knowledge: bool) -> bool:
        return bool(req.process_data) or prediction or safety or knowledge or self._contains(q, ASSET_KEYWORDS)

    @staticmethod
    def _requires_safety_gate(req: AgentRequest, q: str, prediction: bool, safety: bool) -> bool:
        return safety or prediction or any(term.lower() in q for term in MAINTENANCE_KEYWORDS)

    @staticmethod
    def _requires_action_plan(prediction: bool, safety: bool, knowledge: bool) -> bool:
        return prediction or safety or knowledge

    def _requires_rag(self, req: AgentRequest, q: str, prediction: bool, safety: bool, knowledge: bool, intent_result: dict | None) -> tuple[bool, str]:
        if req.mode == 'hybrid':
            return True, 'hybrid mode requires retrieval coverage'
        if intent_result and intent_result.get('requires_rag'):
            return True, 'intent result requires document evidence'
        if knowledge or req.mode == 'knowledge_qa':
            return True, 'knowledge/document QA needs retrieval'
        if self._contains(q, ['문서', '매뉴얼', '절차', '출처', '근거', 'citation', '인용', '기준']):
            return True, 'document/source/evidence wording requires retrieval'
        if safety and self._contains(q, ['절차', '기준', '규정', '문서', '매뉴얼', 'loto', 'lockout', 'tagout']):
            return True, 'safety request asks for procedural/document-backed guidance'
        if req.mode == 'auto' and prediction:
            return False, 'auto process-data prediction can run without retrieval unless evidence is requested'
        return False, 'no retrieval trigger matched'

    @staticmethod
    def _document_scope(prediction: bool, safety: bool, knowledge: bool) -> list[str]:
        scope = []
        if prediction:
            scope.append('failure_mode_catalog')
        if knowledge:
            scope.extend(['maintenance_manual', 'troubleshooting_guide'])
        if safety:
            scope.extend(['safety_standard', 'loto', 'machine_guarding'])
        return list(dict.fromkeys(scope)) or ['manufacturing_reference']

    @staticmethod
    def _build_query(req: AgentRequest, document_scope: list[str]) -> str:
        terms = [req.question]
        if req.process_data:
            terms.extend(['AI4I', 'machine failure', 'torque', 'tool wear', 'process temperature'])
        if req.inspection_notes:
            terms.append(req.inspection_notes)
        terms.extend(document_scope)
        return ' '.join([t for t in terms if t]).strip()


class DiagnosticPlanner:
    """Planning boundary around SupervisorService.

    Root graph callers receive only AgentPlan plus an optional structured
    DiagnosticPlan snapshot. Deterministic keyword planning is intentionally
    isolated here instead of being exposed as root_graph branching logic.
    """

    def __init__(self, supervisor: SupervisorService, policy: DeterministicDiagnosticPolicy | None = None):
        from app.agent.heavy.plan_refiner import PlanRefiner
        from app.agent.heavy.plan_translator import DiagnosticPlanToAgentPlanTranslator

        self.supervisor = supervisor
        self.policy = policy or DeterministicDiagnosticPolicy()
        self.translator = DiagnosticPlanToAgentPlanTranslator()
        self.refiner = PlanRefiner(supervisor.llm_service, self.translator)

    def plan(
        self,
        *,
        request: AgentRequest,
        context_resolution: ContextResolution | None = None,
        intent_result: dict | None = None,
        usage_callback: Callable[[LLMUsageRecord], None] | None = None,
    ) -> PlanningResult:
        diagnostic = self.policy.plan(
            request,
            context_resolution=context_resolution,
            intent_result=intent_result,
        )
        base = self.translator.translate(diagnostic)
        if context_resolution and context_resolution.followup_type == 'ambiguous':
            return PlanningResult(diagnostic_plan=diagnostic, agent_plan=base)
        if not AGENT_SUPERVISOR_LLM_REFINEMENT:
            return PlanningResult(diagnostic_plan=diagnostic, agent_plan=base)
        refined = self.refiner.refine(
            request=request,
            diagnostic_plan=diagnostic,
            base_plan=base,
            usage_callback=usage_callback,
        )
        return PlanningResult(diagnostic_plan=diagnostic, agent_plan=refined or base)

    def replan(self, request: AgentRequest, previous: AgentPlan, findings: list[str], attempt: int) -> AgentPlan:
        return self.supervisor.replan(request, previous, findings, attempt=attempt)

    def structured_plan(
        self,
        request: AgentRequest,
        *,
        context_resolution: ContextResolution | None = None,
        intent_result: dict | None = None,
    ) -> DiagnosticPlan:
        diagnostic = self.policy.plan(
            request,
            context_resolution=context_resolution,
            intent_result=intent_result,
        )
        return diagnostic
