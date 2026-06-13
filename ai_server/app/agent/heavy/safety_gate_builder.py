from __future__ import annotations

from app.schemas.domain import ManufacturingContext


class SafetyGateBuilder:
    """Builds safety guidance and public warnings from domain safety gates."""

    def safety_guidance(self, manufacturing_context: ManufacturingContext) -> str:
        lines: list[str] = []
        for gate in manufacturing_context.safety_gates:
            lines.append(f'### {gate.name_ko}')
            lines.append(f'- 작업 위험도: {gate.severity}')
            if gate.gate_id in {'loto_if_physical_maintenance', 'rotating_parts_guard_check'}:
                lines.append('- 적용 조건: 공구 교체, 커버 개방, 회전부 접근, 분해·조정 등 물리 작업이 필요한 경우')
            lines.append(f'- 설명: {gate.description_ko}')
            for check in gate.required_checks:
                lines.append(f'- 확인: {check}')
            if gate.escalation:
                lines.append(f'- Escalation: {gate.escalation}')
            lines.append('')
        return '\n'.join(lines).strip()

    def warnings(self, manufacturing_context: ManufacturingContext) -> list[str]:
        warnings = list(manufacturing_context.audit_notes)
        if not warnings:
            warnings.append('이 답변은 예측·문서 기반 점검 보조이며 실제 설비 제어·자동 정지·법적 안전 판단을 대체하지 않습니다.')
        return list(dict.fromkeys(warnings))
