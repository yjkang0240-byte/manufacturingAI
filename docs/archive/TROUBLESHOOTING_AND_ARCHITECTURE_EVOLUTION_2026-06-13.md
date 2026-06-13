# 제조 AI Agent 트러블슈팅 및 아키텍처 진화 기록 - 2026-06-13

이 문서는 현재 운영 문서가 아니라, 2026-06-13에 진행된 제조 AI Agent
트러블슈팅, 구조 개선, RAG 복구, 응답 품질 개선 과정을 보존하기 위한
archive 기록이다.

현재 실행 구조를 확인할 때는 아래 문서를 우선 본다.

- `docs/LANGGRAPH_FINAL_ARCHITECTURE.md`
- `docs/CURRENT_BACKEND_ARCHITECTURE_AUDIT.md`
- `docs/rag_evidence_orchestration.md`
- `docs/RAG_INDEX_RUNBOOK.md`

이 문서는 "그동안 무엇이 문제였고, 무엇을 어떻게 고쳤으며, 지금 구조가
어떤 효과를 내는지"를 후속 작업자가 빠르게 이해하도록 돕는 목적이다.

---

## 1. 최종 요약

처음 상태는 다음과 같았다.

```text
FastAPI Agent
  -> RootManufacturingGraph
      -> context
      -> intent/routing
      -> planning
      -> prediction
      -> RAG service/orchestrator
      -> safety
      -> answer/report
      -> memory/history
```

기능은 많았지만 실행 경로가 섞여 있었다.

- RAG Evidence는 Subgraph처럼 불렸지만 실제로는 service class pipeline이었다.
- Root graph가 너무 많은 내부 책임을 직접 들고 있었다.
- AI4I 예측과 RAG-only safety 답변이 섞였다.
- lightweight RAG, legacy retriever, JSONL fallback 같은 오래된 경로가 남아 있었다.
- Chroma vector DB와 JSONL corpus 개수가 달랐다.
- safety gate 검증은 gate id 노출을 요구했고, 사용자 답변에는 gate id를 숨겨야 했다.
- 답변에 run id, model, token, cost 같은 debug 정보가 섞일 수 있었다.
- `generate_report` 옵션 때문에 일반 답변과 report route가 불필요하게 갈라졌다.

최종적으로는 다음 구조로 정리했다.

```text
POST /agent/send
  -> RootManufacturingGraph(StateGraph)
      -> ContextSubAgent(StateGraph)
      -> IntentGateway
      -> PlanningSubAgent(StateGraph)
      -> manufacturing_analysis
      -> RagEvidenceSubAgent(StateGraph)
      -> SafetySubAgent(StateGraph)
      -> response_synthesis
      -> response_packager
      -> MemorySubAgent(StateGraph)
      -> audit_persistence
```

현재 핵심 원칙은 다음과 같다.

- 제품 endpoint는 `/agent/send`.
- `/rag/search`는 API/debug seam.
- Agent 내부 RAG production path는 `RagEvidenceSubAgent` 하나.
- AI4I process data는 prediction input이고 RAG corpus가 아니다.
- RAG corpus는 OSHA, Haas, KOSHA 문서.
- Chroma collection은 `manufacturing_rag`.
- Chroma vector count는 JSONL 기준 727개로 복구.
- 사용자가 보고서 생성을 선택하는 옵션은 제거.
- report 형식 요청은 별도 route가 아니라 일반 answer 스타일로 처리.

---

## 2. 처음 확인된 주요 문제 목록

### 2.1 RAG Evidence 구조 문제

이전에는 `RagEvidenceOrchestrator.run()` 안에서 다음 메서드를 순서대로
호출했다.

```text
query_planning_node
-> evidence_retrieval_node
-> evidence_filtering_node
-> evidence_grading_node
-> citation_building_node
-> evidence_payload_node
-> evidence_trace_node
```

겉으로는 node처럼 보였지만 실제 LangGraph `StateGraph`는 아니었다.
그래서 "Subgraph"라는 문서/이름과 실제 구현이 맞지 않았다.

문제점:

