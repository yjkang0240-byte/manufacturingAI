# FastAPI 제조 특화 Agent 구현 내역 및 보완점

## 1. 반영한 기획

사용자가 요청한 “제조 Agent만의 특별한 설계” 강화를 반영하여, 기존 FastAPI MVP에 다음 구조를 추가했다.

```text
설비 계층 모델
고장모드 카탈로그
위험도 산정 체계
안전 게이트
조치 카탈로그
문서 메타데이터/검색 정책
제조 업무 흐름 기반 Supervisor
실행 경로까지 평가하는 골든 데이터셋 구조
```

---

## 2. 새로 추가한 도메인 설정 파일

| 파일 | 역할 |
|---|---|
| `ai_server/domain/equipment_taxonomy.yaml` | CNC, 일반 설비, 하위 시스템, 부품, hazard 정의 |
| `ai_server/domain/failure_mode_catalog.yaml` | AI4I 고장모드 TWF/HDF/PWF/OSF/RNF와 점검·안전 게이트 연결 |
| `ai_server/domain/safety_gate_matrix.yaml` | LOTO, 회전부 방호, 고온, 전기 격리, 비상대응, 담당자 검토 게이트 정의 |
| `ai_server/domain/action_catalog.yaml` | 공구 마모 점검, 토크 부하 조건 점검, 냉각계통 점검 등 조치 후보 정의 |
| `ai_server/domain/report_templates.yaml` | 점검/정비 보고서 섹션 정의 |
| `ai_server/domain/document_policy.yaml` | 상황별 문서 검색 범위와 우선 출처 정책 정의 |

---

## 3. 새로 추가/수정한 FastAPI 코드

| 경로 | 변경 내용 |
|---|---|
| `ai_server/app/services/domain_service.py` | 제조 도메인 설정 파일을 읽어 설비/공정조건/고장모드/위험도/안전게이트/조치계획 생성 |
| `ai_server/app/services/supervisor_service.py` | 단순 키워드 router에서 Manufacturing Supervisor로 고도화 |
| `ai_server/app/agent/graph.py` | 제조 업무 흐름 기반 실행 그래프 반영 |
| `ai_server/app/schemas.py` | `AssetContext`, `ProcessCondition`, `FailureModeDetail`, `RiskAssessment`, `SafetyGateResult`, `ActionStep`, `ManufacturingContext` 추가 |
| `ai_server/app/services/evaluation_service.py` | route correctness, safety gate compliance, scope control 등 제조 특화 평가 반영 |
| `ai_server/app/main.py` | `/domain/catalog`, `/agent/plan` API 추가 |
| `.env.example` | OpenAI LLM 필수 설정 정리 |
| `README.md` | 실행 방법, 제조 특화 구조, API 예시 업데이트 |

---

## 4. 현재 실행 그래프

```text
0. Input Layer
   └─ Input Normalizer

1. Manufacturing Supervisor Layer
   ├─ Manufacturing Intent Classifier
   └─ Manufacturing Route Planner

2. Asset Context Layer
   └─ Asset Context Agent

3. Process Condition Layer
   └─ Process Condition Agent

4. Failure Mode Layer
   └─ Failure Mode Agent

5. Risk & Priority Layer
   └─ Risk & Priority Agent

6. Procedure Retrieval Layer
   ├─ RAG Query Builder
   └─ Procedure Retrieval Agent

7. Safety Gate Layer
   └─ Safety Gate Agent

8. Action Planning Layer
   └─ Action Planner Agent

9. Reasoning Layer
   └─ Explanation Agent

10. Documentation Layer
   └─ Report Agent

11. Audit & Persistence Layer
   ├─ Evaluation / Audit Agent
   └─ History Store
```

---

## 5. 새 API

### 5.1 도메인 설정 확인

```http
GET /domain/catalog
```

도메인 YAML 설정 전체를 반환한다.

---

### 5.2 실행 계획 미리보기

```http
POST /agent/plan
```

최종 답변을 생성하지 않고, Supervisor route와 `manufacturing_context`만 미리 확인한다.

---

### 5.3 Agent 실행

```http
POST /agent/send
```

권장 메인 API. 사용자 메시지, 공정 데이터, 점검 메모를 받아 제조 Agent 실행 결과를 반환한다.

---

## 6. 테스트 결과

수행한 검증:

```text
python -m compileall app scripts
python scripts/ingest_docs.py --sample-only
FastAPI TestClient /health
FastAPI TestClient /agent/plan
FastAPI TestClient /agent/send
FastAPI TestClient /evaluation/score
```

확인된 동작:

```text
- AI4I 예측 Tool 동작
- 설비 context 추론 동작
- torque_high, tool_wear_high 등 공정조건 태그 생성
- OSF/TWF/HDF/PWF 등 고장모드 카탈로그 매핑
- LOTO, 회전부 방호, 고온, 전기 격리 safety gate 생성
- action_plan 생성
- 보고서 초안 생성
- route correctness / safety gate compliance 평가 동작
```

---

## 7. 현재 보완해야 할 점

## 7.1 RAG 검색 품질

현재 RAG는 MVP 안정성을 위해 경량 lexical 검색을 사용한다.

보완 방향:

```text
Chroma 또는 PostgreSQL pgvector로 교체
문서 chunk embedding 저장
doc_type / equipment_type / subsystem 기반 metadata filter 강화
```

---

## 7.2 실제 문서 수집

현재 샘플 문서는 데모용 요약 문서다.

보완 방향:

```text
Haas 실제 매뉴얼/트러블슈팅 문서 수집
OSHA 실제 안전규정 HTML/PDF 수집
KOSHA 기술문서/안전자료 수집
수집 문서에 equipment/subsystem/component/doc_type metadata 부여
```

---

## 7.3 도메인 규칙 현장화

현재 도메인 YAML은 범용 예시다.

보완 방향:

```text
실제 제조 설비 목록 반영
실제 설비별 하위 부품 반영
사내 LOTO/비상대응 절차 반영
실제 점검표/보고서 양식 반영
```

---

## 7.4 LangGraph 실제 StateGraph 적용

현재는 LangGraph 스타일의 계층형 실행 그래프를 순차 코드로 구현했다.

보완 방향:

```text
langgraph.StateGraph로 각 Agent를 node로 등록
conditional edge로 route 분기 구현
human-in-the-loop checkpoint 추가
retry/re-plan policy 추가
```

---

## 7.5 외부 LLM 실호출 검증

현재 환경에서는 API Key가 없어서 외부 LLM 실호출은 검증하지 않았다.

보완 방향:

```text
.env에 OPENAI_API_KEY 설정
LLM_PROVIDER=openai 설정
/agent/send 실제 LLM 호출 테스트
LLM 응답에서 safety_gates 누락 여부 평가
```

---

## 8. 결론

이번 버전은 기존 MVP를 다음 단계로 끌어올렸다.

```text
기존:
제조 데이터 + 제조 문서 RAG Agent

현재:
설비 계층, 고장모드, 위험도, 안전게이트, 조치계획을 가진 제조 특화 FastAPI Agent
```

아직 실제 공장 수준으로 쓰려면 실제 문서, 실제 설비 taxonomy, 실제 사내 안전절차가 필요하지만, 코드 구조상 그것들을 YAML과 RAG 문서만 교체해 확장할 수 있도록 만들었다.
