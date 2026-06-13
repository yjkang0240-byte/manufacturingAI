from __future__ import annotations

from typing import Any

from app.schemas.agent import AgentPlan, AgentRequest
from app.schemas.domain import ManufacturingContext
from app.schemas.prediction import PredictionResponse

from app.agent.heavy.rag_schemas import RetrievalRequest


INTERNAL_QUERY_TOKENS = {
    'maintenance_manual',
    'troubleshooting_guide',
    'safety_standard',
    'failure_mode_catalog',
    'metadata',
    'planner',
    'route',
    'internal',
}


class RagFanoutPolicy:
    """Builds bounded manufacturing evidence query specs from a primary request."""

    max_query_specs = 4

    def build(
        self,
        primary: RetrievalRequest,
        *,
        request: AgentRequest,
        plan: AgentPlan,
        manufacturing_context: ManufacturingContext,
    ) -> list[dict[str, Any]]:
        profile = self.profile(request=request, plan=plan, manufacturing_context=manufacturing_context)
        filters = primary.filters
        base = RagQueryPlanner.sanitize_query(request.question or primary.query)
        seed = self._query_seed(request, manufacturing_context) or base
        primary_top_k = min(primary.top_k, 3) if profile == 'concept_explanation' else primary.top_k
        specs = [{
            'name': 'primary',
            'query': base,
            'top_k': primary_top_k,
            'filters': filters,
            'intent': 'primary',
            'profile': profile,
        }]
        modes = {mode.code for mode in manufacturing_context.failure_modes}
        gates = {gate.gate_id for gate in manufacturing_context.safety_gates}
        needs_safety = bool(plan.safety_required or plan.safety_gate_required or gates)
        if needs_safety or gates:
            for gate in manufacturing_context.safety_gates[:2 if profile != 'concept_explanation' else 1]:
                gate_query = self._gate_query(request.question, gate)
                specs.append({
                    'name': f'safety_{gate.gate_id}',
                    'query': RagQueryPlanner.sanitize_query(gate_query),
                    'top_k': self._expanded_top_k(primary.top_k),
                    'filters': filters,
                    'intent': 'safety_gate',
                    'profile': profile,
                    'safety_gate_id': gate.gate_id,
                    'metadata_terms': sorted(self._gate_metadata_terms(gate) | self._title_supplement_terms(request, manufacturing_context)),
                    'allow_restricted': gate.gate_id == 'loto_if_physical_maintenance',
                })
        needs_troubleshooting = profile in {'prediction_plus_rag', 'troubleshooting_rag'} or bool(modes.intersection({'OSF', 'TWF'}))
        if needs_troubleshooting:
            specs.append({
                'name': 'troubleshooting',
                'query': RagQueryPlanner.sanitize_query(f'{seed} troubleshooting machine fault diagnosis'),
                'top_k': self._expanded_top_k(primary.top_k),
                'filters': self._with_filter(filters, doc_type='troubleshooting'),
                'intent': 'troubleshooting',
                'profile': profile,
            })
        if profile == 'prediction_plus_rag' and modes:
            specs.append({
                'name': 'failure_mode',
                'query': RagQueryPlanner.sanitize_query(f'{seed} {" ".join(sorted(modes))} failure mode inspection'),
                'top_k': primary.top_k,
                'filters': self._with_filter(filters, preferred_failure_modes=sorted(modes)),
                'intent': 'failure_mode',
                'profile': profile,
            })
        unique: list[dict[str, Any]] = []
        seen: set[str] = set()
        for spec in specs:
            if spec['name'] in seen:
                continue
            seen.add(spec['name'])
            unique.append(spec)
        return unique[:self.max_query_specs]

    @staticmethod
    def profile(*, request: AgentRequest, plan: AgentPlan, manufacturing_context: ManufacturingContext) -> str:
        if request.process_data or manufacturing_context.failure_modes or manufacturing_context.process_conditions:
            return 'prediction_plus_rag'
        if plan.safety_required or plan.safety_gate_required or manufacturing_context.safety_gates:
            return 'rag_only_safety'
        if 'troubleshooting_guide' in set(plan.document_scope or []):
            return 'troubleshooting_rag'
        return 'concept_explanation'

    @staticmethod
    def _expanded_top_k(top_k: int) -> int:
        return min(max(int(top_k or 5) * 4, 12), 20)

    @staticmethod
    def _gate_query(seed: str, gate) -> str:
        parts = [seed, getattr(gate, 'name_ko', ''), getattr(gate, 'description_ko', '')]
        parts.extend((getattr(gate, 'required_checks', None) or [])[:4])
        parts.extend((getattr(gate, 'document_search_terms', None) or [])[:8])
        parts.extend(getattr(gate, 'triggered_by', None) or [])
        return ' '.join(str(part) for part in parts if part).strip()

    @staticmethod
    def _gate_metadata_terms(gate) -> set[str]:
        terms: set[str] = set()
        terms.update(RagQueryPlanner._salient_terms(getattr(gate, 'gate_id', '')))
        terms.update(RagQueryPlanner._salient_terms(getattr(gate, 'name_ko', '')))
        terms.update(RagQueryPlanner._salient_terms(getattr(gate, 'description_ko', '')))
        for check in (getattr(gate, 'required_checks', None) or [])[:4]:
            terms.update(RagQueryPlanner._salient_terms(check))
        for term in getattr(gate, 'document_search_terms', None) or []:
            terms.update(RagQueryPlanner._salient_terms(term))
        for trigger in getattr(gate, 'triggered_by', None) or []:
            terms.update(RagQueryPlanner._salient_terms(trigger))
        return terms

    @staticmethod
    def _title_supplement_terms(request: AgentRequest, manufacturing_context: ManufacturingContext) -> set[str]:
        terms = set(RagQueryPlanner._salient_terms(request.question))
        asset = manufacturing_context.asset_context
        terms.update(RagQueryPlanner._salient_terms(asset.equipment_label_ko))
        for value in [asset.equipment_type, *asset.inferred_subsystems, *asset.inferred_components]:
            terms.update(RagQueryPlanner._salient_terms(value))
        return terms

    @staticmethod
    def _with_filter(filters: dict[str, Any] | None, **updates: Any) -> dict[str, Any]:
        merged = dict(filters or {})
        merged.update({key: value for key, value in updates.items() if value is not None})
        return merged

    @staticmethod
    def _query_seed(request: AgentRequest, manufacturing_context: ManufacturingContext) -> str:
        terms: list[str] = []
        terms.extend(RagQueryPlanner._salient_terms(RagQueryPlanner.sanitize_query(request.question)))
        for condition in manufacturing_context.process_conditions:
            terms.extend(RagQueryPlanner._salient_terms(f'{condition.tag} {condition.label_ko} {condition.source_feature or ""}'))
        for mode in manufacturing_context.failure_modes:
            terms.extend(RagQueryPlanner._salient_terms(' '.join([mode.code, mode.name_ko, *mode.related_features, *mode.related_subsystems, *mode.recommended_checks[:3]])))
        for term in manufacturing_context.document_search_terms[:12]:
            terms.extend(RagQueryPlanner._salient_terms(term))
        return RagQueryPlanner.sanitize_query(' '.join(dict.fromkeys(terms)))[:500]