- 테스트가 "그래프"가 아니라 class pipeline만 검증했다.
- RootGraph 입장에서는 RAG Evidence가 독립 SubAgent인지 service인지 모호했다.
- trace에서 `subgraph`라는 표현이 실제 구현보다 과장되어 있었다.
- query planning, retrieval, filtering, grading, citation, payload, trace가
  한 class 안에 모여 유지보수성이 낮았다.

### 2.2 RootGraph 비대화

`RootManufacturingGraph`는 LangGraph였지만, 내부 책임이 너무 많았다.

당시 RootGraph가 직접 다루던 것:

- request context 구성
- follow-up/context resolution
- intent gateway
- supervisor planning
- manufacturing analysis
- prediction 호출
- RAG handoff
- safety gate 구성
- answer synthesis
- documentation/report
- response packaging
- focus update
- memory write
- audit persistence

문제점:

- root graph가 top-level orchestration이 아니라 대부분의 업무 로직을
  직접 아는 구조였다.
- RAG Evidence는 분리됐지만 context/planning/safety/memory는 아직 root에
  강하게 묶여 있었다.
- private helper method가 많아 테스트가 내부 구현에 묶였다.
- route가 늘수록 root graph가 계속 커질 위험이 있었다.

### 2.3 RAG production path 중복

이전에는 여러 RAG 경로가 공존했다.

- `RagService.search()`
- `RagService.search_with_diagnostics()`
- `lightweight_rag_answer`
- legacy `Retriever`
- Chroma retriever
- JSONL lexical fallback
- RAG Evidence orchestrator

문제점:

- 어떤 질문이 어떤 RAG 경로를 타는지 명확하지 않았다.
- Chroma가 비거나 실패하면 JSONL로 조용히 fallback할 수 있었다.
- `/rag/search`와 agent 내부 답변 경로의 책임이 섞였다.
- 테스트는 통과하지만 production path가 하나라고 말하기 어려웠다.

### 2.4 Chroma corpus 불일치

로컬 상태는 다음과 같았다.

```text
ai_server/data/processed/rag_chunks.jsonl: 727 chunks
Chroma manufacturing_rag collection: 702 vectors
missing: 25 chunks
```

누락된 chunk는 Haas spindle troubleshooting 관련 25개로 진단되었다.

문제점:

- RAG 문서 JSONL에는 존재하지만 Chroma 검색 결과에는 나오지 않는 문서가 있었다.
- "Haas spindle load tool wear troubleshooting torque" 류 질문에서 Haas
  troubleshooting 근거가 약해질 수 있었다.
- vector DB가 git ignored라 다른 환경에서 같은 상태를 재현하기 어려웠다.

### 2.5 AI4I routing 문제

AI4I 예측 의도가 있는데 feature가 부족한 경우, 시스템이 RAG-only 답변으로
흘러갈 위험이 있었다.

예:

```text
AI4I Type=M, Torque=34Nm일 때 공구 마모 고장 가능성을 예측해줘.
```

이 질문은 예측 의도가 있지만 6개 필수 feature가 없다.

문제점:

- prediction을 실행할 수 없는데 RAG-only safety 답변이 나오면 사용자는
  예측이 된 것으로 오해할 수 있다.
- 일부 답변에서 AI4I feature가 없는데도 failure probability나 TWF/OSF
  류 표현이 섞일 수 있었다.

### 2.6 답변 품질 문제

실제 샘플 답변을 확인하면서 아래 문제가 보였다.

AI4I + RAG 답변:

- 예측 결과는 Normal인데 종합 위험도가 high/critical처럼 보일 수 있었다.
- prediction risk와 정비 작업 safety risk가 섞였다.
- TWF 보조 점수 표현이 전체 고장 확률과 혼동될 수 있었다.
- KOSHA 고전압 개폐장치 문서처럼 질문과 약한 문서가 주요 근거로 섞일 수 있었다.

RAG-only safety 답변:

