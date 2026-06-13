from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from app.agent.checkpointing import build_thread_id, create_sqlite_checkpointer
from app.agent.context import AnswerMemoryWriter, ContextCompressor, ContextPackBuilder, ContextResolver, ContextValidator
from app.agent.context_subagent import ContextDeps, ContextInput, ContextSubAgent
from app.agent.formatters import FormatterRegistry
from app.agent.heavy import CitationBuilder, DiagnosticPlanner, EvidenceFilter, EvidenceGrader, RagQueryPlanner, RecommendationBuilder, SafetyGateBuilder, StructuredAnswerPayloadBuilder
from app.agent.heavy.rag_query_planner import RagFanoutPolicy
from app.agent.memory_subagent import MemoryDeps, MemoryInput, MemorySubAgent
from app.agent.planning_subagent import PlanningDeps, PlanningInput, PlanningSubAgent
from app.agent.rag_evidence import RagEvidenceDeps, RagEvidenceInput, RagEvidenceSubAgent
from app.agent.safety_subagent import SafetyDeps, SafetyInput, SafetySubAgent
from app.agent.state import AgentState
from app.agent.trace import append_trace, to_agent_trace_steps, trace_step
from app.config import AGENT_MAX_RAG_TOP_K, AGENT_MAX_REPLAN_ATTEMPTS, LANGGRAPH_CHECKPOINT_DB, LLM_PROVIDER
from app.errors import LLMUnavailableError
from app.errors import UnsafeResponseError
from app.schemas.agent import AgentPlan, AgentRequest, AgentResponse, AgentSendRequest, AgentTraceStep, LLMUsageRecord, LLMUsageSummary
from app.schemas.domain import ManufacturingContext
from app.schemas.prediction import PredictionResponse
from app.schemas.rag import RagChunk
from app.services.context_service import ContextService
from app.services.domain_service import DomainKnowledgeService
from app.services.glossary_answer_service import GlossaryAnswerService
from app.services.intent_classifier_service import IntentClassifierService
from app.services.intent_gateway_service import IntentGatewayService
from app.services.llm_service import ANSWER_SCHEMA, LLMService
from app.services.memory_service import MemoryService
from app.services.prediction_service import PredictionService
from app.services.rag_service import RagService
from app.services.safety_validation_service import SafetyValidationService
from app.services.supervisor_service import SupervisorService
from app.services.user_service import UserService
from app.storage.sqlite_store import SQLiteStore


