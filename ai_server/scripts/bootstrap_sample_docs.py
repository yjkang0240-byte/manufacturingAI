from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / 'data' / 'processed_docs'
PROCESSED.mkdir(parents=True, exist_ok=True)

SAMPLES = [
    {
        'source': 'Haas',
        'document_title': 'CNC Preventive Maintenance Demo Notes',
        'doc_type': 'preventive_maintenance',
        'equipment_type': 'CNC',
        'section': 'Spindle and Tool Changer Preventive Maintenance',
        'language': 'ko',
        'url': 'https://www.haascnc.com/service.html',
        'text': 'CNC 설비 예방정비에서는 냉각수 잔량, 필터 막힘, 펌프 작동음, 공구 교환 장치, 스핀들 부하, 윤활 상태를 정기적으로 확인한다. 공구 마모나 과부하가 의심되면 공구 상태, 스핀들 부하, 회전수와 토크 조건을 확인한다. 정비 또는 수리 절차는 자격 있는 담당자가 수행해야 한다.',
        'metadata': {'subsystem': 'Spindle', 'component': 'tool', 'task_type': 'maintenance', 'risk_type': 'equipment', 'safety_related': True, 'requires_loto': True},
    },
    {
        'source': 'Haas',
        'document_title': 'Coolant System Troubleshooting Demo Notes',
        'doc_type': 'troubleshooting',
        'equipment_type': 'CNC',
        'section': 'Coolant System',
        'language': 'ko',
        'url': 'https://www.haascnc.com/service.html',
        'text': '냉각수 펌프 이상이 의심되면 먼저 냉각수 잔량, 필터 막힘, 배관 막힘, 펌프 작동음을 확인한다. 고온 또는 방열 문제가 의심되면 냉각 계통과 방열 상태를 확인한다.',
        'metadata': {'subsystem': 'Coolant System', 'component': 'pump', 'task_type': 'troubleshooting', 'risk_type': 'equipment', 'safety_related': True, 'requires_loto': 'conditional'},
    },
    {
        'source': 'OSHA',
        'document_title': 'Emergency Action Plan 1910.38 Demo Summary',
        'doc_type': 'safety_procedure',
        'equipment_type': 'general',
        'section': 'Emergency Action Plan',
        'language': 'ko',
        'url': 'https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.38',
        'text': '비상대응계획은 화재 또는 기타 비상상황을 보고하는 절차, 대피 절차, 담당자 역할, 근로자 교육 및 계획 검토 절차를 포함해야 한다. 비상 상황에서는 현장 비상대응계획과 안전관리자의 지시를 우선 따른다.',
        'metadata': {'task_type': 'emergency_response', 'risk_type': 'safety', 'safety_related': True},
    },
    {
        'source': 'OSHA',
        'document_title': 'Machine Guarding 1910.212 Demo Summary',
        'doc_type': 'safety_standard',
        'equipment_type': 'machine',
        'section': 'Machine Guarding',
        'language': 'ko',
        'url': 'https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.212',
        'text': '기계 방호는 작업자를 회전부, 끼임 지점, 절단 지점, 날아오는 칩과 스파크 등의 위험으로부터 보호하기 위한 장치다. 방호 장치에는 배리어 가드, 양수 조작 장치, 전자식 안전장치 등이 포함될 수 있다. 운전 중 회전부 접근은 금지한다.',
        'metadata': {'task_type': 'safety', 'risk_type': 'safety', 'safety_related': True, 'requires_loto': False},
    },
    {
        'source': 'OSHA',
        'document_title': 'Lockout Tagout 1910.147 Demo Summary',
        'doc_type': 'safety_standard',
        'equipment_type': 'machine',
        'section': 'Lockout Tagout',
        'language': 'ko',
        'url': 'https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.147',
        'text': 'Lockout/Tagout은 정비 또는 수리 중 예기치 않은 기동이나 에너지 방출을 방지하기 위한 절차다. 정비 전에는 에너지원 확인, 설비 정지, 에너지 차단, 잠금 및 표지 부착, 잔류 에너지 해소, 무에너지 상태 확인이 필요하다.',
        'metadata': {'task_type': 'maintenance_safety', 'risk_type': 'safety', 'safety_related': True, 'requires_loto': True},
    },
    {
        'source': 'KOSHA',
        'document_title': 'Technical Document Guide Demo Summary',
        'doc_type': 'technical_document_guide',
        'equipment_type': 'general',
        'section': 'Maintenance and Inspection Documentation',
        'language': 'ko',
        'url': 'https://miis.kosha.or.kr/oshci/eng/busi/SmarkGuide.do',
        'text': '설비 기술문서에는 기계 설비 도면, 전기 관련 도면, 유체 및 가스 관련 도면, 사용자 매뉴얼, 안전장치 설명, 인터록 리스트, 비상정지 회로, 점검 간격과 점검 목록, 이상 상황과 대책, 주요 부품 교체 방법, 예비 부품 리스트 등이 포함될 수 있다.',
        'metadata': {'task_type': 'documentation', 'risk_type': 'document_confidence', 'safety_related': True},
    },
    {
        'source': 'KOSHA',
        'document_title': 'Hazardous Machine Classification Demo Summary',
        'doc_type': 'equipment_taxonomy',
        'equipment_type': 'general',
        'section': 'Hazardous Machine and Safety Devices',
        'language': 'ko',
        'url': 'https://miis.kosha.or.kr/oshci/eng/busi/KCsMerchandise.do',
        'text': '위험기계류에는 프레스, 전단기, 프레스 브레이크, 크레인, 리프트, 압력용기, 롤러, 사출성형기, 고소작업대, 곤돌라 등이 포함될 수 있다. 안전장치에는 프레스 및 전단기 안전장치, 과부하 방지장치, 안전밸브, 파열판, 산업용 로봇 안전장치 등이 포함될 수 있다.',
        'metadata': {'task_type': 'taxonomy', 'risk_type': 'safety', 'safety_related': True},
    },
]


def main():
    chunks = []
    for i, sample in enumerate(SAMPLES, 1):
        item = dict(sample)
        item['chunk_id'] = f'sample_{i:03d}_0001'
        chunks.append(item)
    (PROCESSED / 'chunks.jsonl').write_text('\n'.join(json.dumps(c, ensure_ascii=False) for c in chunks), encoding='utf-8')
    print(f'created {len(chunks)} sample chunks')


if __name__ == '__main__':
    main()