- AI4I가 없는데 "AI4I 예측과 문서 근거 기반" disclaimer가 붙었다.
- 단순 safety 절차 질문인데 risk가 critical처럼 표시될 수 있었다.
- 공구 교체/드릴기/방호덮개 질문에서 조선업 일반 점검 문서가 더 앞에 나왔다.
- 답변이 길고 debug 정보가 섞일 수 있었다.

### 2.7 safety validation 충돌

답변 생성 중 다음과 같은 실패가 발생했다.

```text
필수 안전 게이트 누락: rotating_parts_guard_check
HTTP 500
unsafe_response_blocked
```

문제점:

- validator는 safety gate id나 exact required check를 답변에 넣으라고 요구했다.
- 하지만 product 정책은 safety gate id를 사용자-facing answer에 노출하지 않는 것이었다.
- 즉, 안전 검증과 public answer 정책이 충돌했다.

### 2.8 generate_report 문제

UI에는 `보고서 생성` 체크박스가 있었고, API에는 `generate_report`가 있었다.

문제점:

- 일반 답변과 report route가 불필요하게 분리됐다.
- 질문이 "보고서 형식으로 정리해줘"일 때 별도 report node를 탈 수 있었다.
- 긴 보고서 생성은 token/cost를 늘리고 답변 품질을 흐렸다.
- 내부 run 기록은 어차피 trace/history/usage/citation에 남기 때문에,
  사용자가 별도 보고서 생성을 선택할 필요가 크지 않았다.

---

## 3. RAG Evidence SubAgent 전환

### 3.1 이전 구조

이전에는 이름상 "orchestrator/subgraph"였지만 실제 흐름은 다음과 같았다.

```text
RootGraph
  -> _evidence_retrieval_node
      -> RagEvidenceOrchestrator.run()
          -> plan
          -> retrieve
          -> filter
          -> grade
          -> cite
          -> payload
          -> trace
```

문제는 이 흐름이 LangGraph로 컴파일된 Subgraph가 아니라는 점이었다.

### 3.2 수정 방향

새 패키지를 만들었다.

```text
ai_server/app/agent/rag_evidence/
  __init__.py
  state.py
  nodes.py
  subagent.py
```

핵심 구조:

```text
RagEvidenceSubAgent
  -> build_rag_evidence_graph()
  -> StateGraph(RagEvidenceState)
  -> graph.compile()
  -> invoke(input) -> output
```

Node 구성:

```text
plan_queries
retrieve
filter
grade
cite
build_payload
trace
```

### 3.3 설계 원칙

- SubAgent는 반드시 실제 LangGraph `StateGraph`.
- SubAgent 내부 state와 root `AgentState`는 분리.
- public interface는 `invoke(input) -> output` 하나.
- RootGraph는 RAG 내부 node 이름을 몰라도 됨.
- RAG pipeline 로직은 한 곳에만 존재.
- `RagEvidenceOrchestrator` full implementation은 제거 또는 축소.

### 3.4 현재 효과

- RAG Evidence lane이 실제 독립 graph가 되었다.
- trace count, selected chunks, citations가 하나의 state transition으로 관리된다.
- root graph가 RAG 내부 planner/retriever/filter/grader/citation builder를 직접 호출하지 않는다.
- 테스트가 "class method 호출"이 아니라 "graph state transition"을 검증한다.

---

## 4. Context, Planning, Safety, Memory SubAgent 분리

### 4.1 이전 상태

RootGraph는 RAG뿐 아니라 context/planning/safety/memory까지 직접 많은 helper를
가지고 있었다.

문제점:

- root graph가 계속 커졌다.
- 각 단계의 input/output boundary가 흐렸다.
- request-scoped state와 service instance state의 책임이 혼동될 수 있었다.

### 4.2 추가된 SubAgent

다음 SubAgent를 실제 LangGraph `StateGraph`로 분리했다.

```text
ContextSubAgent
PlanningSubAgent
SafetySubAgent
MemorySubAgent
```

각 SubAgent는 자기 state와 input/output contract를 가진다.

### 4.3 ContextSubAgent

책임:

- user/session context 구성
- current turn / previous turn 구분
- previous answer memory 확인
- AI4I feature audit
- context pack 생성
- context validation

