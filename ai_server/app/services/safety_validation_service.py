from __future__ import annotations

from dataclasses import dataclass

from app.schemas import ManufacturingContext


CONTROL_FORBIDDEN = [
    '자동으로 정지',
    '정지했습니다',
    '제가 제어',
    '자동 제어',
    '교체했습니다',
    '수리했습니다',
    '안전 상태를 보증',
    '운전 중 점검',
]


@dataclass(frozen=True)
class SafetyValidationResult:
    passed: bool
    errors: list[str]


class SafetyValidationService:
    @staticmethod
    def validate_answer(answer: str, manufacturing_context: ManufacturingContext | None) -> SafetyValidationResult:
        errors: list[str] = []
        normalized = answer or ''
        unsafe_lines = [
            line
            for line in normalized.splitlines()
            if not SafetyValidationService._is_negated_or_policy_line(line)
        ]
        unsafe_text = '\n'.join(unsafe_lines)
        for phrase in CONTROL_FORBIDDEN:
            if phrase in unsafe_text:
                errors.append(f'금지된 설비 제어/보증 표현 감지: {phrase}')

        if manufacturing_context and manufacturing_context.safety_gates:
            for gate in manufacturing_context.safety_gates:
                checks = gate.required_checks[:3]
                has_gate = gate.name_ko in normalized or gate.gate_id in normalized
                has_check = any(check and check in normalized for check in checks)
                if not has_gate and not has_check:
                    errors.append(f'필수 안전 게이트 누락: {gate.gate_id}')

        return SafetyValidationResult(passed=not errors, errors=errors)

    @staticmethod
    def _is_negated_or_policy_line(line: str) -> bool:
        policy_terms = [
            '금지',
            '하지 않습니다',
            '하지 않는다',
            '하지 않',
            '않습니다',
            '대체하지',
            '보증하지',
            '수행하지',
            '제어하지',
        ]
        return any(term in line for term in policy_terms)