class RagQueryPlanner:
    """Plans retrieval queries only; it never executes retrieval."""

    def plan(
        self,
        *,
        request: AgentRequest,
        planned_query: str,
        prediction: PredictionResponse | None,
        manufacturing_context: ManufacturingContext,
        top_k: int,
        filters: dict | None = None,
    ) -> RetrievalRequest:
        parts = [self.sanitize_query(request.question or planned_query or '')]
        if planned_query and planned_query != request.question:
            parts.extend(sorted(self._salient_terms(self.sanitize_query(planned_query))))
        intent_filters = dict(filters or {})
        infer_filters = filters is None
        if prediction:
            parts.extend(prediction.predicted_modes)
            parts.extend([feature.feature for feature in prediction.evidence_features])
            parts.extend(prediction.recommended_actions[:4])
            if infer_filters and prediction.predicted_modes:
                intent_filters['preferred_failure_modes'] = prediction.predicted_modes
        parts.extend(manufacturing_context.document_search_terms)
        mode_codes = [mode.code for mode in manufacturing_context.failure_modes]
        if mode_codes:
            parts.extend(mode_codes)
            if infer_filters:
                intent_filters.setdefault('preferred_failure_modes', mode_codes)
        safety_gates = [gate.gate_id for gate in manufacturing_context.safety_gates]
        if safety_gates:
            if infer_filters:
                intent_filters.setdefault('preferred_safety_gates', safety_gates)
        context_terms = self._required_context_terms(request, prediction, manufacturing_context)
        if infer_filters and context_terms:
            intent_filters['required_context_terms'] = sorted(context_terms)
        if request.inspection_notes:
            parts.append(request.inspection_notes)
        query = self.sanitize_query(' '.join(part for part in parts if part).strip()) or 'manufacturing safety maintenance troubleshooting'
        return RetrievalRequest(
            query=query,
            top_k=top_k,
            filters=intent_filters,
            reason='request.question primary query plus sanitized planned/domain/prediction hints.',
        )

    @staticmethod
    def sanitize_query(text: str) -> str:
        tokens: list[str] = []
        for raw in str(text or '').split():
            normalized = raw.strip('[](){}:,.=/').lower()
            normalized = normalized.replace('-', '_')
            if normalized in INTERNAL_QUERY_TOKENS:
                continue
            if normalized.replace('_', ' ') in {token.replace('_', ' ') for token in INTERNAL_QUERY_TOKENS}:
                continue
            tokens.append(raw)
        return ' '.join(tokens).strip()

    @staticmethod
    def _required_context_terms(request: AgentRequest, prediction: PredictionResponse | None, context: ManufacturingContext) -> set[str]:
        terms = RagQueryPlanner._salient_terms(request.question)
        if prediction:
            for feature in prediction.evidence_features:
                terms.update(RagQueryPlanner._salient_terms(f'{feature.feature} {feature.tag or ""}'))
            terms.update(mode.lower() for mode in prediction.predicted_modes)
        for condition in context.process_conditions:
            terms.update(RagQueryPlanner._salient_terms(f'{condition.tag} {condition.label_ko} {condition.source_feature or ""}'))
        for mode in context.failure_modes:
            terms.update(RagQueryPlanner._salient_terms(' '.join([mode.code, mode.name_ko, *mode.recommended_checks[:3]])))
        for gate in context.safety_gates:
            terms.update(RagQueryPlanner._salient_terms(f'{gate.gate_id} {gate.name_ko}'))
        return terms

    @staticmethod
    def _salient_terms(text: str) -> set[str]:
        stopwords = {
            'ai4i', 'type', 'air', 'temperature', 'process', 'rotational', 'speed',
            '어떤', '있어', '대한', '확인', '점검', '절차', '해야', '하는지', '알려줘',
            '데이터', '가능성', '예측', '교체', '전에', '항목',
            'check', 'high', 'low', 'normal', 'min', 'max', 'data', 'model', 'false', 'true',
            'maintenance_manual', 'troubleshooting_guide', 'safety_standard', 'failure_mode_catalog',
            'metadata', 'planner', 'route', 'internal',
            'manual', 'guide', 'standard', 'catalog',
        }
        terms: set[str] = set()
        for raw in str(text or '').replace('_', ' ').replace('-', ' ').split():
            token = raw.strip('[](){}:,.=/').lower().rstrip('이가은는을를에의와과도')
            if len(token) >= 2 and token not in stopwords and not token.replace('.', '', 1).isdigit():
                terms.add(token)
                if all('가' <= char <= '힣' for char in token) and len(token) >= 3:
                    terms.add(token[:2])
        return terms