주요 효과:

- AI4I feature 추출이 root graph 밖으로 분리됐다.
- "방금 데이터", "이 조건" 같은 후속 질문 처리 기준이 명확해졌다.
- incomplete AI4I prediction request를 clarification으로 보낼 수 있게 됐다.

### 4.4 PlanningSubAgent

책임:

- 질문과 context 기반 실행 계획 구성
- prediction/RAG/safety/action 필요 여부 판단
- `DiagnosticPlan`을 `AgentPlan`으로 변환
- required nodes와 rationale 구성

주요 효과:

- root graph가 keyword policy를 직접 알지 않는다.
- deterministic planning과 optional LLM refinement가 planning boundary 안에 숨겨졌다.
- report route 제거 후에도 보고서 스타일 요청은 일반 answer style로 처리된다.

### 4.5 SafetySubAgent

책임:

- safety context 구성
- safety gate policy 적용
- required/forbidden wording 구성
- response synthesis가 사용할 safety payload 생성

주요 효과:

- RootGraph에서 safety policy internals를 제거했다.
- SafetySubAgent는 최종 답변을 직접 쓰지 않는다.
- RAG 검색이나 prediction을 직접 하지 않는다.

### 4.6 MemorySubAgent

책임:

- answer memory extraction
- focus update
- user/session memory write
- 다음 턴 context에 필요한 memory output 구성

주요 효과:

- focus update와 memory write가 response generation과 분리됐다.
- report preference memory 같은 불필요한 기록도 제거됐다.

---

## 5. Legacy RAG 및 fallback 제거

### 5.1 제거 전 문제

남아 있던 경로:

```text
lightweight_rag_answer
legacy Retriever
JSONL lexical fallback
agent/heavy/chroma_retriever.py
RagService search fallback
```

문제점:

- RAG production path가 하나라고 말하기 어려웠다.
- Chroma 실패를 JSONL 검색으로 조용히 숨길 수 있었다.
- `agent/heavy`가 Chroma infrastructure를 소유하고 있었다.

### 5.2 정리 내용

- `lightweight_rag_answer` 제거.
- legacy `Retriever` 제거.
- JSONL silent fallback 제거.
- `ChromaRetriever`를 `app.services` 계층으로 이동.
- `/rag/search`는 외부 API/debug seam으로 유지.
- RAG Evidence path는 Chroma 중심으로 유지.

### 5.3 현재 정책

```text
Agent internal RAG path:
  RootGraph -> RagEvidenceSubAgent -> RagService -> ChromaRetriever

Debug/API RAG path:
  /rag/search -> RagService
```

Chroma error/empty:

- RAG Evidence path에서 JSONL로 몰래 fallback하지 않는다.
- warnings/diagnostics에 남긴다.
- evidence 부족은 명시적으로 처리한다.

---

## 6. Chroma 702/727 불일치 복구

### 6.1 문제 발견

상태:

```text
rag_chunks.jsonl: 727
Chroma: 702
missing: 25
```

누락 문서:

```text
Haas spindle troubleshooting 관련 chunk 25개
```

### 6.2 진단 기준

확인한 것:

- JSONL count
- unique chunk_id count
- Chroma collection count
- Chroma ids
- JSONL에는 있는데 Chroma에는 없는 ids
- Chroma에는 있는데 JSONL에는 없는 ids
- 누락 chunk의 source/title/doc_type

### 6.3 복구 방식

`rag_chunks.jsonl`을 source of truth로 보고, 기존 indexing script를 이용해
Chroma를 재색인했다.

원칙:

- 외부 다운로드 없음.
- 문서 재수집 없음.
- re-chunking 없음.
- fake embedding 사용 금지.
- 기존 JSONL 기준으로만 indexing.

복구 후:

```text
rag_chunks.jsonl: 727
Chroma vectors: 727
missing: 0
extra: 0
```

### 6.4 runbook 추가

`docs/RAG_INDEX_RUNBOOK.md`에 재현 절차를 남겼다.

핵심 명령:

```bash
cd ai_server
.venv/bin/python scripts/index_rag_chunks_chroma.py --reset
```

