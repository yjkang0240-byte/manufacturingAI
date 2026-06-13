# 제조 특화 FastAPI Agent 구현 내역 및 보완점

## 1. 구현 목표

사용자가 요청한 제조 특화 설계 MD를 FastAPI 기반 코드에 반영했다.

핵심 목표는 단순 제조 문서 RAG 챗봇이 아니라 다음 구조를 갖는 것이다.

```text
설비 계층 모델
+ 고장모드 카탈로그
+ 위험도 산정
+ 안전 게이트
+ 조치 카탈로그
+ 문서 검색 정책
+ 제조 업무 흐름 기반 Supervisor
+ 실행 경로 평가
```

---

## 2. 추가/강화한 파일

### 2.1 제조 도메인 설정 파일

```text
ai_server/domain/equipment_taxonomy.yaml
ai_server/domain/failure_mode_catalog.yaml
ai_server/domain/safety_gate_matrix.yaml
ai_server/domain/action_catalog.yaml
ai_server/domain/report_templates.yaml
ai_server/domain/document_policy.yaml
```

이 파일들은 제조업 지식을 Python 코드에 하드코딩하지 않고 설정 파일로 분리한 것이다.

---

## 3. 구현한 제조 특화 Agent 구조

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
ai_server/app/services/supervisor_service.py
ai_server/app/services/domain_service.py
ai_server/app/agent/graph.py
```

---

## 4. Agent별 구현 내용

| Agent | 구현 내용 |
|---|---|
| Manufacturing Supervisor | 제조 업무 흐름에 맞게 route 생성 |
| Asset Context Agent | CNC, Spindle, Tool Changer, Coolant System 등 설비 범위 추론 |
| Process Condition Agent | AI4I 예측 근거를 torque_high, tool_wear_high 등 태그로 변환 |
| Failure Mode Agent | AI4I 고장모드와 도메인 카탈로그를 연결 |
| Risk & Priority Agent | 품질/설비/안전/생산/문서 근거 위험도를 분리 산정 |
| Procedure Retrieval Agent | 문서 검색 query에 설비/고장모드/조치/안전 게이트를 반영 |
| Safety Gate Agent | LOTO, 회전부 방호, 고온, 전기 격리, 비상대응 게이트 선택 |
| Action Planner Agent | 고장모드와 공정 조건에 맞는 점검 조치 계획 생성 |
| Report Agent | 제조 점검/정비 보고서 초안 생성 |
| Evaluation / Audit Agent | route, safety gate, forbidden action 기준 평가 |

---

## 5. API 변경점

### 5.1 신규 도메인 API

```text
GET /domain/summary
GET /domain/catalog
GET /domain/failure-modes
GET /domain/safety-gates
GET /domain/actions
```

### 5.2 Agent 계획 미리보기 API

```text
POST /agent/plan
```

Supervisor가 어떤 route와 manufacturing_context를 만들지 미리 확인할 수 있다.

### 5.3 메인 Agent API

```text
POST /agent/send
```

응답에 아래 필드가 포함된다.

```text
plan
route
prediction
manufacturing_context
  asset_context
  process_conditions
  failure_modes
  risk_assessment
  safety_gates
  action_plan
retrieved_documents
answer
report
warnings
trace
```

---

## 6. 검증한 내용

다음 테스트를 수행했다.

```text
python -m compileall app scripts
python scripts/ingest_docs.py --sample-only
python scripts/train_ai4i_model.py
FastAPI TestClient /health
FastAPI TestClient /domain/summary
FastAPI TestClient /domain/catalog
FastAPI TestClient /agent/send
FastAPI TestClient /agent/plan
FastAPI TestClient /evaluation/score
```

검증 결과:

```text
- 컴파일 성공
- 샘플 RAG 문서 인덱싱 성공
- AI4I 모델 학습 성공
- /agent/send 정상 응답 확인
- manufacturing_context 생성 확인
- safety_gates 생성 확인
- action_plan 생성 확인
- report 생성 확인
- evaluation score 응답 확인
```

테스트 질의:

```text
토크가 높고 공구 마모가 큰데 어떤 점검과 안전 절차를 확인해야 해? 보고서도 만들어줘.
```

생성된 주요 route:

```text
Input Normalizer
Manufacturing Intent Classifier
Manufacturing Route Planner
Asset Context Agent
Process Condition Agent
Failure Mode Agent
Risk & Priority Agent
RAG Query Builder
Procedure Retrieval Agent
Safety Gate Agent
Action Planner Agent
Explanation Agent
Report Agent
Evaluation / Audit Agent
History Store
```

생성된 Safety Gate 예시:

```text
loto_if_physical_maintenance
rotating_parts_guard_check
hot_surface_warning
electrical_isolation_check
```

생성된 Action Plan 예시:

```text
공구 마모 상태 점검
토크 부하 조건 점검
회전수/토크/출력 조건 점검
냉각/방열 상태 점검
```

---

## 7. 보완해야 할 점

### 7.1 실제 외부 LLM 실호출 검증

`.env.example`은 외부 LLM 설정을 지원하지만, 실제 API Key가 없어서 실호출은 검증하지 못했다.

실제 사용 시에는 `.env`에 API Key를 넣고 `LLM_PROVIDER=openai` 또는 `openai_compatible`으로 설정해야 한다.

---

### 7.2 RAG 검색 고도화

현재 RAG는 제한 환경에서도 실행되도록 lightweight lexical scorer를 사용한다.

실사용 품질을 높이려면 아래 중 하나로 교체하는 것이 좋다.

```text
Chroma
FAISS
PostgreSQL + pgvector
Supabase pgvector
```

---

### 7.3 실제 공개 문서 수집

현재 RAG 문서는 데모용 샘플 요약 문서다.

실제 Haas/OSHA/KOSHA 문서를 수집하려면 다음 스크립트를 사용한다.

```bash
python scripts/collect_rag_docs.py
python scripts/extract_text.py
python scripts/ingest_docs.py
```

---

### 7.4 사내 데이터 적용

실제 제조 현장 적용을 위해서는 아래 문서가 필요하다.

```text
사내 설비 매뉴얼
실제 점검 보고서 양식
실제 안전 절차서
실제 설비 분류체계
실제 P&ID/도면
실제 알람/정비 이력
```

---

### 7.5 실제 LangGraph StateGraph 전환

현재는 LangGraph-style 구조로 각 Agent를 명확히 분리했다.

실제 LangGraph `StateGraph`로 전환하려면 현재 `graph.py`의 각 단계를 node로 등록하면 된다.

---

## 8. 최종 상태

이번 버전은 다음 수준까지 구현했다.

```text
제조 문서 RAG + 예측 Agent
→ 설비/고장모드/안전게이트/조치계획/보고서 흐름을 이해하는 제조 특화 FastAPI Agent
```

즉, 단순 제조 챗봇이 아니라 **제조 현장 업무 절차를 반영한 Agent 서버**로 개선했다.