class RootManufacturingGraph:
    """LangGraph root graph for the manufacturing agent runtime."""

    def __init__(
        self,
        *,
        store: SQLiteStore,
        user_service: UserService,
        context_service: ContextService,
        memory_service: MemoryService,
        prediction_service: PredictionService,
        domain_service: DomainKnowledgeService,
        safety_validator: SafetyValidationService,
        llm_service: LLMService,
        rag_service: RagService,
        intent_classifier: IntentClassifierService | None = None,
        checkpoint_path: Path | None = None,
    ):
        self.store = store
        self.prediction_service = prediction_service
        self.domain_service = domain_service
        self.safety_validator = safety_validator
        self.llm_service = llm_service
        self.intent_classifier = intent_classifier or IntentClassifierService(llm_service)
        self.intent_gateway = IntentGatewayService(intent_classifier=self.intent_classifier)
        self.glossary_answer_service = GlossaryAnswerService()
        self.formatter_registry = FormatterRegistry()
        self.context_subagent = ContextSubAgent(ContextDeps(
            user_service=user_service,
            context_service=context_service,
            context_resolver=ContextResolver(),
            context_pack_builder=ContextPackBuilder(),
            context_compressor=ContextCompressor(max_recent_turns=5),
            context_validator=ContextValidator(),
        ))
        self.diagnostic_planner = DiagnosticPlanner(SupervisorService(self.llm_service))
        self.planning_subagent = PlanningSubAgent(PlanningDeps(diagnostic_planner=self.diagnostic_planner))
        self.citation_builder = CitationBuilder()
        self.rag_evidence_subagent = RagEvidenceSubAgent(RagEvidenceDeps(
            query_planner=RagQueryPlanner(),
            fanout_policy=RagFanoutPolicy(),
            rag_service=rag_service,
            evidence_filter=EvidenceFilter(),
            evidence_grader=EvidenceGrader(),
            citation_builder=self.citation_builder,
            domain_service=self.domain_service,
        ))
        self.recommendation_builder = RecommendationBuilder()
        self.safety_subagent = SafetySubAgent(SafetyDeps(
            domain_service=domain_service,
            recommendation_builder=self.recommendation_builder,
            safety_gate_builder=SafetyGateBuilder(),
        ))
        self.memory_subagent = MemorySubAgent(MemoryDeps(
            answer_memory_writer=AnswerMemoryWriter(),
            memory_service=memory_service,
        ))
        self.structured_payload_builder = StructuredAnswerPayloadBuilder()
        self.checkpoint_path = checkpoint_path or LANGGRAPH_CHECKPOINT_DB.with_name(f'{LANGGRAPH_CHECKPOINT_DB.stem}_v2{LANGGRAPH_CHECKPOINT_DB.suffix}')
        self._checkpointer_handle = create_sqlite_checkpointer(self.checkpoint_path)
        self.checkpointer = self._checkpointer_handle.checkpointer
        self.graph = self._build_graph()
        self._progress_callback: Callable[[AgentTraceStep], None] | None = None

    def close(self) -> None:
        self._checkpointer_handle.close()

    def run(self, req: AgentSendRequest, progress_callback: Callable[[AgentTraceStep], None] | None = None) -> AgentResponse:
        self._progress_callback = progress_callback
        session_id = req.session_id or f'session_{uuid4().hex[:12]}'
        thread_id = build_thread_id(user_id=req.user_id, session_id=session_id)
        state: AgentState = {
            'state_schema_version': 2,
            'run_id': str(uuid4()),
            'user_id': req.user_id,
            'session_id': session_id,
            'thread_id': thread_id,
            'current_user_message': req.message,
            'send_request': req.model_dump(),
            'warnings': [],
            'errors': [],
            'usage_records': [],
            'trace': [],
            'replan_count': 0,
        }
        config = self._thread_config(user_id=req.user_id, session_id=session_id)
        try:
            final_state = self.graph.invoke(state, config=config)
            response = final_state.get('response')
            if not response:
                raise LLMUnavailableError('Root graph did not produce a response')
            return self._response_model(response)
        finally:
            self._progress_callback = None

    def preview_route(self, req: AgentSendRequest) -> dict[str, Any]:
        session_id = req.session_id or f'session_{uuid4().hex[:12]}'
        previous = self._checkpoint_values(user_id=req.user_id, session_id=session_id)
        state = self._request_context_node({
            'state_schema_version': 2,
            'run_id': str(uuid4()),
            'user_id': req.user_id,
            'session_id': session_id,
            'thread_id': build_thread_id(user_id=req.user_id, session_id=session_id),
            'current_user_message': req.message,
            'recent_turns': previous.get('recent_turns') or [],
            'rolling_summary': previous.get('rolling_summary') or '',
            'recent_turn_routes': previous.get('recent_turn_routes') or [],
            'last_answer_memory': previous.get('last_answer_memory') or {},
            'session_last_process_data': previous.get('session_last_process_data'),
            'send_request': req.model_dump(),
            'warnings': [],
            'errors': [],
            'usage_records': [],
            'trace': [],
            'replan_count': 0,
        })
        state = self.intent_gateway_node(state)
        return state['intent_gateway']

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node('request_context', self._request_context_node)
        graph.add_node('intent_gateway', self.intent_gateway_node)
        graph.add_node('fast_concept_answer', self._fast_concept_answer_node)
        graph.add_node('general_lightweight_answer', self._general_lightweight_answer_node)
        graph.add_node('recommended_action_recap', self._recommended_action_recap_node)
        graph.add_node('recommended_action_item_explanation', self._recommended_action_item_explanation_node)
        graph.add_node('unsupported_or_clarification', self._unsupported_or_clarification_node)
        graph.add_node('meta_feedback', self._meta_feedback_node)
        graph.add_node('supervisor_planning', self._supervisor_planning_node)
        graph.add_node('manufacturing_analysis', self._manufacturing_analysis_node)
        graph.add_node('evidence_retrieval', self._evidence_retrieval_node)
        graph.add_node('safety', self._safety_node)
        graph.add_node('response_synthesis', self._response_synthesis_node)
        graph.add_node('response_packager', self._response_packager_node)
        graph.add_node('focus_updater', self._focus_updater_node)
        graph.add_node('audit_persistence', self._audit_persistence_node)
        graph.set_entry_point('request_context')
        graph.add_edge('request_context', 'intent_gateway')
        graph.add_conditional_edges(
            'intent_gateway',
            self.route_after_gateway,
            {
                'fast_concept_answer': 'fast_concept_answer',
                'general_lightweight_answer': 'general_lightweight_answer',
                'recommended_action_recap': 'recommended_action_recap',
                'recommended_action_item_explanation': 'recommended_action_item_explanation',
                'unsupported_or_clarification': 'unsupported_or_clarification',
                'ai4i_clarification_required': 'unsupported_or_clarification',
                'meta_feedback': 'meta_feedback',
                'supervisor_planning': 'supervisor_planning',
            },
        )
        graph.add_edge('fast_concept_answer', 'focus_updater')
        graph.add_edge('general_lightweight_answer', 'focus_updater')
        graph.add_edge('recommended_action_recap', 'focus_updater')
        graph.add_edge('recommended_action_item_explanation', 'focus_updater')
        graph.add_edge('unsupported_or_clarification', 'focus_updater')
        graph.add_edge('meta_feedback', 'focus_updater')
        graph.add_conditional_edges(
            'supervisor_planning',
            self._route_after_supervisor,
            {
                'manufacturing_analysis': 'manufacturing_analysis',
                'evidence_retrieval': 'evidence_retrieval',
                'safety': 'safety',
                'response_synthesis': 'response_synthesis',
            },
        )
        graph.add_conditional_edges(
            'manufacturing_analysis',
            self._route_after_manufacturing,
            {
                'evidence_retrieval': 'evidence_retrieval',
                'safety': 'safety',
                'response_synthesis': 'response_synthesis',
            },
        )
        graph.add_conditional_edges(
            'evidence_retrieval',
            self._route_after_retrieval,
            {
                'safety': 'safety',
                'response_synthesis': 'response_synthesis',
            },
        )
        graph.add_edge('safety', 'response_synthesis')
        graph.add_edge('response_synthesis', 'response_packager')
        graph.add_edge('response_packager', 'focus_updater')
        graph.add_edge('focus_updater', 'audit_persistence')
        graph.add_edge('audit_persistence', END)
        return graph.compile(checkpointer=self.checkpointer)

    def _request_context_node(self, state: AgentState) -> AgentState:
        output = self.context_subagent.invoke(ContextInput(
            send_request=self._send_request_model(state),
            session_id=state['session_id'],
            recent_turns=list(state.get('recent_turns') or []),
            rolling_summary=state.get('rolling_summary') or '',
            recent_turn_routes=list(state.get('recent_turn_routes') or []),
            last_answer_memory=dict(state.get('last_answer_memory') or {}),
            session_last_process_data=state.get('session_last_process_data'),
            warnings=list(state.get('warnings') or []),
        ))
        self._emit_trace(state, trace_step(
            node_id='context_subagent.context_builder',
            node_name='ContextSubAgent',
            node_type='subgraph',
            layer='Context SubAgent',
            status='success',
            input_summary=f'user_id={output.send_request.user_id}, session_id={output.send_request.session_id}',
            output_summary=(
                f'followup={output.trace.get("followup")}, '
                f'type={output.trace.get("followup_type")}, '
                f'previous_process_data_used={output.trace.get("previous_process_data_used")}'
            ),
        ))
        state['send_request'] = output.send_request.model_dump()
        state['request'] = output.request.model_dump()
        state['user_context'] = output.user_context
        state['turn_context'] = output.turn_context
        state['context_resolution'] = output.context_resolution
        state['context_packs'] = output.context_packs
        state['compressed_context'] = output.compressed_context
        state['rolling_summary'] = output.rolling_summary
        state['context_validation_warnings'] = output.context_validation_warnings
        state['warnings'] = list(dict.fromkeys(output.warnings))
        state['turn_process_data'] = output.turn_process_data
        state['previous_turn_process_data'] = output.previous_turn_process_data
        state['process_data_reference_policy'] = output.process_data_reference_policy
        state['ai4i_feature_status'] = output.ai4i_feature_status
        return self._return_state(state)

    def intent_gateway_node(self, state: AgentState) -> AgentState:
        ai4i_status = state.get('ai4i_feature_status') or {}
        if ai4i_status.get('clarification_required'):
            gateway = {
                'selected_path': 'ai4i_clarification_required',
                'answer_type': 'ai4i_clarification',
                'turn_type': 'prediction_clarification',
                'requires_prediction': False,
                'requires_rag': False,
                'requires_safety': False,
                'reason': ai4i_status.get('prediction_skip_reason') or 'AI4I feature clarification required.',
            }
            self._emit_trace(state, trace_step(
                node_id='intent_gateway.ai4i_feature_check',
                node_name='AI4I Feature Completeness Gate',
                node_type='router',
                layer='Intent Gateway',
                status='success',
                input_summary=(state.get('current_user_message') or '')[:120],
                output_summary=(
                    f'skip_reason={ai4i_status.get("prediction_skip_reason")}, '
                    f'missing={len(ai4i_status.get("missing_features") or [])}, '
                    f'ambiguous={len(ai4i_status.get("ambiguous_features") or [])}'
                ),
            ))
            state['intent_gateway'] = gateway
            state['selected_path'] = 'ai4i_clarification_required'
            return self._return_state(state)

        def collect_usage(record: LLMUsageRecord) -> None:
            state['usage_records'].append(record)
            self._emit_trace(state, trace_step(
                node_id='audit.usage_meter',
                node_name='Usage Meter',
                node_type='metric',
                layer='Audit / Persistence',
                status='success',
                output_summary=f'{record.operation}: input={record.input_tokens}, output={record.output_tokens}, cost=${record.estimated_cost_usd:.6f}',
            ))

        request = self._request_model(state)
        gateway = self.intent_gateway.classify(request=request, user_context=state.get('user_context') or {}, usage_callback=collect_usage)
        self._emit_trace(state, trace_step(
            node_id='intent_gateway.classifier',
            node_name='Intent Gateway',
            node_type='router',
            layer='Intent Gateway',
            status='success',
            input_summary=request.question[:120],
            output_summary=f'turn_type={gateway["turn_type"]}, path={gateway["selected_path"]}',
        ))
        state['intent_gateway'] = gateway
        state['selected_path'] = gateway['selected_path']
        return self._return_state(state)

    @staticmethod
    def route_after_gateway(state: AgentState) -> str:
        return state.get('selected_path') or 'supervisor_planning'

    def _fast_concept_answer_node(self, state: AgentState) -> AgentState:
        request = self._request_model(state)
        glossary_payload = self.glossary_answer_service.answer_payload(request.question)
        if glossary_payload:
            formatter_context = {
                'selected_path': state.get('selected_path') or 'fast_concept_answer',
                'answer_type': (state.get('intent_gateway') or {}).get('answer_type') or 'definition',
                'concept_payload': glossary_payload,
                'reference_note': self._reference_note(state, glossary_payload.get('term')),
            }
            answer = self.formatter_registry.format('fast_concept_answer', formatter_context)
            self._emit_trace(state, trace_step(
                node_id='fast_path.glossary_answer',
                node_name='No-LLM Glossary Answer',
                node_type='template',
                layer='Fast Path',
                status='success',
                output_summary=f'term={glossary_payload["term"]}',
            ))
            state['response'] = self._response_from_state(
                state,
                answer=answer,
                warnings=[],
                route=['context_subagent.context_builder', 'intent_gateway.classifier', 'fast_path.glossary_answer'],
            )
            state['formatter_context'] = formatter_context
            state['structured_answer_payload'] = {'concept': glossary_payload}
            return self._return_state(state)

        usage_records: list[LLMUsageRecord] = []

        def collect_usage(record: LLMUsageRecord) -> None:
            usage_records.append(record)

        payload = {
            'question': request.question,
            'context_resolution': (request.user_context or {}).get('context_resolution') or {},
            'intent_gateway': state.get('intent_gateway') or {},
            'policy': {
                'answer_scope': 'general_concept_only',
                'do_not_infer_current_machine_state': True,
                'must_say_process_data_required_for_current_risk': True,
            },
        }
        result = self.llm_service.generate_json(
            schema_name='fast_concept_answer',
            schema=ANSWER_SCHEMA,
            system_prompt=(
                '당신은 제조/기계 개념을 설명하는 AI입니다. '
                '정의, 장단점, 한계, 원리 질문에는 일반 제조/기계 지식으로 간결하게 답하세요. '
                '현재 설비 상태, 고장 확률, 안전 상태는 공정 데이터와 검증 근거 없이는 단정하지 마세요. '
                '답변에는 "현재 설비 상태나 고장 위험은 실제 공정 데이터가 있어야 판단할 수 있습니다."라는 경계 문구를 포함하세요.'
            ),
            payload=payload,
            model=request.llm_model,
            operation='fast_concept_answer',
            usage_callback=collect_usage,
        )
        if not result:
            raise LLMUnavailableError(self.llm_service.last_error or 'Fast concept answer failed')
        state['usage_records'].extend(usage_records)
        self._emit_trace(state, trace_step(
            node_id='fast_path.concept_answer',
            node_name='Concept Answer Node',
            node_type='llm',
            layer='Fast Path',
            status='success',
            output_summary='general concept answer composed',
        ))
        answer = str(result.get('answer') or '').strip()
        warnings = [str(w) for w in (result.get('warnings') or []) if str(w).strip()]
        state['response'] = self._response_from_state(state, answer=answer, warnings=warnings, route=['context_subagent.context_builder', 'intent_gateway.classifier', 'fast_path.concept_answer'])
        return self._return_state(state)

    def _general_lightweight_answer_node(self, state: AgentState) -> AgentState:
        gateway = state.get('intent_gateway') or {}
        answer_context = ((state.get('context_packs') or {}).get('answer_context') or {})
        memory = answer_context.get('relevant_answer_memory') or {}
        formatter_context = {
            'selected_path': state.get('selected_path') or 'general_lightweight_answer',
            'answer_type': gateway.get('answer_type') or 'explanation',
            'target': (gateway.get('resolved_reference') or {}).get('normalized') or memory.get('focus'),
            'resolved_claim': gateway.get('resolved_claim'),
            'phrase_repair': gateway.get('phrase_repair'),
            'followup_target': (state.get('context_resolution') or {}).get('followup_target'),
        }
        answer = self.formatter_registry.format('general_lightweight_answer', formatter_context)
        self._emit_trace(state, trace_step(
            node_id='general_lightweight.answer',
            node_name='General Lightweight Answer',
            node_type='template',
            layer='Fast Path',
            status='success',
            output_summary=f'answer_type={formatter_context.get("answer_type")}',
        ))
        state['formatter_context'] = formatter_context
        state['response'] = self._response_from_state(
            state,
            answer=answer,
            warnings=[],
            route=['context_subagent.context_builder', 'intent_gateway.classifier', 'general_lightweight.answer'],
        )
        return self._return_state(state)

    def _recommended_action_recap_node(self, state: AgentState) -> AgentState:
        formatter_context = ((state.get('context_packs') or {}).get('formatter_context') or {})
        answer = self.formatter_registry.format('recommended_action_recap', formatter_context)
        self._emit_trace(state, trace_step(
            node_id='response.recommended_action_recap',
            node_name='Recommended Action Recap Formatter',
            node_type='formatter',
            layer='Response Synthesis',
            status='success',
            output_summary=f'actions={len(formatter_context.get("recommended_actions") or [])}',
        ))
        state['formatter_context'] = formatter_context
        state['response'] = self._response_from_state(
            state,
            answer=answer,
            warnings=[],
            route=['context_subagent.context_builder', 'intent_gateway.classifier', 'response.recommended_action_recap'],
        )
        return self._return_state(state)

    def _recommended_action_item_explanation_node(self, state: AgentState) -> AgentState:
        formatter_context = ((state.get('context_packs') or {}).get('formatter_context') or {})
        answer = self.formatter_registry.format('recommended_action_item_explanation', formatter_context)
        self._emit_trace(state, trace_step(
            node_id='response.recommended_action_item_explanation',
            node_name='Recommended Action Item Formatter',
            node_type='formatter',
            layer='Response Synthesis',
            status='success',
            output_summary=f'item={formatter_context.get("followup_item_index")}',
        ))
        state['formatter_context'] = formatter_context
        state['response'] = self._response_from_state(
            state,
            answer=answer,
            warnings=[],
            route=['context_subagent.context_builder', 'intent_gateway.classifier', 'response.recommended_action_item_explanation'],
        )
        return self._return_state(state)

    def _meta_feedback_node(self, state: AgentState) -> AgentState:
        self._emit_trace(state, trace_step(
            node_id='intent_gateway.meta_feedback',
            node_name='Meta Feedback',
            node_type='router',
            layer='Intent Gateway',
            status='success',
            output_summary='사용자 피드백을 제조 분석이 아닌 메타 응답으로 처리',
        ))
        memory = state.get('last_answer_memory') or {}
        formatter_context = {
            'selected_path': state.get('selected_path') or 'meta_feedback',
            'answer_type': 'meta_feedback',
            'answer_memory_focus': memory.get('focus'),
        }
        state['response'] = self._response_from_state(
            state,
            answer=self._meta_feedback_answer(formatter_context),
            warnings=[],
            route=['context_subagent.context_builder', 'intent_gateway.classifier', 'intent_gateway.meta_feedback'],
        )
        state['formatter_context'] = formatter_context
        return self._return_state(state)

    def _unsupported_or_clarification_node(self, state: AgentState) -> AgentState:
        if state.get('selected_path') == 'ai4i_clarification_required':
            answer = self._ai4i_clarification_answer(state.get('ai4i_feature_status') or {})
            self._emit_trace(state, trace_step(
                node_id='intent_gateway.ai4i_clarification',
                node_name='AI4I Clarification',
                node_type='router',
                layer='Intent Gateway',
                status='success',
                output_summary='AI4I 필수 feature 보완 요청',
            ))
            state['response'] = self._response_from_state(
                state,
                answer=answer,
                warnings=[],
                route=['context_subagent.context_builder', 'intent_gateway.ai4i_feature_check', 'intent_gateway.ai4i_clarification'],
            )
            return self._return_state(state)

        gateway = state.get('intent_gateway') or {}
        resolution = state.get('context_resolution') or {}
        answer = None
        if resolution.get('followup_type') == 'ambiguous':
            answer = '이전 답변의 어떤 대상을 가리키는지 명확하지 않습니다. 대상이나 항목을 지정해 다시 질문해 주세요.'
        if not answer:
            answer = self._clarification_answer(reason=gateway.get('reason') or '이 요청은 현재 Agent가 수행할 수 없습니다.')
        else:
            answer = self._clarification_answer(reason=str(answer))
        self._emit_trace(state, trace_step(
            node_id='intent_gateway.clarification',
            node_name='Unsupported / Clarification Node',
            node_type='router',
            layer='Intent Gateway',
            status='success',
            output_summary=str(answer)[:160],
        ))
        state['response'] = self._response_from_state(
            state,
            answer=answer,
            warnings=['제조 설비 제어, 안전 보증, 법적 최종 판단은 수행하지 않습니다.'],
            route=['context_subagent.context_builder', 'intent_gateway.classifier', 'intent_gateway.clarification'],
        )
        return self._return_state(state)

    def _supervisor_planning_node(self, state: AgentState) -> AgentState:
        request = self._request_model(state)
        output = self.planning_subagent.invoke(PlanningInput(
            request=request,
            context_resolution=state.get('context_resolution') or {},
            intent_gateway=state.get('intent_gateway') or {},
        ))
        for record in output.usage_records:
            state['usage_records'].append(record)
            self._emit_trace(state, trace_step(
                node_id='audit.usage_meter',
                node_name='Usage Meter',
                node_type='metric',
                layer='Audit / Persistence',
                status='success',
                output_summary=f'{record.operation}: input={record.input_tokens}, output={record.output_tokens}, cost=${record.estimated_cost_usd:.6f}',
            ))
        state['plan'] = output.plan.model_dump()
        state['diagnostic_plan'] = output.diagnostic_plan
        state['route'] = list(output.route)
        self._emit_trace(state, trace_step(
            node_id='planning_subagent.route_planner',
            node_name='PlanningSubAgent',
            node_type='subgraph',
            layer='Planning SubAgent',
            status='success',
            input_summary=f'question={request.question[:120]}',
            output_summary=(
                f'intent={output.plan.intent}, '
                f'data={output.trace.get("requires_data")}, '
                f'rag={output.plan.rag_required}, '
                f'prediction={output.plan.prediction_required}, '
                f'safety={output.plan.safety_required}'
            ),
        ))
        return self._return_state(state)

    @staticmethod
    def _route_after_supervisor(state: AgentState) -> str:
        plan = RootManufacturingGraph._plan_model(state.get('plan'))
        if not plan:
            return 'response_synthesis'
        if plan.asset_context_required or plan.process_condition_required or plan.failure_mode_required or plan.risk_priority_required or plan.prediction_required:
            return 'manufacturing_analysis'
        if plan.rag_required:
            return 'evidence_retrieval'
        if plan.safety_required or plan.safety_gate_required:
            return 'safety'
        return 'response_synthesis'

    def _manufacturing_analysis_node(self, state: AgentState) -> AgentState:
        request = self._request_model(state)
        plan = self._plan_model(state.get('plan'))
        if not plan:
            return self._return_state(state)
        prediction: PredictionResponse | None = None
        if plan.prediction_required and request.process_data:
            prediction = self.prediction_service.predict(request.process_data)
            self._emit_trace(state, trace_step(
                node_id='manufacturing_analysis.prediction_tool',
                node_name='Prediction Tool',
                node_type='tool',
                layer='Manufacturing Analysis',
                status='success',
                output_summary=f'risk={prediction.risk_level}, failure={prediction.predicted_failure}',
            ))
        elif plan.prediction_required:
            self._emit_trace(state, trace_step(
                node_id='manufacturing_analysis.prediction_tool',
                node_name='Prediction Tool',
                node_type='tool',
                layer='Manufacturing Analysis',
                status='skipped',
                output_summary='process_data가 없어 예측을 건너뜀',
            ))

        manufacturing_context = self.domain_service.build_context(request, prediction, doc_count=0)
        state['prediction'] = prediction.model_dump() if prediction else None
        state['manufacturing_context'] = manufacturing_context.model_dump()
        self._emit_trace(state, trace_step(
            node_id='manufacturing_analysis.context_builder',
            node_name='Manufacturing Analysis',
            node_type='subgraph',
            layer='Manufacturing Analysis',
            status='success',
            output_summary=(
                f'equipment={manufacturing_context.asset_context.equipment_type}, '
                f'conditions={len(manufacturing_context.process_conditions)}, '
                f'failure_modes={len(manufacturing_context.failure_modes)}, '
                f'priority={manufacturing_context.risk_assessment.overall_priority}'
            ),
        ))
        return self._return_state(state)

    @staticmethod
    def _route_after_manufacturing(state: AgentState) -> str:
        plan = RootManufacturingGraph._plan_model(state.get('plan'))
        if plan and plan.rag_required:
            return 'evidence_retrieval'
        if plan and (plan.safety_required or plan.safety_gate_required):
            return 'safety'
        return 'response_synthesis'

    def _evidence_retrieval_node(self, state: AgentState) -> AgentState:
        request = self._request_model(state)
        plan = self._plan_model(state.get('plan'))
        if not plan:
            return self._return_state(state)
        prediction = self._prediction_model(state.get('prediction'))
        manufacturing_context = self._manufacturing_context_model(state.get('manufacturing_context'))
        if not manufacturing_context:
            manufacturing_context = self.domain_service.build_context(request, prediction, doc_count=0)

        output = self.rag_evidence_subagent.invoke(RagEvidenceInput(
            request=request,
            plan=plan,
            prediction=prediction,
            manufacturing_context=manufacturing_context,
            top_k=min(max(request.top_k or 5, 1), AGENT_MAX_RAG_TOP_K),
        ))

        state['plan'] = output.plan.model_dump()
        state['route'] = list(output.route)
        state['replan_count'] = int(state.get('replan_count') or 0) + output.replan_count_delta
        state['evidence_grade'] = output.evidence_grade.model_dump()
        state['retrieved_documents'] = [item.model_dump() for item in output.retrieved_documents]
        state['citations'] = output.citations
        state['manufacturing_context'] = output.manufacturing_context.model_dump()
        state['rag_evidence'] = {
            'trace': output.trace,
            'warnings': output.warnings,
        }
        state['warnings'].extend(warning for warning in output.warnings if warning not in state['warnings'])
        self._emit_trace(state, trace_step(
            node_id='retrieval.rag_evidence_subagent',
            node_name='RAG Evidence SubAgent',
            node_type='subgraph',
            layer='Evidence Retrieval',
            status='success',
            input_summary=','.join(output.trace.get('query_spec_names') or []),
            output_summary=f'backend={output.trace.get("retrieval_backend")}, selected={len(output.retrieved_documents)}, citations={len(output.citations)}',
        ))
        self._emit_trace(state, trace_step(
            node_id='rag_evidence.evidence_grader',
            node_name='RAG Evidence Grader',
            node_type='validator',
            layer='RAG Evidence SubAgent',
            status='success',
            output_summary=f'usable={output.evidence_grade.usable}, usable_chunks={output.evidence_grade.usable_chunks}',
        ))
        return self._return_state(state)

    @staticmethod
    def _route_after_retrieval(state: AgentState) -> str:
        plan = RootManufacturingGraph._plan_model(state.get('plan'))
        if plan and (plan.safety_required or plan.safety_gate_required):
            return 'safety'
        return 'response_synthesis'

    def _safety_node(self, state: AgentState) -> AgentState:
        output = self.safety_subagent.invoke(SafetyInput(
            request=self._request_model(state),
            prediction=self._prediction_model(state.get('prediction')),
            manufacturing_context=self._manufacturing_context_model(state.get('manufacturing_context')),
            retrieved_documents=self._rag_chunks(state.get('retrieved_documents')),
            structured_answer_payload=dict(state.get('structured_answer_payload') or {}),
        ))
        state['manufacturing_context'] = output.manufacturing_context.model_dump()
        state['structured_answer_payload'] = output.structured_answer_payload
        state['safety_guidance'] = output.safety_guidance
        state['safety_warnings'] = output.safety_warnings
        self._emit_trace(state, trace_step(
            node_id='safety_subagent.policy',
            node_name='SafetySubAgent',
            node_type='subgraph',
            layer='Safety SubAgent',
            status='success',
            output_summary=f'gates={output.trace.get("safety_gate_count")}, actions={output.trace.get("recommended_action_count")}',
        ))
        return self._return_state(state)

    def _response_synthesis_node(self, state: AgentState) -> AgentState:
        request = self._request_model(state)
        plan = self._plan_model(state.get('plan'))
        if not plan:
            return self._return_state(state)
        prediction = self._prediction_model(state.get('prediction'))
        contexts = self._rag_chunks(state.get('retrieved_documents'))
        manufacturing_context = self._manufacturing_context_model(state.get('manufacturing_context')) or self.domain_service.build_context(request, prediction, doc_count=len(contexts))
        payload = dict(state.get('structured_answer_payload') or {})
        action_items = self.recommendation_builder.to_action_dicts(payload.get('recommended_actions') or self.recommendation_builder.collect_action_phrases(prediction, manufacturing_context))
        action_titles = [item['title'] for item in action_items]
        safety_guidance = state.get('safety_guidance')
        warnings = list(state.get('safety_warnings') or [])
        if prediction and prediction.input_warnings:
            warnings.extend(prediction.input_warnings)

        answer: str | None = None
        report: str | None = None
        llm_error: str | None = None
        audit_feedback: list[str] = []
        llm_used = False

        def collect_usage(record: LLMUsageRecord) -> None:
            state['usage_records'].append(record)
            self._emit_trace(state, trace_step(
                node_id='audit.usage_meter',
                node_name='Usage Meter',
                node_type='metric',
                layer='Audit / Persistence',
                status='success',
                output_summary=f'{record.operation}: input={record.input_tokens}, output={record.output_tokens}, cost=${record.estimated_cost_usd:.6f}',
            ))

        for llm_attempt in range(AGENT_MAX_REPLAN_ATTEMPTS + 1):
            llm_result = self.llm_service.generate_json(
                schema_name='manufacturing_domain_agent_response',
                schema=ANSWER_SCHEMA,
                system_prompt=self._answer_system_prompt(),
                payload=self.structured_payload_builder.build(request=request, plan=plan, prediction=prediction, manufacturing_context=manufacturing_context, contexts=contexts, action_titles=action_titles, safety_guidance=safety_guidance, audit_feedback=audit_feedback),
                model=request.llm_model,
                operation='answer_generation',
                usage_callback=collect_usage,
            )
            if llm_result:
                answer = str(llm_result.get('answer') or '').strip() or None
                safety_guidance = llm_result.get('safety_guidance') or safety_guidance
                llm_actions = llm_result.get('recommended_actions') or []
                if isinstance(llm_actions, list):
                    merged_titles = list(dict.fromkeys([str(a) for a in llm_actions if str(a).strip()] + action_titles))
                    action_items = self.recommendation_builder.to_action_dicts(merged_titles)
                    action_titles = [item['title'] for item in action_items]
                llm_warnings = llm_result.get('warnings') or []
                if isinstance(llm_warnings, list):
                    warnings = list(dict.fromkeys(warnings + [str(w) for w in llm_warnings if str(w).strip()]))
                llm_used = True
                validation = self.safety_validator.validate_answer(answer or '', manufacturing_context)
                self._emit_trace(state, trace_step(
                    node_id='response.answer_composer',
                    node_name='Response Synthesis Subgraph',
                    node_type='llm',
                    layer='Response Synthesis',
                    status='success' if validation.passed else 'failed',
                    output_summary=f'attempt={llm_attempt + 1}, safety_passed={validation.passed}',
                ))
                if validation.passed:
                    break
                warnings.extend(validation.errors)
                audit_feedback = validation.errors
                answer = None
                report = None
                llm_used = False
                if llm_attempt < AGENT_MAX_REPLAN_ATTEMPTS:
                    plan = self.diagnostic_planner.replan(request, plan, validation.errors, attempt=llm_attempt + 1)
                    state['plan'] = plan.model_dump()
                    state['route'] = list(plan.required_nodes)
                    state['replan_count'] = int(state.get('replan_count') or 0) + 1
                    self._emit_trace(state, trace_step(
                        node_id='planning_subagent.replan',
                        node_name='PlanningSubAgent Replan',
                        node_type='router',
                        layer='Planning SubAgent',
                        status='success',
                        output_summary='안전 검증 실패를 반영해 재계획',
                        replan_reason='answer_safety_validation_failed',
                    ))
                    continue
                raise UnsafeResponseError('; '.join(validation.errors))

            llm_error = self.llm_service.last_error
            retryable = llm_error and any(token in llm_error.lower() for token in ['json', 'schema', 'unterminated', 'parse'])
            self._emit_trace(state, trace_step(
                node_id='response.answer_composer',
                node_name='Response Synthesis Subgraph',
                node_type='llm',
                layer='Response Synthesis',
                status='failed',
                output_summary=f'LLM 응답 사용 불가: {llm_error or "unknown"}',
            ))
            if retryable and llm_attempt < AGENT_MAX_REPLAN_ATTEMPTS:
                audit_feedback = [f'LLM structured output parse failed: {llm_error}']
                state['replan_count'] = int(state.get('replan_count') or 0) + 1
                continue
            break

        if not answer:
            raise LLMUnavailableError(llm_error or 'LLM did not return a usable answer')

        state['manufacturing_context'] = manufacturing_context.model_dump()
        payload['recommended_actions'] = action_items
        state['structured_answer_payload'] = payload
        state['safety_guidance'] = safety_guidance
        state['answer'] = self._append_reference_details(answer, state.get('citations') or [], manufacturing_context)
        state['report'] = report
        state['warnings'] = self._public_warning_lines((state.get('warnings') or []) + warnings)
        state['llm_used'] = llm_used
        state['llm_error'] = llm_error
        return self._return_state(state)

    def _response_packager_node(self, state: AgentState) -> AgentState:
        request = self._request_model(state)
        contexts = self._rag_chunks(state.get('retrieved_documents'))
        citations = list(state.get('citations') or [])
        response = AgentResponse(
            run_id=state['run_id'],
            user_id=request.user_id,
            session_id=request.session_id,
            route=state.get('route') or [],
            answer=self._sanitize_public_answer(state.get('answer') or ''),
            prediction=self._prediction_model(state.get('prediction')),
            manufacturing_context=self._manufacturing_context_model(state.get('manufacturing_context')),
            retrieved_documents=contexts,
            safety_guidance=state.get('safety_guidance'),
            report=state.get('report'),
            citations=citations,
            warnings=self._public_warning_lines(state.get('warnings') or []),
            trace=to_agent_trace_steps(state.get('trace') or []),
            saved=True,
            plan=self._plan_model(state.get('plan')),
            llm_used=bool(state.get('llm_used')),
            llm_provider=LLM_PROVIDER,
            llm_model=request.llm_model or self.llm_service.model,
            llm_usage=self._usage_summary(state.get('usage_records') or []),
            llm_error=state.get('llm_error'),
            context_used=self._context_metadata(request.user_context, request.user_id),
            **self._prediction_metadata(state),
        )
        self._emit_trace(state, trace_step(
            node_id='response.response_packager',
            node_name='Response Packager',
            node_type='subgraph',
            layer='Response Synthesis',
            status='success',
            output_summary=f'route_nodes={len(response.route)}, citations={len(citations)}',
        ))
        state['citations'] = citations
        state['response'] = response.model_dump()
        return self._return_state(state)

    def _focus_updater_node(self, state: AgentState) -> dict[str, Any]:
        response = self._response_model(state.get('response'))
        output = self.memory_subagent.invoke(MemoryInput(
            request=self._request_model(state),
            response=response,
            answer_memory_context={
                'intent_gateway': state.get('intent_gateway') or {},
                'formatter_context': state.get('formatter_context') or {},
                'structured_answer_payload': state.get('structured_answer_payload') or {},
                'context_resolution': state.get('context_resolution') or {},
                'selected_path': state.get('selected_path'),
            },
            recent_turns=list(state.get('recent_turns') or []),
            recent_turn_routes=list(state.get('recent_turn_routes') or []),
            turn_process_data=state.get('turn_process_data'),
            user_id=state['user_id'],
        ))
        state['last_answer_memory'] = output.last_answer_memory
        state['recent_turn_routes'] = output.recent_turn_routes
        state['recent_turns'] = output.recent_turns
        if output.session_last_process_data:
            state['session_last_process_data'] = output.session_last_process_data
        if output.warnings:
            state['warnings'] = list(dict.fromkeys((state.get('warnings') or []) + output.warnings))
        state['memory_diagnostics'] = output.diagnostics
        self._emit_trace(state, trace_step(
            node_id='memory_subagent.answer_memory_writer',
            node_name='MemorySubAgent',
            node_type='memory',
            layer='Memory SubAgent',
            status='success',
            output_summary=f'focus={output.trace.get("focus") or "none"}, actions={output.trace.get("recommended_action_count")}',
        ))
        return self._return_state(state)

    def _audit_persistence_node(self, state: AgentState) -> AgentState:
        response = self._response_model(state.get('response'))
        request = self._request_model(state)
        self._emit_trace(state, trace_step(
            node_id='audit.memory_writer',
            node_name='Memory Writer',
            node_type='storage',
            layer='Audit / Persistence',
            status='success',
            output_summary='history/memory updated',
        ))
        if response.run_id == state['run_id']:
            response.trace = to_agent_trace_steps(state.get('trace') or [])
        else:
            response.trace = to_agent_trace_steps(state.get('trace') or []) + response.trace
        if response.llm_usage and not response.llm_usage.records and state.get('usage_records'):
            response.llm_usage = self._usage_summary(state['usage_records'])
        if response.run_id == state['run_id']:
            self.store.append({'run_id': response.run_id, 'user_id': request.user_id, 'session_id': request.session_id, 'request': request.model_dump(), 'response': response.model_dump()})
        response.context_used = response.context_used or self._context_metadata(request.user_context, request.user_id)
        state['response'] = response.model_dump()
        return self._return_state(state)

    def _response_from_state(self, state: AgentState, *, answer: str, warnings: list[str], route: list[str]) -> AgentResponse:
        request = self._request_model(state)
        return AgentResponse(
            run_id=state['run_id'],
            user_id=request.user_id,
            session_id=request.session_id,
            route=route,
            answer=self._sanitize_public_answer(answer),
            warnings=self._public_warning_lines(warnings),
            trace=to_agent_trace_steps(state.get('trace') or []),
            saved=True,
            llm_used=bool(state.get('usage_records')),
            llm_provider=LLM_PROVIDER,
            llm_model=request.llm_model or self.llm_service.model,
            llm_usage=self._usage_summary(state.get('usage_records') or []),
            context_used=self._context_metadata(request.user_context, request.user_id),
            **RootManufacturingGraph._prediction_metadata(state),
        )

    @staticmethod
    def _usage_summary(records: list[LLMUsageRecord]) -> LLMUsageSummary:
        normalized = [RootManufacturingGraph._usage_record_model(item) for item in (records or [])]
        return LLMUsageSummary(
            calls=len(normalized),
            input_tokens=sum(item.input_tokens for item in normalized),
            output_tokens=sum(item.output_tokens for item in normalized),
            cached_input_tokens=sum(item.cached_input_tokens for item in normalized),
            total_tokens=sum(item.total_tokens for item in normalized),
            estimated_cost_usd=round(sum(item.estimated_cost_usd for item in normalized), 8),
            estimated_cost_krw=round(sum(item.estimated_cost_krw for item in normalized), 2),
            usd_krw_exchange_rate=normalized[-1].usd_krw_exchange_rate if normalized else 0.0,
            records=normalized,
        )

    @staticmethod
    def _public_warning_lines(warnings: list[str]) -> list[str]:
        blocked = [
            '응답 생성 시 금지 표현',
            'forbidden_agent_actions',
            '금지 표현:',
        ]
        normalized: list[str] = []
        seen_keys: set[str] = set()
        for warning in warnings or []:
            text = ' '.join(str(warning or '').split())
            if not text:
                continue
            if any(token in text for token in blocked):
                continue
            key = RootManufacturingGraph._warning_key(text)
            if key not in seen_keys:
                normalized.append(text)
                seen_keys.add(key)
        return normalized[:5]

    @staticmethod
    def _warning_key(text: str) -> str:
        lower = text.lower()
        training_range = '학습 데이터 10~90%' in text or '학습 데이터 범위 밖' in text or 'training data' in lower
        if training_range and ('공구 마모' in text or 'tool wear' in lower):
            return 'tool_wear_training_range'
        if training_range and ('토크' in text or 'torque' in lower):
            return 'torque_training_range'
        if '실제 설비 제어' in text or '자동 정지' in text or '법적 안전 판단' in text:
            return 'agent_disclaimer'
        if 'LOTO/방호 절차' in text:
            return 'conditional_loto'
        return text

    def _clarification_answer(self, *, reason: str, missing_info: str | None = None) -> str:
        return self.formatter_registry.format('clarification', {
            'public_reason': self._safe_public_reason(reason),
            'missing_info': missing_info,
        })

    @staticmethod
    def _ai4i_clarification_answer(status: dict[str, Any]) -> str:
        missing = list(status.get('missing_features') or [])
        ambiguous = list(status.get('ambiguous_features') or [])
        invalid = list(status.get('invalid_features') or [])
        parsed = status.get('parsed_ai4i_features') or {}
        lines = [
            'AI4I 예측에 필요한 입력이 아직 완전하지 않습니다.',
            '',
            '예측을 실행하려면 아래 6개 feature가 모두 유효해야 합니다.',
        ]
        if missing:
            lines.extend(['', '누락된 값', *[f'- {item}' for item in missing]])
        if ambiguous:
            lines.extend(['', '단위나 해석이 불명확한 값', *[f'- {item}' for item in ambiguous]])
        if invalid:
            lines.extend(['', '유효 범위를 벗어난 값', *[f'- {item}' for item in invalid]])
        if parsed:
            parsed_text = ', '.join(f'{key}={value}' for key, value in parsed.items())
            lines.extend(['', f'현재까지 인식한 값: {parsed_text}'])
        lines.extend([
            '',
            '다음 형식으로 다시 보내 주세요.',
            'Type=L/M/H, Air temperature=300.2K, Process temperature=309.0K, Rotational speed=1480rpm, Torque=34Nm, Tool wear=235min',
        ])
        return '\n'.join(lines)

    @staticmethod
    def _meta_feedback_answer(public_context: dict[str, Any]) -> str:
        focus_text = public_context.get('answer_memory_focus')
        if focus_text:
            first = f'맞습니다. 이 경우 "이걸"은 직전 대화의 "{focus_text}"로 해석하는 것이 자연스럽습니다.'
        else:
            first = '맞습니다. 이런 경우에는 직전 대화의 핵심 주제를 먼저 참조해서 지시어를 해석해야 합니다.'
        return (
            f'{first}\n\n'
            '수정 방향은 단순히 이전 실행 이력을 다시 검색하는 것이 아니라, 직전 답변의 핵심 기억을 `AnswerMemory`로 저장하고 다음 턴에서 "이것/이걸/그거" 같은 지시어가 나오면 그 값을 먼저 참조하도록 만드는 것입니다.\n\n'
            '또한 이런 시스템 동작 피드백에는 제조 분석 보고서 형식을 붙이지 않고, 짧게 문제를 인정하고 수정 방향만 설명해야 합니다.'
        )

    @staticmethod
    def _sanitize_public_answer(answer: str) -> str:
        blocked = [
            'resolved=false',
            'resolved_target',
            'question_kind',
            'context_policy',
            'rag_contexts',
            'safety_gates',
            'recent_runs',
            'similar_runs',
            'audit_notes',
            'action_plan',
            'current turn information',
            'current_turn',
            'internal_reason',
            'badrequesterror',
            'invalid_json_schema',
            'run_id',
            'run id',
            'llm usage',
            'model=',
            'llm_model',
            'tokens',
            'cost',
            'calls=',
            'replans',
            're-plans',
            'trace',
            'raw error',
        ]
        lines = []
        for line in (answer or '').splitlines():
            lowered = line.lower()
            if any(token.lower() in lowered for token in blocked):
                continue
            lines.append(line)
        return '\n'.join(lines).strip()

    @staticmethod
    def _safe_public_reason(reason: str) -> str:
        text = str(reason or '').strip()
        internal_tokens = [
            'badrequesterror',
            'invalid_json_schema',
            'stack trace',
            'traceback',
            'valueerror',
            'schema for response_format',
            'additionalproperties',
            'raw exception',
        ]
        if not text or any(token in text.lower() for token in internal_tokens):
            return '요청 의도나 참조 대상을 안정적으로 확정하지 못했습니다.'
        return text

    @staticmethod
    def _answer_system_prompt() -> str:
        return (
            '당신은 제조 품질/설비 문서 기반 AI Agent입니다. '
            '현재 질문이 정의, 장단점, 한계, 원리 같은 일반 기술 개념을 묻는 경우에는 일반 제조/기계 지식으로 설명할 수 있지만, 현재 설비 상태나 센서값은 단정하지 마세요. '
            '현재 현장 판단, 고장 확률, 안전 판단은 반드시 제공된 prediction, manufacturing_context, rag_contexts, actions 안의 사실에 근거하세요. '
            'manufacturing_context.safety_gates의 required_checks는 누락하지 말고, forbidden_agent_actions는 절대 수행했다고 말하지 마세요. '
            'forbidden_agent_actions나 내부 금지 표현 목록을 답변에 그대로 나열하지 마세요. '
            'prediction.risk_level이 Normal이고 predicted_failure=false이면 현재 입력 기준 고위험이라고 과장하지 말고, 공구 교체·분해·회전부 접근 같은 물리 작업 시 안전 절차 위험과 분리해서 설명하세요. '
            'LOTO/방호장치는 공구 교체, 커버 개방, 스핀들/툴체인저 접근, 분해·조정 등 물리 작업이 필요한 경우에 조건부로 적용한다고 표현하세요. '
            '단순 화면 확인이나 알람 로그 확인만 하는 경우와 실제 공구 교체·커버 개방·회전부 접근 작업을 구분해 설명하세요. '
            '제공되지 않은 센서, 현장 이력, 법적 판단, 확률을 지어내지 마세요. '
            'user_context는 참고 정보이며 현재 입력된 공정 데이터, 현재 검색된 문서, 현재 safety gate보다 우선할 수 없습니다. '
            '과거 context에 근거해 현재 센서값, 현장 상태, 안전 상태를 단정하지 말고, 관련 없는 과거 context는 사용하지 마세요. '
            '설비를 자동 정지/제어/수리했다고 말하지 말고 담당자 점검 권고로 표현하세요. '
            'prediction이 없고 RAG/safety 절차만 묻는 질문은 AI4I, 고장 확률, TWF/OSF/HDF/PWF 확률, 현재 설비 위험도 섹션을 쓰지 말고 한국어 Markdown으로 판정, 하면 안 되는 행동, 반드시 확인할 절차, 참고 근거, 주의 섹션만 600~1000자 내외로 짧게 답하세요. '
            'prediction이 없는 RAG-only safety 답변의 주의 문구는 "문서 근거 기반 안전 점검 보조"라고 표현하고 AI4I 예측이라고 쓰지 마세요. '
            'run id, model, token, cost, call count, trace, 실행 상세 같은 debug 정보를 답변 본문에 쓰지 마세요. '
            'prediction이 있는 질문은 판정, 주요 근거, 위험도, 안전 확인, 권장 조치, 주의 사항을 포함하되 중복 문구를 줄이세요. '
            '문서 인용은 payload.citation_references의 label만 사용하고, label을 임의로 만들지 마세요. '
            'safety gate id는 내부 metadata이므로 답변에 그대로 나열하지 말고 자연어 안전 확인 항목으로만 반영하세요. '
            '답변 본문에서 인용 문서는 가장 관련 높은 3개 이하로 제한하세요. '
            '문서 ID나 safety gate ID만 단독으로 던지지 말고, 주요 근거 문장에는 가능한 경우 source 또는 문서 제목을 함께 언급하세요. '
            '사용자가 보고서 형식이나 리포트 형식을 요청하면 별도 report 필드를 만들지 말고 answer 본문을 간결한 Markdown 보고서 스타일로 작성하세요. '
            'report 필드는 항상 null로 두세요.'
        )

    @staticmethod
    def _append_reference_details(answer: str, citations: list[dict[str, Any]], manufacturing_context: ManufacturingContext) -> str:
        sections: list[str] = []
        citation_lines = RootManufacturingGraph._citation_reference_lines(citations)
        if citation_lines and '참조 문서' not in (answer or ''):
            sections.append('참조 문서\n' + '\n'.join(citation_lines))
        if not sections:
            return answer
        return answer.rstrip() + '\n\n' + '\n\n'.join(sections)

    @staticmethod
    def _citation_reference_lines(citations: list[dict[str, Any]]) -> list[str]:
        lines: list[str] = []
        seen: set[str] = set()
        for index, citation in enumerate(citations or [], start=1):
            label = str(citation.get('label') or citation.get('doc_id') or citation.get('chunk_id') or f'ref-{index}')
            source = str(citation.get('source') or 'unknown')
            title = str(citation.get('title') or citation.get('document') or citation.get('doc_id') or 'Untitled document')
            key = f'{label}:{source}:{title}'
            if key in seen:
                continue
            seen.add(key)
            details = [f'source={source}']
            if citation.get('doc_type'):
                details.append(f'doc_type={citation["doc_type"]}')
            if citation.get('doc_id'):
                details.append(f'doc_id={citation["doc_id"]}')
            line = f'- [{label}] {title} ({", ".join(details)})'
            lines.append(line)
            if len(lines) >= 3:
                break
        return lines

    @staticmethod
    def _context_metadata(context: dict | None, user_id: str | None = None) -> dict | None:
        if not context:
            return None
        return {
            'user_id': user_id,
            'session_id': (context.get('session_context') or {}).get('session_id'),
            'recent_runs_count': len(context.get('recent_runs') or []),
            'similar_runs_count': len(context.get('similar_runs') or []),
            'memories_count': len(context.get('long_term_memory') or []),
            'estimated_context_tokens': context.get('estimated_context_tokens', 0),
            'context_policy': context.get('context_policy') or {},
            'process_data_reference_policy': context.get('process_data_reference_policy') or {},
            'ai4i_feature_status': context.get('ai4i_feature_status') or {},
            'context_resolution': context.get('context_resolution') or {},
            'context_validation_warnings': context.get('context_validation_warnings') or [],
        }

    @staticmethod
    def _prediction_metadata(state: dict[str, Any]) -> dict[str, Any]:
        status = state.get('ai4i_feature_status') or {}
        prediction_called = bool(state.get('prediction'))
        return {
            'prediction_called': prediction_called,
            'prediction_skip_reason': None if prediction_called else status.get('prediction_skip_reason'),
            'missing_features': [] if prediction_called else list(status.get('missing_features') or []),
            'ambiguous_features': [] if prediction_called else list(status.get('ambiguous_features') or []),
            'parsed_ai4i_features': dict(status.get('parsed_ai4i_features') or {}),
        }

    def _emit_trace(self, state: dict[str, Any], step: dict[str, Any]) -> None:
        append_trace(state, step)
        if self._progress_callback:
            self._progress_callback(to_agent_trace_steps([step])[0])

    @staticmethod
    def _thread_config(*, user_id: str, session_id: str) -> dict[str, Any]:
        thread_id = build_thread_id(user_id=user_id, session_id=session_id)
        return {'configurable': {'thread_id': thread_id, 'user_id': user_id, 'session_id': session_id}}

    def _checkpoint_values(self, *, user_id: str, session_id: str) -> dict[str, Any]:
        try:
            snapshot = self.graph.get_state(self._thread_config(user_id=user_id, session_id=session_id))
        except Exception:
            return {}
        values = dict(snapshot.values or {})
        if values.get('state_schema_version') != 2:
            return {}
        return values

    @staticmethod
    def _return_state(state: dict[str, Any]) -> dict[str, Any]:
        clean = RootManufacturingGraph._sanitize_value(state)
        clean['state_schema_version'] = 2
        return clean

    @staticmethod
    def _recommended_action_titles(state: AgentState) -> list[str]:
        actions = ((state.get('structured_answer_payload') or {}).get('recommended_actions') or [])
        titles: list[str] = []
        for action in actions:
            if isinstance(action, dict):
                title = action.get('title') or action.get('text') or action.get('action')
            else:
                title = str(action)
            if title:
                titles.append(str(title))
        return titles

    @staticmethod
    def _reference_note(state: AgentState, term: str | None = None) -> str | None:
        resolution = state.get('context_resolution') or {}
        if not resolution.get('is_followup'):
            return None
        target = resolution.get('followup_target') or term
        if not target:
            return None
        followup_type = resolution.get('followup_type')
        if followup_type in {'previous_concept', 'previous_answer_reason', 'previous_claim'}:
            return f'직전 답변의 "{target}"{RootManufacturingGraph._object_particle(str(target))} 기준으로 답변하겠습니다.'
        return None

    @staticmethod
    def _object_particle(text: str) -> str:
        if not text:
            return '을'
        code = ord(text[-1])
        if 0xAC00 <= code <= 0xD7A3:
            return '을' if (code - 0xAC00) % 28 else '를'
        return '를'

    @staticmethod
    def _sanitize_value(value: Any) -> Any:
        if isinstance(value, BaseModel):
            return RootManufacturingGraph._sanitize_value(value.model_dump())
        if isinstance(value, dict):
            return {str(k): RootManufacturingGraph._sanitize_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [RootManufacturingGraph._sanitize_value(item) for item in value]
        if isinstance(value, tuple):
            return [RootManufacturingGraph._sanitize_value(item) for item in value]
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    @staticmethod
    def _send_request_model(state: dict[str, Any]) -> AgentSendRequest:
        value = state.get('send_request') or {}
        if isinstance(value, AgentSendRequest):
            return value
        return AgentSendRequest.model_validate(value)

    @staticmethod
    def _request_model(state: dict[str, Any]) -> AgentRequest:
        value = state.get('request') or {}
        if isinstance(value, AgentRequest):
            return value
        return AgentRequest.model_validate(value)

    @staticmethod
    def _response_model(value: Any) -> AgentResponse:
        if isinstance(value, AgentResponse):
            return value
        return AgentResponse.model_validate(value)

    @staticmethod
    def _plan_model(value: Any) -> AgentPlan | None:
        if not value:
            return None
        if isinstance(value, AgentPlan):
            return value
        return AgentPlan.model_validate(value)

    @staticmethod
    def _prediction_model(value: Any) -> PredictionResponse | None:
        if not value:
            return None
        if isinstance(value, PredictionResponse):
            return value
        return PredictionResponse.model_validate(value)

    @staticmethod
    def _manufacturing_context_model(value: Any) -> ManufacturingContext | None:
        if not value:
            return None
        if isinstance(value, ManufacturingContext):
            return value
        return ManufacturingContext.model_validate(value)

    @staticmethod
    def _rag_chunks(value: Any) -> list[RagChunk]:
        chunks: list[RagChunk] = []
        for item in value or []:
            if isinstance(item, RagChunk):
                chunks.append(item)
            else:
                chunks.append(RagChunk.model_validate(item))
        return chunks

    @staticmethod
    def _usage_record_model(value: Any) -> LLMUsageRecord:
        if isinstance(value, LLMUsageRecord):
            return value
        return LLMUsageRecord.model_validate(value)