효과:

- vector DB가 git ignored여도 다른 환경에서 재생성 가능.
- Haas spindle troubleshooting 검색 가능 여부를 smoke check로 확인 가능.

---

## 7. AI4I feature audit 및 clarification routing

### 7.1 이전 문제

예측 의도가 있지만 feature가 부족한 질문이 RAG-only로 흘러갈 수 있었다.

예:

```text
AI4I Type=M, Torque=34Nm일 때 공구 마모 고장 가능성을 예측해줘.
```

이 질문은 prediction intent가 명확하지만 feature는 2개뿐이다.

### 7.2 개선 내용

AI4I prediction node는 다음 6개 feature가 모두 유효할 때만 호출한다.

```text
Type
Air temperature
Process temperature
Rotational speed
Torque
Tool wear
```

허용 alias:

```text
Air temperature: air_temp, 공기온도, 대기온도
Process temperature: process_temp, 공정온도
Rotational speed: rpm, 회전수, 회전속도
Torque: 토크, 부하토크
Tool wear: tool_wear, 공구마모, 공구 마모 시간
Type: L/M/H, 제품유형, 장비유형
```

단위 처리:

- K, rpm, Nm, min 기본 정규화.
- Celsius가 명시되면 Kelvin 변환.
- 단위 불명확 또는 값 범위 비정상은 clarification.

### 7.3 현재 metadata

응답 metadata:

```text
prediction_called: true/false
prediction_skip_reason:
  - missing_ai4i_features
  - ambiguous_ai4i_features
  - invalid_ai4i_features
missing_features: []
ambiguous_features: []
parsed_ai4i_features: {}
```

### 7.4 효과

- AI4I feature가 부족하면 RAG를 실행하지 않는다.
- `ai4i_clarification_required`로 종료한다.
- 부족하거나 불명확한 feature만 사용자에게 요청한다.
- 예측하지 않은 상황에서 고장 확률/TWF/OSF/HDF/PWF 확률을 만들지 않는다.

---

## 8. Adaptive RAG 1차 개선

### 8.1 문제

초기 RAG 개선 전에는 다음 문제가 있었다.

- LLM/planner 내부 토큰이 retrieval query에 섞였다.
- vector score만 높으면 질문과 직접 관련 없는 문서가 선택될 수 있었다.
- safety gate 문서가 semantic search만으로 충분히 올라오지 않았다.
- 장비명 질문에서 장비 전용 문서보다 일반 업종 문서가 먼저 나올 수 있었다.

### 8.2 route별 retrieval profile

Adaptive RAG profile을 도입했다.

```text
rag_only_safety
prediction_plus_rag
troubleshooting_rag
concept_explanation
```

각 profile의 목적:

`rag_only_safety`

- AI4I 예측 없이 안전/정비 절차를 묻는 질문.
- safety gate 기반 검색 강화.
- evidence는 짧게 제한.

`prediction_plus_rag`

- AI4I prediction 결과와 문서 근거를 함께 사용.
- failure mode, risk tag, safety gate를 retrieval hint로 사용.
- prediction이 Normal이면 위험도를 과장하지 않음.

`troubleshooting_rag`

- Haas 또는 `doc_type=troubleshooting` 문서 우선.
- 물리 점검/정비가 있으면 safety 문서를 보조 근거로 추가.

`concept_explanation`

- top_k를 작게 유지.
- safety/procedure 문서가 필요 없으면 과도하게 검색하지 않음.

### 8.3 query sanitize

제거 대상 내부 토큰:

```text
maintenance_manual
troubleshooting_guide
safety_standard
failure_mode_catalog
metadata
planner
route
internal
```

정책:

- primary query는 사용자 원문을 우선.
- planned query는 salient term 추출용.
- sanitize된 term만 보조 query에 추가.

### 8.4 safety gate metadata/title supplement

YAML 기반 보강:

- `safety_gate_matrix.yaml`의 `triggers`
- `required_checks`
- `document_search_terms`
- gate name/description

검색 보강 대상:

