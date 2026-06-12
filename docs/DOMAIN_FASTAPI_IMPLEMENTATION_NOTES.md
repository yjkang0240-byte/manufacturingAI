# 제조 특화 FastAPI 구현 내역 및 보완점

## 1. 반영한 기획

`manufacturing_agent_domain_specialization_plan.md`의 핵심 요구를 FastAPI 서버 코드에 반영했다.

반영 항목:

```text
1. 설비 계층 모델
2. 고장모드 카탈로그
3. 위험도 산정 체계
4. 안전 게이트
5. 조치 카탈로그
6. 문서 메타데이터 정책
7. 제조 업무 흐름 기반 Supervisor
8. 실행 경로까지 평가하는 골든 데이터셋 구조
```

---

## 2. 새로 추가한 도메인 설정 파일

```text
ai_server/domain/
  equipment_taxonomy.yaml
  failure_mode_catalog.yaml
  safety_gate_matrix.yaml
  action_catalog.yaml
  report_templates.yaml
  document_policy.yaml
```

### 2.1 `equipment_taxonomy.yaml`

제조 설비를 다음 구조로 이해하기 위한 설정이다.

```text
Factory → Line → Equipment → Subsystem → Component
```

예시:

```text
CNC
 ├─ Spindle
 ├─ Tool Changer
 ├─ Coolant System
 ├─ Servo Motor
 └─ Control Panel
```

### 2.2 `failure_mode_catalog.yaml`

AI4I 고장모드인 `TWF/HDF/PWF/OSF/RNF`를 제조 업무 의미로 확장했다.

각 고장모드에는 다음이 들어간다.

```text
- 한글 이름
- 설명
- 관련 공정 변수 태그
- 증상
- 권장 점검
- 필요한 안전 게이트
- 관련 하위 설비
- 보고서 섹션
```

### 2.3 `safety_gate_matrix.yaml`

정비/점검 전에 반드시 확인해야 하는 안전 게이트를 정의했다.

예시:

```text
- loto_if_maintenance
- rotating_parts_guard_check
- hot_surface_warning
- electrical_isolation_if_panel_open
- emergency_response
```

### 2.4 `action_catalog.yaml`

고장모드와 공정 조건에 따라 어떤 조치를 추천해야 하는지 정의했다.

조치에는 다음 속성이 포함된다.

```text
- applicable_failure_modes
- related_features
- requires_machine_stop
- requires_loto
- requires_authorized_person
- priority
- output_phrase
```

---

## 3. 새로 추가한 Agent 계층

기존 구조는 다음과 같았다.

```text
Supervisor
 ├─ Prediction Tool
 ├─ RAG Search Agent
 ├─ Safety Ops Agent
 ├─ Explanation Agent
 └─ Report Agent
```

이번 버전은 다음 구조로 확장했다.

```text
Manufacturing Supervisor
 ├─ Asset Context Agent
 ├─ Process Condition Agent
 ├─ Failure Mode Agent
 ├─ Risk & Priority Agent
 ├─ Procedure Retrieval Agent
 ├─ Safety Gate Agent
 ├─ Action Planner Agent
 ├─ Report Agent
 └─ Evaluation / Audit Agent
```

구현 파일:

```text
ai_server/app/services/manufacturing_domain_agents.py
ai_server/app/services/supervisor_service.py
ai_server/app/agent/graph.py
```

---

## 4. Agent별 구현 내용

| Agent | 구현 내용 |
|---|---|
| Manufacturing Supervisor | 예측/문서검색/안전/보고서 여부를 제조 업무 관점으로 분기 |
| Asset Context Agent | 질문에서 CNC, Spindle, Tool Changer, Coolant System 등 설비 범위 추론 |
| Process Condition Agent | AI4I 예측 근거를 `torque_high`, `tool_wear_high` 같은 태그로 변환 |
| Failure Mode Agent | 고장모드 카탈로그와 예측 결과를 결합해 OSF/TWF/HDF 등 후보 생성 |
| Risk & Priority Agent | 품질/설비/안전/생산/문서근거 위험도 분리 산정 |
| Procedure Retrieval Agent | 제조 Context에 맞게 RAG query와 검색 profile 구성 |
| Safety Gate Agent | LOTO, 회전부 방호, 고온, 전기, 비상대응 게이트 산출 |
| Action Planner Agent | 고장모드와 안전 게이트에 맞는 점검 조치 순서 생성 |
| Evaluation / Audit Agent | 금지 표현, 안전 게이트 누락, 보고서 완성도 점검 |

---

## 5. API 변경점

### 5.1 신규 도메인 확인 API

```text
GET /domain/summary
GET /domain/failure-modes
GET /domain/safety-gates
GET /domain/actions
```

### 5.2 Agent API 응답 확장

`POST /agent/send` 응답에 다음 필드를 추가했다.

```text
manufacturing_context
  asset_context
  process_conditions
  failure_modes
  risk_assessment
  safety_gates
  action_plan

audit
```

---

## 6. 테스트한 내용

```text
- Python compile 검사
- 샘플 RAG 문서 인덱싱
- AI4I 모델 학습
- FastAPI TestClient /health 확인
- FastAPI TestClient /domain/summary 확인
- FastAPI TestClient /agent/send 확인
- LLM-only 구조에서는 안전 검증 실패를 재계획/재시도 후 차단하도록 정리 필요
- manufacturing_context 생성 확인
- safety_gates 생성 확인
- action_plan 생성 확인
- report 생성 확인
- audit 생성 확인
```

---

## 7. 보완해야 할 점

### 7.1 실제 LLM 호출 검증

외부 API Key가 없으면 실제 OpenAI/LLM 호출은 검증할 수 없다.  
현재 구조에서는 API Key가 없는 Agent 실행을 `llm_unavailable`로 실패시킨다.

### 7.2 RAG 검색 고도화

현재 RAG는 제한 환경에서도 안정적으로 실행되도록 lightweight lexical scorer를 사용한다.

실서비스에서는 다음 중 하나로 교체하는 것이 좋다.

```text
- Chroma
- FAISS
- PostgreSQL + pgvector
- Supabase pgvector
```

### 7.3 실제 문서 수집

현재 포함된 RAG 문서는 데모용 샘플 요약 문서다.

실제 프로젝트에서는 다음 자료를 추가 수집해야 한다.

```text
- Haas 실제 Operator Manual
- Haas Troubleshooting Guide
- OSHA Emergency Action Plan
- OSHA Machine Guarding
- OSHA Lockout/Tagout
- KOSHA 기술문서 가이드
- KOSHA 안전자료
```

### 7.4 사내 데이터 적용

실제 회사용 Agent로 만들려면 아래 자료가 필요하다.

```text
- 사내 설비 매뉴얼
- 실제 점검 보고서 양식
- 실제 안전 절차서
- 실제 설비 분류체계
- 실제 P&ID/도면
- 실제 알람/정비 이력
```

### 7.5 LangGraph 실제 라이브러리 그래프화

현재는 LangGraph-style 실행 구조다.  
각 Agent 함수가 명확히 분리되어 있으므로 실제 `StateGraph` 노드로 전환 가능하다.

---

## 8. 최종 상태

이번 버전은 다음 수준까지 구현했다.

```text
제조 문서 RAG + 예측 Agent
→ 설비/고장모드/안전게이트/조치계획/보고서 흐름을 이해하는 제조 특화 FastAPI Agent
```

즉, 단순 제조 챗봇이 아니라 **제조 현장 업무 절차를 반영한 Agent 서버**로 개선했다.
