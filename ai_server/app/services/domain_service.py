from __future__ import annotations

from pathlib import Path
from typing import Any
import re
import yaml

from app.config import DOMAIN_DIR
from app.schemas.agent import AgentRequest
from app.schemas.domain import (
    ActionStep,
    AssetContext,
    FailureModeDetail,
    ManufacturingContext,
    ProcessCondition,
    RiskAssessment,
    RiskAxis,
    SafetyGateResult,
)
from app.schemas.prediction import PredictionResponse

TOKEN_RE = re.compile(r'[가-힣A-Za-z0-9_+.-]+')

FEATURE_TAGS = {
    'Air temperature': 'air_temperature_high',
    'Process temperature': 'process_temperature_high',
    'Rotational speed': 'rpm_condition',
    'Torque': 'torque_high',
    'Tool wear': 'tool_wear_high',
}

CONDITION_LABELS = {
    'air_temperature_high': '공기 온도 높음',
    'process_temperature_high': '공정 온도 높음',
    'rpm_high': '회전수 높음',
    'rpm_low': '회전수 낮음',
    'rpm_condition': '회전수 조건 주의',
    'torque_high': '토크 높음',
    'tool_wear_high': '공구 마모 높음',
    'emergency': '비상상황 키워드',
}

MAINTENANCE_WORDS = ['정비', '점검', '교체', '수리', '분해', 'maintenance', 'repair', 'replace', 'inspect']
EMERGENCY_WORDS = ['비상', '화재', '누출', '부상', '대피', 'emergency', 'fire', 'evacuation']