- metadata
- title
- document_title
- safety_gate
- doc_type

중요:

- 특정 doc_id는 하드코딩하지 않았다.
- restricted 문서는 기본 제외.
- LOTO gate가 실제 정비/에너지 차단 질문에 적용될 때만 restricted 후보를 열 수 있다.

### 8.5 evidence selection

vector score보다 강하게 본 것:

- title match
- document_title match
- doc_type match
- safety_gate match
- failure_mode match
- retrieval_scope
- project_priority
- 질문/route와 직접 관련성

낮은 우선순위:

- 본문 일부 단어만 맞는 특정 업종 문서.
- 질문과 title이 직접 맞지 않는 특정 기계 문서.
- 같은 doc_id 여러 chunk.
- 같은 safety_gate 과다 중복.

효과:

- 공구 교체/드릴기/회전부 방호 질문에서 장비명과 제목이 맞는 문서가
  더 앞에 올 수 있다.
- 조선업/신선기 같은 일반 또는 특정 업종 문서가 단어 유사도만으로
  primary evidence가 되는 현상을 줄였다.

---

## 9. Safety gate와 public answer 정책 정리

### 9.1 이전 문제

validator는 다음처럼 실패할 수 있었다.

```text
필수 안전 게이트 누락: rotating_parts_guard_check
```

하지만 public answer에는 safety gate id를 출력하지 않는 것이 정책이었다.

충돌:

```text
validator: gate id 또는 exact check 필요
public answer: gate id 숨김
```

### 9.2 개선 내용

validator를 자연어 coverage 기반으로 수정했다.

허용:

- gate id 직접 언급
- gate name 언급
- required check 직접 언급
- required checks / document_search_terms / description에서 추출된 주요
  safety term이 자연어로 충분히 반영된 경우

거부:

- "일반적인 점검을 수행하세요" 같은 너무 빈약한 표현.
- 필수 gate 의미가 없는 답변.
- forbidden action 위반.

효과:

- 사용자는 gate id를 보지 않는다.
- 답변은 자연어로 안전 절차를 설명한다.
- validator는 실질적 안전 내용이 있는지 확인한다.

---

## 10. RAG-only safety 답변 개선

### 10.1 이전 문제

RAG-only safety 질문 예:

```text
드릴기 작업 전에 공작물 고정 상태, 방호덮개, 비상정지장치를 어떻게 확인해야 하는지 알려줘.
```

문제:

- AI4I가 없는데 "AI4I 예측과 문서 근거 기반" disclaimer가 붙을 수 있었다.
- prediction risk가 없음에도 overall risk가 critical처럼 보일 수 있었다.
- "비상정지장치"를 실제 emergency incident로 오판할 수 있었다.
- run id, model, token, cost, calls 같은 debug 정보가 답변에 섞일 수 있었다.

### 10.2 개선 내용

prediction이 없으면:

```text
prediction_risk = not_applicable
safety_work_risk = conditional
```

RAG-only disclaimer:

```text
이 답변은 문서 근거 기반 안전 점검 보조이며,
실제 설비 제어·자동 정지·법적 안전 판단을 대체하지 않습니다.
물리적 정비, 커버 개방, 회전부 접근이 필요한 경우에는
현장 절차와 자격 있는 담당자 확인이 우선입니다.
```

RAG-only answer section:

```text
판정
하면 안 되는 행동
반드시 확인할 절차
참고 근거
주의
```

답변에서 제거:

- AI4I 예측
- 고장 확률
- TWF/OSF/HDF/PWF 확률
- run id
- model
- token
- cost
- calls
- replans
- trace
- raw score
- chunk id
- safety gate id

### 10.3 효과

- AI4I 없는 safety 질문이 예측 답변처럼 보이지 않는다.
- 현재 설비 위험과 물리 작업 절차 위험을 분리한다.
- RAG-only safety 답변이 짧고 사용하기 쉬워졌다.

---

## 11. generate_report 제거

### 11.1 이전 상태

입력 schema:

```text
AgentSendRequest.generate_report
AgentRequest.generate_report
```

UI:

