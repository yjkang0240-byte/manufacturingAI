from __future__ import annotations
from app.schemas import ManufacturingContext, PredictionResponse, ProcessData, RagChunk

class ReportService:
    @staticmethod
    def citations(chunks: list[RagChunk]) -> list[dict]:
        return [
            {'source': c.source, 'title': c.document_title, 'url': c.url, 'section': c.section, 'score': c.score}
            for c in chunks
        ]

    def make_report(self, question: str, process_data: ProcessData | None, prediction: PredictionResponse | None, contexts: list[RagChunk], actions: list[str], inspection_notes: str | None, manufacturing_context: ManufacturingContext | None = None) -> str:
        pd = process_data.model_dump() if process_data else None
        lines = ['# 점검/정비 보고서 초안', '']
        lines += ['## 1. 기본 정보', f'- 질문: {question or "-"}', f'- 점검 메모: {inspection_notes or "-"}', '']
        if manufacturing_context:
            asset = manufacturing_context.asset_context
            lines += ['## 2. 대상 설비/서브시스템', f'- 설비 유형: {asset.equipment_label_ko} ({asset.equipment_type})', f'- 하위 시스템: {", ".join(asset.inferred_subsystems) or "미지정"}', f'- 추정 근거: {asset.rationale}', '']
        else:
            lines += ['## 2. 대상 설비/서브시스템', '- 미지정', '']
        lines += ['## 3. 입력 공정 데이터', f'```json\n{pd}\n```' if pd else '- 공정 데이터 없음', '']
        lines += ['## 4. 예측 결과']
        if prediction:
            lines += [f'- 위험도: {prediction.risk_level}', f'- 고장 확률: {prediction.failure_probability:.2%}', f'- 고장모드: {", ".join(prediction.predicted_modes) or "미확정"}']
        else:
            lines += ['- 예측 결과 없음']
        if manufacturing_context:
            lines += ['', '## 5. 고장모드 분석']
            if manufacturing_context.failure_modes:
                for f in manufacturing_context.failure_modes:
                    lines.append(f'- {f.code} / {f.name_ko}: {f.description_ko}')
            else:
                lines.append('- 고장모드 후보 없음')
            risk = manufacturing_context.risk_assessment
            lines += ['', '## 6. 위험도 평가', f'- 품질 위험: {risk.quality.level}', f'- 설비 위험: {risk.equipment.level}', f'- 안전 위험: {risk.safety.level}', f'- 생산 위험: {risk.production.level}', f'- 종합 우선순위: {risk.overall_priority}', f'- 담당자 검토 필요: {risk.escalation_required}']
            lines += ['', '## 7. 안전 게이트 확인']
            if manufacturing_context.safety_gates:
                for gate in manufacturing_context.safety_gates:
                    lines.append(f'### {gate.name_ko}')
                    lines.extend([f'- 확인: {x}' for x in gate.required_checks])
                    lines.extend([f'- 금지: {x}' for x in gate.forbidden_agent_actions[:3]])
            else:
                lines.append('- 필수 안전 게이트 없음')
        lines += ['', '## 8. 권장 조치']
        if manufacturing_context and manufacturing_context.action_plan:
            for i, a in enumerate(manufacturing_context.action_plan, 1):
                lines.append(f'{i}. {a.label_ko}: {a.output_phrase}')
                lines.append(f'   - LOTO: {a.requires_loto}, 설비 정지 필요: {a.requires_machine_stop}, 담당자 필요: {a.requires_authorized_person}')
        else:
            lines += [f'- {a}' for a in actions]
        lines += ['', '## 9. 근거 문서']
        if contexts:
            lines += [f'- {c.source} / {c.document_title} / {c.url or "no-url"}' for c in contexts]
        else:
            lines += ['- 검색된 근거 문서 없음']
        lines += ['', '## 10. 담당자 확인 필요 사항', '- 공개 데이터·문서 기반 초안이므로 실제 현장 절차와 사내 기준을 반영해 검토해야 합니다.', '- AI는 설비를 제어하거나 안전 상태를 보증하지 않습니다.']
        return '\n'.join(lines)