class DomainKnowledgeService:
    """Manufacturing-domain rule and catalog service.

    This is the manufacturing-specific layer requested in the domain plan:
    equipment hierarchy, failure-mode catalog, safety-gate matrix, action catalog,
    document policy, and report templates are loaded from YAML files instead of
    being hard-coded into a generic RAG chatbot.
    """

    def __init__(self, domain_dir: Path | None = None):
        self.domain_dir = domain_dir or DOMAIN_DIR
        self.equipment_taxonomy = self._load_yaml('equipment_taxonomy.yaml')
        self.failure_catalog = self._load_yaml('failure_mode_catalog.yaml')
        self.safety_matrix = self._load_yaml('safety_gate_matrix.yaml')
        self.action_catalog = self._load_yaml('action_catalog.yaml')
        self.report_templates = self._load_yaml('report_templates.yaml')
        self.document_policy = self._load_yaml('document_policy.yaml')

    def _load_yaml(self, name: str) -> dict[str, Any]:
        path = self.domain_dir / name
        if not path.exists():
            return {}
        return yaml.safe_load(path.read_text(encoding='utf-8')) or {}

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {t.lower() for t in TOKEN_RE.findall(text or '')}

    @staticmethod
    def _blob(req: AgentRequest) -> str:
        parts = [req.question or '', req.inspection_notes or '']
        if req.process_data:
            parts += ['공정 데이터', '토크', '공구 마모', '회전수', '온도']
        return ' '.join(parts).lower()

    def build_context(self, req: AgentRequest, prediction: PredictionResponse | None, doc_count: int = 0) -> ManufacturingContext:
        asset = self.infer_asset_context(req)
        process_conditions = self.analyze_process_conditions(req, prediction)
        failure_modes = self.analyze_failure_modes(prediction, process_conditions)
        risk = self.assess_risk(req, prediction, asset, process_conditions, failure_modes, doc_count=doc_count)
        safety_gates = self.select_safety_gates(req, asset, process_conditions, failure_modes, risk)
        actions = self.plan_actions(req, prediction, asset, process_conditions, failure_modes, safety_gates)
        search_terms = self.document_search_terms(asset, process_conditions, failure_modes, safety_gates, actions)
        audit_notes = self.audit_notes(req, risk, safety_gates, prediction)
        return ManufacturingContext(
            asset_context=asset,
            process_conditions=process_conditions,
            failure_modes=failure_modes,
            risk_assessment=risk,
            safety_gates=safety_gates,
            action_plan=actions,
            document_search_terms=search_terms,
            audit_notes=audit_notes,
        )

    def infer_asset_context(self, req: AgentRequest) -> AssetContext:
        blob = self._blob(req)
        equipment_config = (self.equipment_taxonomy.get('equipment') or {})
        best_equipment = 'GeneralMachine'
        best_score = 0
        matched_subsystems: list[str] = []
        matched_components: list[str] = []
        hazards: list[str] = []

        for eq_name, eq in equipment_config.items():
            aliases = [str(a).lower() for a in eq.get('aliases', [])]
            score = sum(1 for a in aliases if a and a in blob)
            subsystems = eq.get('subsystems') or {}
            subs_for_eq: list[str] = []
            comps_for_eq: list[str] = []
            hazards_for_eq: list[str] = []
            for sub_name, sub in subsystems.items():
                sub_aliases = [str(a).lower() for a in sub.get('aliases', [])]
                if any(a and a in blob for a in sub_aliases):
                    score += 3
                    subs_for_eq.append(sub_name)
                    comps_for_eq.extend([str(c) for c in sub.get('components', []) if str(c).lower() in blob or any(k in blob for k in [str(c).lower()])])
                    hazards_for_eq.extend(sub.get('safety_hazards', []) or [])
            if score > best_score:
                best_score = score
                best_equipment = eq_name
                matched_subsystems = subs_for_eq
                matched_components = comps_for_eq
                hazards = hazards_for_eq

        if not matched_subsystems and req.process_data:
            matched_subsystems = ['Spindle', 'Tool Changer']
            hazards = ['rotating_parts', 'pinch_point']
        if not matched_subsystems:
            matched_subsystems = ['Safety System'] if any(w in blob for w in ['안전', '비상', 'loto', '방호', '가드']) else []

        label = 'CNC 계열 설비' if best_equipment == 'CNC' else '일반 산업 설비'
        confidence = min(0.95, 0.35 + 0.12 * best_score + (0.2 if req.process_data else 0.0))
        rationale = '질문 키워드와 설비 taxonomy를 기반으로 설비 범위를 추정했습니다.'
        return AssetContext(
            equipment_type=best_equipment,
            equipment_label_ko=label,
            inferred_subsystems=list(dict.fromkeys(matched_subsystems)),
            inferred_components=list(dict.fromkeys(matched_components)),
            hazards=list(dict.fromkeys(hazards)),
            confidence=round(confidence, 3),
            rationale=rationale,
        )

    def analyze_process_conditions(self, req: AgentRequest, prediction: PredictionResponse | None) -> list[ProcessCondition]:
        conditions: list[ProcessCondition] = []
        if prediction:
            for e in prediction.evidence_features:
                tag = FEATURE_TAGS.get(e.feature, e.feature.lower().replace(' ', '_'))
                if e.feature == 'Rotational speed':
                    tag = 'rpm_low' if e.direction == 'low' else 'rpm_high' if e.direction == 'high' else 'rpm_condition'
                label = CONDITION_LABELS.get(tag, tag)
                sev = 'high' if e.direction in {'high', 'low'} else 'medium'
                conditions.append(ProcessCondition(tag=tag, label_ko=label, severity=sev, source_feature=e.feature, value=e.value, explanation=e.reason))
        elif req.process_data:
            pd = req.process_data
            heuristics = [
                ('torque_high', '토크 높음', pd.torque_nm, pd.torque_nm >= 55, '토크가 높은 편이므로 부하 조건 점검이 필요할 수 있습니다.'),
                ('tool_wear_high', '공구 마모 높음', pd.tool_wear_min, pd.tool_wear_min >= 180, '공구 마모 시간이 누적되어 마모 점검이 필요할 수 있습니다.'),
                ('air_temperature_high', '공기 온도 높음', pd.air_temperature_k, pd.air_temperature_k >= 301, '공기 온도가 높은 편입니다.'),
                ('process_temperature_high', '공정 온도 높음', pd.process_temperature_k, pd.process_temperature_k >= 310, '공정 온도가 높은 편입니다.'),
                ('rpm_low', '회전수 낮음', pd.rotational_speed_rpm, pd.rotational_speed_rpm <= 1400, '회전수가 낮아 토크 부하와 함께 확인이 필요합니다.'),
                ('rpm_high', '회전수 높음', pd.rotational_speed_rpm, pd.rotational_speed_rpm >= 1800, '회전수가 높아 출력 조건을 확인할 필요가 있습니다.'),
            ]
            for tag, label, value, cond, exp in heuristics:
                if cond:
                    conditions.append(ProcessCondition(tag=tag, label_ko=label, severity='medium', value=value, explanation=exp))
        return list({c.tag: c for c in conditions}.values())

    def analyze_failure_modes(self, prediction: PredictionResponse | None, conditions: list[ProcessCondition]) -> list[FailureModeDetail]:
        catalog = (self.failure_catalog.get('failure_modes') or {})
        condition_tags = {c.tag for c in conditions}
        codes: list[tuple[str, float, str]] = []
        if prediction:
            for m in prediction.failure_modes:
                if m.predicted or m.code in prediction.predicted_modes or m.probability >= 0.25:
                    codes.append((m.code, float(m.probability), 'prediction_tool'))
        # Add deterministic manufacturing hints even if the classifier did not select them.
        if {'torque_high', 'tool_wear_high'} <= condition_tags:
            codes.append(('OSF', 0.55, 'condition_rule'))
        if 'tool_wear_high' in condition_tags:
            codes.append(('TWF', 0.45, 'condition_rule'))
        if {'air_temperature_high', 'process_temperature_high'} & condition_tags:
            codes.append(('HDF', 0.4, 'condition_rule'))
        if 'torque_high' in condition_tags and ({'rpm_high', 'rpm_low'} & condition_tags):
            codes.append(('PWF', 0.35, 'condition_rule'))
        if not codes and prediction and prediction.predicted_failure:
            codes.append(('RNF', 0.3, 'default_prior'))

        merged: dict[str, tuple[float, str]] = {}
        for code, conf, source in codes:
            if code not in catalog:
                continue
            if code not in merged or conf > merged[code][0]:
                merged[code] = (conf, source)
        result: list[FailureModeDetail] = []
        for code, (conf, source) in sorted(merged.items(), key=lambda x: x[1][0], reverse=True):
            info = catalog.get(code) or {}
            result.append(FailureModeDetail(
                code=code,
                name_ko=info.get('name_ko', code),
                description_ko=info.get('description_ko', ''),
                confidence=round(conf, 3),
                related_features=info.get('related_features', []) or [],
                related_subsystems=info.get('related_subsystems', []) or [],
                recommended_checks=info.get('recommended_checks', []) or [],
                safety_gates=info.get('safety_gates', []) or [],
                source=source,
            ))
        return result

    def assess_risk(self, req: AgentRequest, prediction: PredictionResponse | None, asset: AssetContext, conditions: list[ProcessCondition], failure_modes: list[FailureModeDetail], doc_count: int = 0) -> RiskAssessment:
        pred_level = (prediction.risk_level if prediction else 'Unknown').lower()
        quality_level = {'critical': 'critical', 'warning': 'high', 'caution': 'medium', 'normal': 'low'}.get(pred_level, 'unknown')
        equipment_level = 'high' if failure_modes and any(f.code in {'OSF', 'PWF', 'HDF'} for f in failure_modes) else 'medium' if failure_modes else 'low'
        blob = self._blob(req)
        emergency = self._has_emergency_intent(blob)
        maintenance_requested = any(w in blob for w in MAINTENANCE_WORDS) or bool(req.inspection_notes)
        physical_maintenance = any(w in blob for w in ['교체', '분해', '수리', '정비', '커버', '접근', 'replace', 'repair', 'disassemble'])
        hazardous_access = any(h in asset.hazards for h in ['rotating_parts', 'pinch_point', 'electrical', 'machine_guarding', 'emergency_stop'])
        safety_level = (
            'critical' if emergency
            else 'high' if physical_maintenance and hazardous_access
            else 'medium' if maintenance_requested or hazardous_access or '안전' in blob
            else 'low'
        )
        production_level = 'high' if quality_level in {'critical', 'high'} and equipment_level in {'high', 'critical'} else 'medium' if failure_modes else 'low'
        doc_level = 'high' if doc_count >= 3 else 'medium' if doc_count >= 1 else 'unknown'
        if prediction is None:
            quality_level = 'not_applicable'
        order = {'not_applicable': 0, 'unknown': 0, 'low': 1, 'conditional': 2, 'medium': 2, 'high': 3, 'critical': 4}
        operation_overall = max([quality_level, equipment_level, production_level], key=lambda x: order.get(x, 0))
        if emergency or operation_overall in {'high', 'critical'}:
            overall = max([operation_overall, safety_level], key=lambda x: order.get(x, 0))
        elif safety_level == 'high':
            overall = 'medium'
        else:
            overall = max([operation_overall, safety_level], key=lambda x: order.get(x, 0))
        escalation = emergency or operation_overall in {'high', 'critical'} or (safety_level == 'high' and physical_maintenance)
        return RiskAssessment(
            quality=RiskAxis(axis='quality', level=quality_level, rationale='AI4I 예측이 있을 때만 품질 위험으로 변환합니다.'),
            equipment=RiskAxis(axis='equipment', level=equipment_level, rationale='고장모드와 설비 하위 시스템 영향을 기준으로 산정했습니다.'),
            safety=RiskAxis(axis='safety', level=safety_level, rationale='현재 운전 위험과 분리해, 공구 교체·분해·회전부 접근 등 물리 작업이 필요한 경우의 절차 위험을 산정했습니다.'),
            production=RiskAxis(axis='production', level=production_level, rationale='품질 위험과 설비 위험이 생산 중단 가능성으로 이어질 수 있는지 평가했습니다.'),
            document_confidence=RiskAxis(axis='document_confidence', level=doc_level, rationale='검색된 근거 문서 수를 기준으로 산정했습니다.'),
            prediction_risk=RiskAxis(
                axis='prediction_risk',
                level='not_applicable' if prediction is None else quality_level,
                rationale='AI4I 예측 결과가 없으면 prediction risk는 적용하지 않습니다.',
            ),
            safety_work_risk=RiskAxis(
                axis='safety_work_risk',
                level='conditional' if physical_maintenance or hazardous_access else 'low',
                rationale='물리 작업, 커버 개방, 회전부 접근이 필요한 경우에만 절차 위험이 있습니다.',
            ),
            overall_priority=overall,
            escalation_required=escalation,
            rationale='현재 운전 위험, AI4I 예측 위험, 물리 정비 작업 시 안전 절차 위험을 분리해 종합 우선순위를 산정했습니다.',
        )

    def select_safety_gates(self, req: AgentRequest, asset: AssetContext, conditions: list[ProcessCondition], failure_modes: list[FailureModeDetail], risk: RiskAssessment) -> list[SafetyGateResult]:
        matrix = (self.safety_matrix.get('safety_gates') or {})
        blob = self._blob(req)
        tags = {c.tag for c in conditions}
        tags.update(f.code for f in failure_modes)
        physical_work = self._gate_triggered(matrix.get('loto_if_physical_maintenance') or {}, blob, tags) or bool(req.inspection_notes)
        rotating_work = self._gate_triggered(matrix.get('rotating_parts_guard_check') or {}, blob, tags)
        gate_ids: list[str] = []
        for f in failure_modes:
            gate_ids.extend(f.safety_gates)
        if physical_work:
            gate_ids.append('loto_if_physical_maintenance')
        if (
            rotating_work
            or
            any(h in asset.hazards for h in ['rotating_parts', 'pinch_point'])
            or any(t in tags for t in ['OSF', 'TWF', 'rpm_high', 'rpm_low'])
            or (physical_work and rotating_work)
        ):
            gate_ids.append('rotating_parts_guard_check')
        if any(t in tags for t in ['HDF', 'air_temperature_high', 'process_temperature_high']) or any(w in blob for w in ['고온', '냉각', '방열']):
            gate_ids.append('hot_surface_warning')
        if any(t in tags for t in ['PWF']) or any(w in blob for w in ['전기', '제어반', '드라이브', 'power', 'electrical']):
            gate_ids.append('electrical_isolation_check')
        if self._has_emergency_intent(blob):
            gate_ids.append('emergency_response')
        if any(f.code == 'RNF' for f in failure_modes):
            gate_ids.append('authorized_person_review')
        if risk.escalation_required and not gate_ids:
            gate_ids.append('authorized_person_review')

        results: list[SafetyGateResult] = []
        for gate_id in list(dict.fromkeys(gate_ids)):
            g = matrix.get(gate_id)
            if not g:
                continue
            triggered = [t for t in (g.get('triggers') or []) if str(t).lower() in blob or str(t) in tags]
            results.append(SafetyGateResult(
                gate_id=gate_id,
                name_ko=g.get('name_ko', gate_id),
                severity=self._normalize_level(g.get('severity', 'medium')),
                description_ko=g.get('description_ko', ''),
                required_checks=g.get('required_checks', []) or [],
                forbidden_agent_actions=g.get('forbidden_agent_actions', []) or [],
                escalation=g.get('escalation'),
                triggered_by=triggered or list(tags & set(g.get('triggers') or [])),
                document_search_terms=g.get('document_search_terms', []) or [],
            ))
        return results

    @staticmethod
    def _gate_triggered(gate: dict[str, Any], blob: str, tags: set[str]) -> bool:
        for trigger in gate.get('triggers') or []:
            text = str(trigger).lower()
            if text in blob or str(trigger) in tags:
                return True
        return False

    def plan_actions(self, req: AgentRequest, prediction: PredictionResponse | None, asset: AssetContext, conditions: list[ProcessCondition], failure_modes: list[FailureModeDetail], safety_gates: list[SafetyGateResult]) -> list[ActionStep]:
        action_config = (self.action_catalog.get('actions') or {})
        failure_codes = {f.code for f in failure_modes}
        cond_tags = {c.tag for c in conditions}
        safety_ids = [g.gate_id for g in safety_gates]
        selected: list[ActionStep] = []
        for action_id, info in action_config.items():
            applicable = set(info.get('applicable_failure_modes') or [])
            evidence = set(info.get('evidence_tags') or [])
            related_subsystems = set(info.get('related_subsystems') or [])
            if (applicable & failure_codes) or (evidence & cond_tags) or (related_subsystems & set(asset.inferred_subsystems)):
                selected.append(ActionStep(
                    action_id=action_id,
                    label_ko=info.get('label_ko', action_id),
                    description_ko=info.get('description_ko', ''),
                    output_phrase=info.get('output_phrase', info.get('label_ko', action_id)),
                    priority=self._normalize_level(info.get('priority', 'medium')),
                    related_failure_modes=list(applicable & failure_codes) or list(applicable),
                    related_subsystems=info.get('related_subsystems', []) or [],
                    requires_machine_stop=bool(info.get('requires_machine_stop', False)),
                    requires_loto=info.get('requires_loto', False),
                    requires_authorized_person=bool(info.get('requires_authorized_person', True)),
                    safety_gate_ids=safety_ids,
                ))
        if any(w in self._blob(req) for w in EMERGENCY_WORDS) and 'check_emergency_plan' in action_config:
            info = action_config['check_emergency_plan']
            selected.insert(0, ActionStep(
                action_id='check_emergency_plan',
                label_ko=info.get('label_ko'),
                description_ko=info.get('description_ko'),
                output_phrase=info.get('output_phrase'),
                priority='critical',
                related_failure_modes=[],
                related_subsystems=info.get('related_subsystems', []) or [],
                requires_machine_stop=False,
                requires_loto=False,
                requires_authorized_person=True,
                safety_gate_ids=safety_ids,
            ))
        if not selected and prediction:
            for idx, phrase in enumerate(prediction.recommended_actions[:4], 1):
                selected.append(ActionStep(
                    action_id=f'prediction_recommended_{idx}',
                    label_ko=phrase,
                    description_ko='예측 도구가 제안한 기본 점검 항목입니다.',
                    output_phrase=phrase,
                    priority='medium',
                    related_failure_modes=prediction.predicted_modes,
                    safety_gate_ids=safety_ids,
                ))
        if not selected:
            selected.append(ActionStep(
                action_id='request_more_data',
                label_ko='추가 데이터 및 담당자 확인',
                description_ko='명확한 고장모드가 없으므로 추가 데이터와 현장 담당자 검토가 필요합니다.',
                output_phrase='추가 공정 데이터, 경보 이력, 점검 메모를 확인한 뒤 담당자가 점검 필요 여부를 판단하세요.',
                priority='medium',
                requires_authorized_person=True,
                safety_gate_ids=safety_ids,
            ))
        priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3, 'unknown': 4}
        selected = sorted({a.action_id: a for a in selected}.values(), key=lambda x: priority_order.get(x.priority, 9))
        return selected[:8]

    def document_search_terms(self, asset: AssetContext, conditions: list[ProcessCondition], failure_modes: list[FailureModeDetail], safety_gates: list[SafetyGateResult], actions: list[ActionStep]) -> list[str]:
        terms: list[str] = [asset.equipment_type, asset.equipment_label_ko]
        terms.extend(asset.inferred_subsystems)
        terms.extend(asset.inferred_components)
        terms.extend(c.label_ko for c in conditions)
        for f in failure_modes:
            terms.extend([f.code, f.name_ko])
            terms.extend(f.recommended_checks[:3])
        for g in safety_gates:
            terms.append(g.name_ko)
            terms.extend(g.document_search_terms[:8])
        for a in actions:
            terms.append(a.label_ko)
        terms.extend(['troubleshooting', 'preventive maintenance', 'safety procedure'])
        return [t for t in dict.fromkeys(str(x) for x in terms if x)][:30]

    def audit_notes(self, req: AgentRequest, risk: RiskAssessment, safety_gates: list[SafetyGateResult], prediction: PredictionResponse | None = None) -> list[str]:
        if prediction:
            notes = ['이 답변은 AI4I 예측과 문서 근거 기반 점검 보조이며 실제 설비 제어·자동 정지·법적 안전 판단을 대체하지 않습니다.']
        else:
            notes = ['이 답변은 문서 근거 기반 안전 점검 보조이며, 실제 설비 제어·자동 정지·법적 안전 판단을 대체하지 않습니다. 물리적 정비, 커버 개방, 회전부 접근이 필요한 경우에는 현장 절차와 자격 있는 담당자 확인이 우선입니다.']
        if safety_gates:
            notes.append('공구 교체, 커버 개방, 회전부 접근 등 물리 작업이 필요한 경우에만 현장 LOTO/방호 절차를 적용하세요.')
        if risk.escalation_required:
            notes.append('물리적 정비나 교체가 필요하면 자격 있는 담당자 또는 안전관리자 확인이 필요합니다.')
        return notes

    @staticmethod
    def _has_emergency_intent(blob: str) -> bool:
        compact = blob.replace(' ', '')
        if '비상정지' in compact or 'emergencystop' in compact or 'e-stop' in blob:
            compact = compact.replace('비상정지', '')
            blob = blob.replace('emergency stop', '').replace('e-stop', '')
        emergency_terms = ['화재', '누출', '부상', '대피', 'emergency', 'fire', 'evacuation']
        return any(term in blob for term in emergency_terms) or '비상상황' in compact

    @staticmethod
    def _normalize_level(level: Any) -> str:
        text = str(level or 'medium').lower()
        if text in {'critical', 'high', 'medium', 'low', 'unknown'}:
            return text
        return 'medium'