```text
보고서 생성 checkbox
```

Runtime:

```text
ReportGate
report_request
report_required
documentation node
ReportService
report field generation
```

### 11.2 문제

- 일반 답변과 보고서 답변이 불필요하게 갈라졌다.
- 사용자는 대부분 "답변"을 원하지 별도 report route를 원하지 않았다.
- 긴 보고서가 token/cost를 증가시켰다.
- 내부 run 기록은 이미 trace/history/usage/citation으로 남았다.

### 11.3 개선 내용

제거:

- public schema의 `generate_report`
- Streamlit `보고서 생성` checkbox
- request payload의 `generate_report`
- `ReportGate`
- `report_request`
- `report_answer`
- `report_required`
- `requires_report`
- `documentation.report_composer`
- `ReportService`
- documentation mode

유지:

- `run_id`
- `session_id`
- route
- trace
- retrieved_documents
- citations
- llm_usage
- prediction metadata
- risk summary
- safety context
- warnings

정책:

```text
사용자가 "보고서 형식으로 정리해줘"라고 하면
별도 report route가 아니라 answer 본문을 Markdown 스타일로 작성한다.
```

### 11.4 효과

- 제품 답변 경로가 단순해졌다.
- UI에서 불필요한 선택지가 줄었다.
- 일반 answer가 항상 중심이 된다.
- 내부 기록은 계속 보존된다.

---

## 12. 현재 구조 상세

### 12.1 FastAPI entrypoint

주요 endpoint:

```text
POST /agent/send
POST /agent/send/stream
POST /rag/search
GET /health
GET /ready
GET /llm/models
POST /predict
user/domain/history/evaluation endpoints
```

삭제된 endpoint:

```text
POST /agent/run
```

### 12.2 Product path

```text
/agent/send
  -> AgentSendRequest
  -> RootManufacturingGraph.run
  -> AgentResponse
```

### 12.3 RAG debug path

```text
/rag/search
  -> RagSearchRequest
  -> RagService.search
  -> ChromaRetriever
```

이 경로는 agent 내부 답변 production path가 아니다.

### 12.4 RootGraph node

현재 root-level node:

```text
request_context
intent_gateway
fast_concept_answer
general_lightweight_answer
recommended_action_recap
recommended_action_item_explanation
unsupported_or_clarification
meta_feedback
supervisor_planning
manufacturing_analysis
evidence_retrieval
safety
response_synthesis
response_packager
focus_updater
audit_persistence
```

삭제/비활성화된 node:

```text
lightweight_rag_answer
documentation
legacy graph run path
```

### 12.5 RAG Evidence SubAgent state

RAG Evidence state에는 요청별 정보만 들어간다.

```text
request
plan
prediction
manufacturing_context
top_k
query_specs
raw_chunks
filtered_chunks
selected_chunks
evidence_grade
citations
warnings
trace
output
```

trace에는 raw text/API key/full prompt를 넣지 않는다.

---

## 13. 테스트 및 검증 상태

최종 테스트:

```text
93 passed
```

중요 테스트 축:

- AI4I feature complete -> prediction_called=true
- AI4I feature incomplete -> ai4i_clarification_required
- AI4I incomplete이면 RAG 실행 안 함
- RAG Evidence SubAgent graph flow
- Chroma runtime RAG
- safety validator natural language coverage
- RAG-only safety answer에 AI4I/debug 정보 없음
- equipment title match가 generic industry 문서보다 우선
- `generate_report` extra input 무시
- report-style request가 report node를 만들지 않음

---

## 14. 개선 효과 정리

### 14.1 안정성

이전:

- feature 부족 prediction 요청이 RAG-only로 흘러갈 수 있음.
- Chroma 실패가 JSONL fallback으로 숨겨질 수 있음.
- report route가 답변 경로를 흔들 수 있음.

현재:

- AI4I feature audit으로 prediction 실행 조건 명확.
- Chroma production path는 explicit diagnostic.
- report option 제거로 답변 경로 단순.

### 14.2 유지보수성

이전:

- RootGraph에 많은 helper가 몰림.
- RAG pipeline이 service/orchestrator/root graph 사이에 걸쳐 있음.
- schemas.py가 거대한 bucket 역할.

현재:

- Context/Planning/RAG/Safety/Memory가 SubAgent boundary를 가짐.
- RAG production path는 하나.
- schemas는 bounded package로 분리.

### 14.3 답변 품질

이전:

- Normal prediction인데 위험도가 과장됨.
- RAG-only 질문에 AI4I 문구가 붙음.
- 문서 근거가 뜬금없는 업종/설비 문서로 치우침.
- debug 정보가 사용자 답변에 섞일 수 있음.

현재:

- prediction risk와 safety work risk 분리.
- RAG-only answer는 AI4I 표현 제거.
- title/doc_type/safety_gate/failure_mode 기반 evidence selection 강화.
- public answer와 debug metadata 분리.

### 14.4 운영성

이전:

- vector DB가 git ignored라 다른 환경에서 Chroma 상태 재현이 어려움.
- 702/727 mismatch 원인 파악이 필요했음.

현재:

- runbook으로 JSONL -> Chroma 727 재생성 절차 명시.
- mismatch는 reindex issue로 분리.
- runtime에서 자동 sync/reindex하지 않음.

---

## 15. 남은 리스크

아직 남은 리스크는 다음과 같다.

1. `LLMService.generate_json(...)`이 `None`과 `last_error` 방식으로 실패를
   표현한다. caller가 반드시 명시적으로 surface해야 한다.
2. 일부 broad `except Exception` 경로가 남아 있다.
3. response synthesis는 아직 별도 SubAgent가 아니다.
4. corpus versioning은 아직 없다.
5. Chroma index health automation은 없다. runbook 기반 수동 재생성이다.
6. archive 문서에는 과거 구조가 남아 있으므로 current runtime 문서와
   혼동하면 안 된다.
7. safety gate YAML 품질이 답변 품질에 직접 영향을 준다.
8. evidence selection은 deterministic rerank 중심이며, 애매한 케이스의
   LLM judge는 제한적으로만 사용해야 한다.

---

## 16. 앞으로 건드리면 안 되는 것

아키텍처 작업 중 아래 artifact를 수정하면 안 된다.

```text
ai_server/storage/models/ai4i_model_bundle.joblib
ai_server/storage/history/*.sqlite3
ai_server/storage/history/*.sqlite3-shm
ai_server/storage/history/*.sqlite3-wal
ai_server/data/processed/rag_chunks.jsonl
ai_server/data/processed/rag_documents.jsonl
ai_server/data/processed/rag_corpus_report.md
ai_server/data/processed/rag_pipeline_summary.json
ai_server/data/vector_db/chroma/*
```

해당 artifact는 명시적인 모델 학습, ingestion, corpus 복구, Chroma rebuild
작업에서만 수정해야 한다.

---

## 17. 후속 작업 우선순위

### P0

- LLM failure path를 더 명시적인 error contract로 정리.
- broad fallback/exception handling audit.
- response synthesis 실패 시 UI progress status와 backend error code 정합성 강화.

### P1

- ResponseSynthesisSubAgent 분리 검토.
- safety gate YAML 품질 개선.
- evidence judge 호출 조건 더 정교화.
- answer length policy를 route별로 더 엄격히 적용.

### P2

- corpus versioning.
- Chroma index health dashboard.
- admin/debug UI.
- LangGraph `Send` 기반 RAG fan-out 병렬화 검토.

---

## 18. 후속 작업자가 기억할 핵심 문장

```text
AI4I는 예측 입력이고, RAG corpus가 아니다.
RAG Evidence는 OSHA/Haas/KOSHA 문서 근거 레이어다.
RootGraph는 top-level orchestration만 해야 한다.
Agent 내부 RAG production path는 RagEvidenceSubAgent 하나다.
Chroma fallback은 조용히 하지 말고 diagnostic으로 드러낸다.
Public answer에는 debug metadata와 safety gate id를 노출하지 않는다.
보고서 생성은 별도 route가 아니라 answer style 문제다.
```
