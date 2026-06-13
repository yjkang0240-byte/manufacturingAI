# Historical Record

This document is an implementation log, not the current runtime contract.

# Manufacturing AI Agent Full Implementation Record

이 문서는 제조 AI Agent 프로젝트에서 초반 지시부터 현재 RAG Vector DB 구축까지 진행한 전체 작업을 정리한 기록이다.

목적은 단순 변경 목록이 아니라, 나중에 포트폴리오/트러블슈팅/개발 회고에서 다음을 설명할 수 있게 하는 것이다.

- 처음에는 어떤 문제가 있었는가
- 어떤 지시를 기준으로 개선했는가
- 어떤 구조로 바꾸었는가
- 어떤 코드와 문서가 추가되었는가
- 어떤 성과가 있었는가
- 앞으로 무엇을 보완해야 하는가

## 0. 전체 방향 요약

초기 프로젝트는 FastAPI 기반 제조 AI Agent였지만, 다음 한계가 있었다.

- 단순 질문과 제조 분석 질문이 구분되지 않음
- history/context가 user/session 단위로 안전하게 분리되지 않음
- follow-up 질문의 지시어 해석이 불안정함
- RAG, safety, prediction, report, usage, memory 책임이 섞여 있음
- Streamlit UI가 Agent 진행 과정과 usage/cost를 충분히 보여주지 못함
- Vector DB용 외부 문서 수집/정제/embedding 파이프라인이 없음
- LangGraph 구조가 명시적 subgraph orchestration이라기보다 imperative flow에 가까움

현재 구조는 다음 방향으로 정리되었다.

```text
FastAPI + SQLite + Streamlit
  -> User-scoped Context Engineering
  -> LangGraph RootManufacturingGraph
  -> ContextResolution / ContextPacks / AnswerMemory
  -> IntentGateway + Structured Output Classifier + Hard Gate Registry
  -> FormatterRegistry
  -> SafetyPolicy
  -> Heavy Manufacturing Modules
  -> RAG Source Pipeline + Chroma Vector DB
```

## 1. 초반 코드 부정 평가 및 보완점 문서화

### 사용자 지시

처음 요청은 다음과 같았다.

```text
지금 코드를 보고 부정적으로 평가 후 보완해야할 점들을 md로 정리해
```

### 당시 문제 인식

초기 코드에는 다음 문제가 있었다.

- Agent 실행 구조가 명확한 graph/subgraph가 아니라 service 호출 흐름에 가까웠음
- user/session context가 충분히 분리되지 않음
- Streamlit UI가 실제 agent 상태와 trace를 충분히 보여주지 못함
- mock/smoke/LLM false 경로가 실제 운영 검증을 흐리게 함
- usage/cost 관측이 부족함
- code/file 구조가 커지고 책임이 섞여 있었음

### 결과

부정 평가와 보완점을 문서화했다.

- `docs/CODE_NEGATIVE_REVIEW.md`
- `docs/WORK_DONE_AND_GAPS.md`
- `docs/DOMAIN_FASTAPI_WORK_DONE_AND_GAPS.md`

### 성과

이 단계에서 이후 작업의 기준이 생겼다.

- 단순 기능 추가보다 구조 개선이 우선이라는 방향 확정
- Streamlit UI, usage/cost, context engineering, LangGraph 구조 개선 필요성 도출
- portfolio 문서화 대상으로 삼을 수 있는 문제 목록 확보

## 2. Streamlit UI 구축 및 Agent 실행 가시화

### 사용자 지시

```text
너가 지적한 부분을 모두 반영해서 고치고,
streamlit 으로 테스트 할 수 있게 UI 까지 만들어.
AI가 구동 중일 때는 어떤게 구동중인지 UI에서 보여줬으면 좋겠어.
```

### 기존 문제

- API만으로 테스트해야 해서 비개발자가 흐름을 확인하기 어려움
- Agent가 실행 중일 때 prediction, RAG, safety, answer generation 중 무엇이 진행 중인지 알 수 없음
- 사용자가 입력한 process_data, session, report 옵션을 시각적으로 다루기 어려움

### 변경

Streamlit 앱을 확장했다.

- `streamlit_app.py`

반영한 기능:

- Agent 입력 폼
- process_data 입력
- report 생성 옵션
- user/session 선택
- chat UI
- 실행 trace/progress 표시
- usage/cost 표시
- model 선택
- history/context/usage 관련 탭

### 성과

- FastAPI만으로는 확인하기 어려운 Agent 실행 흐름을 UI에서 검증 가능
- Agent가 어떤 노드를 실행 중인지 사용자가 볼 수 있게 됨
- 단일 응답 usage와 누적 usage를 분리해서 확인 가능

## 3. OpenAI Key 기반 실제 LLM 실행 전환

### 사용자 지시

```text
나 방금 .env 파일에 openAPI key 넣었는데 이제 에이전트 돌아가는거 확인 가능해?
아 방금 바꿨어
```

### 기존 문제

- mock/LLM false 경로가 남아 있어 실제 agent 품질 검증을 방해
- OpenAI key가 있어도 어느 모델/비용/usage로 호출되는지 UI에서 알기 어려움

### 변경

`.env` 기반 OpenAI 실행을 전제로 정리했다.

- `.env.example`
- `ai_server/.env.example`
- `ai_server/app/services/llm_service.py`
- `streamlit_app.py`

관련 환경변수:

```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-5.4-mini
OPENAI_API_KEY=
LLM_ENABLE_STRUCTURED_OUTPUT=true
LLM_ALLOW_EXPENSIVE_MODELS=false
```

### 성과

- 실제 OpenAI LLM 호출 기반으로 Agent 검증 가능
- mock 중심 개발에서 실제 실행 중심 개발로 전환
- model 선택과 usage/cost 확인 기반 마련

## 4. Usage / Cost / KRW 환산 / OpenTelemetry 설계

### 사용자 지시

```text
Open Telemety로 토큰을 측정해서 예상 비용도 계산할 수 있을까?
요금은 UI 어디서 확인할 수 있는거야?
추정 cost에 환율로 한국 돈도 계산할 수 있게 해줘
```

### 기존 문제

- LLM 호출 비용과 token 사용량이 사용자에게 보이지 않음
- 누적 cost와 단일 응답 cost가 섞일 수 있음
- 포트폴리오 관점에서 LLMOps 요소가 부족함

### 변경

OpenAI response usage 기반으로 token/cost를 계산하는 구조를 반영했다.

주요 방향:

```text
LLMService 호출
  -> response.usage 추출
  -> UsageRecord 생성
  -> 모델별 가격표 기반 비용 계산
  -> USD/KRW 환산
  -> response 및 history 저장
  -> OpenTelemetry span attribute 기록
  -> Streamlit 표시
```

관련 파일:

- `ai_server/app/services/llm_service.py`
- `ai_server/app/services/observability_service.py`
- `streamlit_app.py`
- `.env.example`

환경변수:

```env
USD_KRW_EXCHANGE_RATE=1400
```

### 성과

- 단일 Agent 응답에는 해당 응답의 token/cost만 표시
- Usage tab에서는 누적 token/cost 표시
- USD와 KRW 예상 비용을 함께 확인 가능
- LLMOps 관점에서 usage/cost 관측 기반 확보

## 5. 모델 선택 UI 및 고가 모델 제한

### 사용자 지시

```text
어떤 모델 쓰는지도 선택할 수 있나?
선택하는 창도 하나 만들 되, 비싼 애들은 못누르게 막으면 좋겠는데
```

### 기존 문제

- 모델이 고정되어 있었음
- 비싼 모델을 실수로 선택할 가능성 있음
- model별 가격과 usage를 UI에서 통제하기 어려움

### 변경

Streamlit sidebar/model selector를 추가하고 고가 모델 제한 정책을 반영했다.

관련 파일:

- `streamlit_app.py`
- `.env.example`

환경변수:

```env
LLM_ALLOW_EXPENSIVE_MODELS=false
```

### 성과

- 사용자가 실행 전 모델을 확인 가능
- 비용 위험이 큰 모델은 UI에서 제한 가능
- portfolio demo에서 LLM 비용 통제 설계를 설명 가능

## 6. Mock / Smoke / 불필요 코드 제거 및 최적화

### 사용자 지시

```text
LLM false 는 필요없어.
기존에 목업데이터나 쓸데없는 코드는 싹다 삭제하고,
코드가 지금 불필요하게 많은 것 같은데 합칠 수 있는 건 합쳐줘.
기존 스모크들은 싹 없애.
파일도 최적화하고 코드도 합쳤어?
```

### 기존 문제

- demo/mock/smoke 코드가 실제 운영 경로와 섞여 있었음
- 테스트 목적 코드와 runtime 코드의 경계가 흐림
- LLM false fallback이 실제 실패를 숨길 수 있음

### 변경 방향

- 실제 OpenAI 기반 실행 경로 중심으로 정리
- 기존 smoke 중심 검증 대신 pytest contract 중심으로 이동
- mock은 테스트 fixture 용도로만 제한

### 성과

- 실제 운영 경로와 테스트 경로가 더 명확해짐
- Agent 품질 문제를 mock이 가리지 않게 됨

## 7. Portfolio Roadmap / Feature Registry 구조화

### 사용자 지시

```text
나 포트폴리오에 지금 프로젝트 녹여야해서,
지금 구현된 것들 고려한 것들 좀 더 보완하면 좋을 것들 쫙 적어주고,
기능 확장할 때마다 계속적으로 추가해 나갈 수 있게 구조 짜줘
```

### 변경

포트폴리오 및 확장 관리 문서를 추가/정리했다.

관련 문서:

- `docs/PORTFOLIO_ROADMAP.md`
- `docs/FEATURE_REGISTRY.md`
- `docs/ARCHITECTURE_DECISIONS.md`
- `docs/QUALITY_CHECKLIST.md`
- `docs/DEMO_SCRIPT.md`

### 성과

- 기능 추가 시 변경 파일/API/테스트/데모 방법을 누적 기록 가능
- 포트폴리오에서 "무엇을 왜 설계했는지" 설명할 문서 기반 확보

## 8. User-scoped Context Engineering 기획 및 구현

### 사용자 지시

```text
유저 생성 및 삭제 기능을 만들고,
유저 별로 컨텍스트를 가지고,
전에 있었던 내용을 가지고 할 수 있도록 컨텍스트 엔지니어링을 했으면 하는데
```

이후 상세 기획으로 다음 요구가 추가되었다.

- `POST /users`
- `GET /users`
- `PATCH /users/{user_id}`
- `DELETE /users/{user_id}`
- `GET /users/{user_id}/context`
- `GET /users/{user_id}/history`
- `/agent/send`에 `user_id` 필수
- user별 history/session/memory 분리
- hard/soft delete 정책
- context budget
- memory extraction
- Streamlit user select/create/delete/context tab

### 기존 문제

- session_id는 있었지만 user identity가 약했음
- 다른 user의 context가 섞일 가능성이 있었음
- 장기 memory와 최근 session context가 분리되지 않았음

### 변경

User/Context/Memory 관련 service와 SQLite store를 추가했다.

관련 파일:

- `ai_server/app/services/user_service.py`
- `ai_server/app/services/context_service.py`
- `ai_server/app/services/memory_service.py`
- `ai_server/app/storage/sqlite_store.py`
- `ai_server/app/schemas.py`
- `ai_server/app/main.py`
- `streamlit_app.py`
- `docs/CONTEXT_ENGINEERING.md`
- `docs/USER_CONTEXT_ENGINEERING_PLAN.md`

### 성과

- user별 session/history/memory 분리
- 다른 user context contamination 방지
- user 삭제 시 관련 context 정리 정책 도입
- Streamlit에서 user별 context 확인 가능

## 9. Chat UI와 이전 대화 맥락 문제

### 사용자 지시

```text
히스토리 탭이 아니라 채팅 탭을 말한거야
토크가 뭐냐고 물어보고 그 다음에 이것의 단점이 뭐야? 라고 물어봤는데
이것이 무엇인지 특정하지 못했어.
이전 컨텍스트를 기억하지 못하고 있는 것 같은데 수정 부탁해.
```

### 기존 문제

대표 실패:

```text
User: 토크가 뭐냐
User: 이것의 단점이 뭐야?

Assistant:
prediction 값이 없습니다.
rag_contexts가 비어 있습니다.
failure_modes가 비어 있습니다.
```

문제 원인:

- 단순 개념 follow-up을 current process state 판단처럼 처리
- "이것"을 구조화된 resolved reference로 관리하지 않음
- 이전 질문/답변의 focus가 LangGraph state에 안정적으로 저장되지 않음

### 변경

초기에는 `last_focus` 개념을 도입했고, 이후 clean-slate v2에서 `AnswerMemory.focus`로 흡수했다.

현재 구조:

```text
ContextResolver
  -> ContextResolution
  -> followup_type
  -> followup_target
  -> standalone_query
```

관련 파일:

- `ai_server/app/agent/context/context_resolver.py`
- `ai_server/app/agent/context/schemas.py`
- `ai_server/app/agent/context/answer_memory_writer.py`
- `ai_server/app/agent/context/context_pack_builder.py`

### 성과

- "이것/이걸/그거/방금" 같은 표현을 이전 답변 memory 기반으로 처리
- 신규 질문은 과거 heavy path에 오염되지 않음
- follow-up 질문은 필요한 memory만 참조

## 10. LangGraph thread_id / checkpoint memory 정리

### 사용자 지시

```text
session_id를 LangGraph의 thread_id로 써야 함.
run_id를 thread_id로 쓰면 안 된다.
messages, last_focus, recent_entities를 state에 저장해야 한다.
```

이후 clean-slate 전환에서 다음 정책으로 확정했다.

```text
thread_id = user_id:session_id
state_schema_version = 2
v1 checkpoint는 보존하지 않음
primitive-only checkpoint
```

### 기존 문제

- recent_runs/history 검색은 대화 memory가 아니라 실행 로그 검색에 가까움
- run_id를 thread_id처럼 쓰면 매 요청이 새 대화가 됨
- checkpoint에 Pydantic model/object가 들어갈 위험이 있음

### 변경

checkpointing 모듈을 분리했다.

관련 파일:

- `ai_server/app/agent/checkpointing/factory.py`
- `ai_server/app/agent/checkpointing/thread_id.py`
- `ai_server/app/agent/checkpointing/reset.py`
- `ai_server/app/agent/state.py`

### 성과

- user/session별 memory 격리
- checkpoint v2 schema 고정
- checkpoint에는 dict/list/str/int/float/bool/None만 저장
- v1 compatibility 제거

## 11. IntentGateway 휴리스틱에서 Structured Output Router로 전환

### 사용자 지시

```text
키워드 휴리스틱을 계속 늘리는 구조가 아니라,
structured output 기반 intent classifier + hard safety gate 구조로 바꿔라.
Formatter는 라우팅 결과를 렌더링만 하게 해라.
```

### 기존 문제

- `왜`, `도표`, `보여줘`, `주의`, `이걸` 같은 키워드가 계속 늘어남
- 표현이 바뀔 때마다 if문과 테스트가 늘어나는 구조
- formatter가 질문 문자열을 보고 다시 route를 추론

### 변경

Structured Output 기반 intent classifier와 policy validator를 추가했다.

관련 파일:

- `ai_server/app/services/intent_classifier_service.py`
- `ai_server/app/services/intent_gateway_service.py`
- `ai_server/app/services/intent_policy_validator.py`
- `ai_server/app/prompts/intent_classifier_prompt.py`
- `ai_server/app/services/structured_output_schema.py`

### 성과

- glossary exact match는 No-LLM fast path
- process_data risk/safety/report는 hard gate
- ambiguous follow-up/rationale/chart distinction은 structured classifier
- formatter는 selected_path/answer_type만 사용

## 12. OpenAI Strict JSON Schema 문제 해결

### 문제

Structured output 사용 중 다음 오류가 발생했다.

```text
Invalid schema for response_format 'intent_classifier_output':
'additionalProperties' is required to be supplied and to be false.
```

### 변경

OpenAI strict structured output schema 변환 helper를 공용화했다.

관련 파일:

- `ai_server/app/services/structured_output_schema.py`

처리 내용:

- object schema에 `additionalProperties: false`
- nested object 처리
- `$defs`, `anyOf`, `oneOf`, array items 처리
- default 제거
- optional field strict schema 변환

### 성과

- IntentClassifierService뿐 아니라 향후 다른 structured output에도 재사용 가능
- schema 오류가 사용자 답변에 raw exception으로 노출되는 문제 완화

## 13. Context Engineering v2 clean-slate 전환

### 사용자 지시

```text
기존 checkpoint/state 데이터는 보존할 필요 없다.
LegacyContextAdapter를 두지 말고 clean-slate Context Engineering 구조로 정리하라.
last_focus, last_answer_claims, last_answer_key_phrases 제거.
```

### 기존 문제

- 레거시 state 호환을 유지하면 새 구조가 계속 더러워짐
- `last_focus`, `last_answer_claims`, `recommended_actions`가 top-level state로 흩어짐
- PublicAnswerContextBuilder나 formatter가 legacy field를 읽을 위험

### 변경

clean-slate v2 구조로 정리했다.

핵심 스키마:

- `ContextResolution`
- `AnswerMemory`
- `RecommendedAction`
- `ContextPacks`
- `FallbackReason`

관련 파일:

- `ai_server/app/agent/context/schemas.py`
- `ai_server/app/agent/context/context_resolver.py`
- `ai_server/app/agent/context/context_pack_builder.py`
- `ai_server/app/agent/context/context_compressor.py`
- `ai_server/app/agent/context/answer_memory_writer.py`
- `ai_server/app/agent/context/context_validator.py`

### 성과

- 레거시 state 직접 의존 제거
- 신규 질문과 follow-up 질문 분리
- 권장조치 follow-up은 `RecommendedActionFormatter`로 처리
- checkpoint v2로 상태 안정화

## 14. FormatterRegistry와 SafetyPolicy 분리

### 사용자 지시

```text
Formatter는 이미 결정된 answer_type/selected_path를 렌더링만 해야 한다.
Safety는 formatter 함수 하나가 아니라 SafetyPolicy/SafetyContext/SafetyFormatter로 분리되어야 한다.
```

### 기존 문제

- 모든 답변 포맷이 하나의 거대한 formatter에 섞일 위험
- fast_concept_answer에 heavy/safety format이 섞일 수 있음
- safety 판단과 safety 출력이 섞임

### 변경

FormatterRegistry와 safety layer를 분리했다.

관련 파일:

- `ai_server/app/agent/formatters/registry.py`
- `ai_server/app/agent/formatters/fast_concept_formatter.py`
- `ai_server/app/agent/formatters/heavy_analysis_formatter.py`
- `ai_server/app/agent/formatters/rag_formatter.py`
- `ai_server/app/agent/formatters/safety_formatter.py`
- `ai_server/app/agent/formatters/recommended_action_formatter.py`
- `ai_server/app/agent/formatters/fallback_formatter.py`
- `ai_server/app/agent/safety/safety_policy.py`
- `ai_server/app/agent/safety/safety_context_builder.py`
- `ai_server/app/agent/safety/safety_formatter.py`

### 성과

- selected_path별 답변 포맷 분리
- fast answer에 `판정/위험도/권장 조치` 누수 방지
- safety가 필요한 경우에만 SafetyContext 기반 출력

## 15. Heavy Manufacturing Path 분리

### 사용자 지시

```text
ManufacturingAgentGraph가 너무 많은 helper 책임을 갖고 있으면 분리하라.
DiagnosticPlanner, RagEvidenceSubAgent, RagQueryPlanner, EvidenceFilter, EvidenceGrader,
SafetyGateBuilder, RecommendationBuilder, StructuredAnswerPayloadBuilder로 나눠라.
```

이후 추가 지시:

```text
RagEvidencePlanner, make_query, last_diagnostic_plan, SupervisorService private 의존,
legacy wrapper를 지금 제거하라.
```

### 기존 문제

- `ManufacturingAgentGraph`가 helper/wrapper를 많이 들고 있었음
- RAG query, evidence grading, safety guidance, recommendation, payload build가 섞임
- `DiagnosticPlanner.last_diagnostic_plan` 같은 request instance state가 있었음
- `SupervisorService._intent`, `_layers`, `_llm_refine` 같은 private method 의존 위험

### 변경

heavy path를 모듈화했다.

관련 파일:

- `ai_server/app/agent/heavy/diagnostic_planner.py`
- `ai_server/app/agent/heavy/plan_translator.py`
- `ai_server/app/agent/heavy/plan_refiner.py`
- `ai_server/app/agent/heavy/rag_query_planner.py`
- `ai_server/app/agent/rag_evidence/subagent.py`
- `ai_server/app/agent/heavy/chroma_retriever.py`
- `ai_server/app/agent/heavy/evidence_filter.py`
- `ai_server/app/agent/heavy/evidence_grader.py`
- `ai_server/app/agent/heavy/citation_builder.py`
- `ai_server/app/agent/heavy/safety_gate_builder.py`
- `ai_server/app/agent/heavy/recommendation_builder.py`
- `ai_server/app/agent/heavy/structured_answer_payload_builder.py`

제거한 것:

- `RagEvidencePlanner`
- `make_query(...)`
- `last_diagnostic_plan`
- `self.supervisor._...` private dependency
- graph wrapper helper

### 성과

- `root_graph.py`와 `graph.py`는 orchestration 중심으로 축소
- RAG/citation/safety/recommendation 책임이 모듈 단위로 분리
- grep 기준으로 legacy wrapper/private dependency 제거 확인

## 16. RAG Source Pipeline 및 Chroma Vector DB 구축

### 사용자 지시

```text
외부 데이터 가지고 vectorDB 만들려고 했는데,
api 키도 env에 넣어놓은 상태야.
다운로드좀 쫙 받아서 벡터화까지 진행하는 코드 짜주고,
이거 메뉴얼에 반영해.
```

이후 추가 지시:

```text
다 다운 받지 말고 지금 데이터랑 연관 있는 것만 먼저 선제적으로 다운받으면 안되나?
```

### 기존 문제

- 기존에는 static/KOSHA/document/chunk/index 스크립트가 나뉘어 있었지만 end-to-end 실행이 없었음
- Chroma indexing은 optional stub에 가까웠음
- KOSHA 실제 응답 필드명이 예상과 달랐음
- 전체 KOSHA를 받으면 범위가 과하고 느림

### 변경

end-to-end pipeline을 추가했다.

관련 파일:

- `ai_server/scripts/run_rag_vector_pipeline.py`
- `ai_server/scripts/download_static_rag_sources.py`
- `ai_server/scripts/download_kosha_sources.py`
- `ai_server/scripts/build_rag_documents.py`
- `ai_server/scripts/build_rag_chunks.py`
- `ai_server/scripts/inspect_rag_corpus.py`
- `ai_server/scripts/index_rag_chunks_chroma.py`
- `ai_server/scripts/rag_pipeline_utils.py`

핵심 코드:

- AI4I 관련 keyword 제한: `run_rag_vector_pipeline.py`
- OpenAI embedding: `index_rag_chunks_chroma.py`
- KOSHA `fileDownloadUrl` 대응: `download_kosha_sources.py`
- atomic JSONL write: `rag_pipeline_utils.py`

### 실제 실행 결과

```text
profile: ai4i-mvp
KOSHA documents: 40
total documents: 44
chunks: 727
Chroma vectors: 727
collection: manufacturing_rag
embedding model: text-embedding-3-small
```

생성 산출물:

- `ai_server/data/processed/kosha_download_index.json`
- `ai_server/data/processed/kosha_download_index.jsonl`
- `ai_server/data/processed/rag_documents.jsonl`
- `ai_server/data/processed/rag_chunks.jsonl`
- `ai_server/data/processed/rag_corpus_report.md`
- `ai_server/data/processed/rag_pipeline_summary.json`
- `ai_server/data/vector_db/chroma/`

### 성과

- AI4I CSV row는 Vector DB에 넣지 않는 원칙 유지
- OSHA/Haas/KOSHA 문서만 RAG 근거로 사용
- 현재 AI4I 제조 예측과 직접 연결되는 안전/정비 문서부터 우선 수집
- OpenAI embedding 기반 Chroma vector DB 생성 완료

## 17. Git ignore 및 데이터 파일 관리

### 사용자 지시

```text
gitignore에 라이브러리 파일들은 무시하게 해줘. 지금 너무 많이 잡힌다
```

### 변경

`.gitignore`에 raw/vector/checkpoint/cache/db 파일을 무시하도록 보강했다.

관련 파일:

- `.gitignore`

대상:

- `.env`
- raw download files
- vector DB
- checkpoint DB
- cache files

### 성과

- API key/raw data/vector DB가 실수로 commit될 위험 감소
- 코드 변경과 생성 산출물을 더 명확히 구분

## 18. Python 3.12 전환

### 사용자 지시

```text
파이썬 3.12로 바꾸고 전체 코드도 수정그에 맞게 하자
```

### 변경

Python 3.12 기반 실행을 정리했다.

관련 파일:

- `.python-version`
- `runtime.txt`
- `ai_server/Dockerfile`
- `ai_server/requirements.txt`

### 성과

- `.venv312` 기준으로 compile/test 실행
- 의존성 설치 및 Streamlit/FastAPI 실행 환경 정리

## 19. 주요 테스트 및 검증

오늘 기준 주요 검증 결과:

```bash
cd ai_server

../.venv312/bin/python -m pytest tests/test_context_engineering.py -q
# 35 passed

../.venv312/bin/python -m pytest tests/test_intent_gateway.py -q
# 10 passed

../.venv312/bin/python -m pytest tests/test_kosha_download_utils.py tests/test_rag_document_building.py tests/test_rag_chunking.py -q
# 6 passed

../.venv312/bin/python -m pytest -q
# 62 passed
```

RAG/Chroma 확인:

```bash
../.venv312/bin/python -c "import chromadb; c=chromadb.PersistentClient(path='data/vector_db/chroma').get_collection('manufacturing_rag'); print(c.count())"
# 727
```

보안 문자열 확인:

```text
serviceKey / KOSHA_API_KEY / OPENAI_API_KEY 검색 결과: 0건
```

## 20. 현재까지 완료된 핵심 산출물

### Code

- `ai_server/app/agent/root_graph.py`
- `ai_server/app/agent/graph.py`
- `ai_server/app/agent/context/*`
- `ai_server/app/agent/formatters/*`
- `ai_server/app/agent/safety/*`
- `ai_server/app/agent/routing/*`
- `ai_server/app/agent/heavy/*`
- `ai_server/app/agent/checkpointing/*`
- `ai_server/app/services/intent_classifier_service.py`
- `ai_server/app/services/intent_gateway_service.py`
- `ai_server/app/services/structured_output_schema.py`
- `ai_server/app/services/user_service.py`
- `ai_server/app/services/context_service.py`
- `ai_server/app/services/memory_service.py`
- `ai_server/app/storage/sqlite_store.py`
- `ai_server/scripts/run_rag_vector_pipeline.py`
- `ai_server/scripts/index_rag_chunks_chroma.py`
- `streamlit_app.py`

### Docs

- `docs/CODE_NEGATIVE_REVIEW.md`
- `docs/CONTEXT_ENGINEERING.md`
- `docs/USER_CONTEXT_ENGINEERING_PLAN.md`
- `docs/LANGGRAPH_FINAL_ARCHITECTURE.md`
- `docs/ORCHESTRATION_NODE_STRUCTURE.md`
- `docs/CHROMA_PDF_INGESTION_STRATEGY.md`
- `docs/architecture.md`
- `docs/TROUBLESHOOTING_RECORD_2026-06-13.md`
- `docs/FULL_PROJECT_IMPLEMENTATION_RECORD.md`

### Data artifacts

- `ai_server/data/processed/rag_documents.jsonl`
- `ai_server/data/processed/rag_chunks.jsonl`
- `ai_server/data/processed/rag_corpus_report.md`
- `ai_server/data/processed/rag_pipeline_summary.json`
- `ai_server/data/vector_db/chroma/`

## 21. 앞으로 보완해야 할 점

### 21.1 Chroma Retriever를 Agent runtime에 완전 연결

현재는 Chroma vector DB 생성까지 완료되었다. 다음 단계는 실제 Agent RAG path가 이 Chroma DB를 검색하도록 연결하는 것이다.

해야 할 일:

- `RagEvidenceSubAgent`가 `RagService` / `ChromaRetriever`를 통해 Chroma collection 검색
- metadata filter 적용
  - `failure_modes`
  - `safety_gate`
  - `project_priority`
  - `retrieval_scope`
  - `source`
- 검색 결과를 `EvidenceFilter -> EvidenceGrader -> CitationBuilder`로 전달

성과 목표:

- "토크 높고 공구 마모 큰데 점검/안전 절차?" 질문에서 KOSHA/OSHA/Haas 관련 chunk가 실제 citation으로 사용

### 21.2 Streamlit PDF 업로드 및 Vectorize UI

현재는 CLI pipeline이다. UI에서도 문서 업로드 후 vectorize가 가능해야 한다.

해야 할 일:

- Streamlit sidebar 또는 RAG tab 추가
- PDF/HWPX/HTML 업로드
- 저장 위치: `ai_server/data/raw/rag_sources/user_uploads/`
- build documents/chunks/index 실행 버튼
- corpus report 표시
- Chroma collection count 표시

성과 목표:

- 사용자가 문서를 넣고 바로 Agent RAG에 반영 가능

### 21.3 RAG 검색 품질 테스트

현재는 pipeline 테스트 중심이다. retrieval 품질 테스트가 필요하다.

추가 테스트:

- `토크`, `공구 마모`, `스핀들 부하` query가 Haas/KOSHA 문서를 찾는지
- `LOTO`, `에너지 차단`, `정비 전 안전` query가 OSHA/KOSHA 문서를 찾는지
- `retrieval_scope=restricted` 문서가 기본 검색에서 과하게 섞이지 않는지
- KOSHA 문서가 법적 보증처럼 답변되지 않는지

### 21.4 RAG Corpus 품질 개선

현재 corpus report 기준:

```text
documents: 44
chunks: 727
KOSHA: 40
OSHA: 2
Haas: 2
```

보완할 점:

- `haas_spindle_drive_troubleshooting` source file missing 원인 확인
- CNC spindle 관련 Haas 문서 추가 확보
- KOSHA HWP/HWPX extraction 품질 개선
- chunk size/overlap tuning
- duplicate/similar chunk 제거

### 21.5 Safety Subgraph 고도화

현재 SafetyPolicy/Formatter는 분리되어 있다. 다음은 validator 계층이다.

해야 할 일:

- `ActionSafetyValidator`
- `AnswerSafetyValidator`
- `ReportSafetyValidator`
- `EscalationDecisionNode`

성과 목표:

- 조치계획, 답변, 보고서 각각에서 LOTO/방호/전문가 확인 누락 여부 검증

### 21.6 Async Job / Streaming API

긴 작업은 `/agent/send` 단일 요청보다 job/stream이 적합하다.

해야 할 일:

- `/agent/send/stream`
- `/agent/jobs`
- job event table
- background worker
- Streamlit progress event stream 연결

성과 목표:

- RAG ingestion, report generation, multi-step LLM 작업을 안정적으로 처리

### 21.7 평가 데이터셋과 Golden Tests

현재 contract tests는 구조를 보장한다. 다음은 품질 평가다.

해야 할 일:

- 제조 질문 golden dataset
- expected route
- expected safety gates
- expected source types
- expected answer sections
- regression scoring

성과 목표:

- 기능 추가 후 답변 품질 회귀 감지

### 21.8 운영형 Observability

현재 usage/cost와 OpenTelemetry 설계가 있다. 다음은 운영 전송이다.

해야 할 일:

- OTLP exporter 설정
- trace/span dashboard
- run_id/user_id_hash/session_id 기반 추적
- token/cost/latency metric
- error budget 및 budget alert

### 21.9 Security / Compliance

해야 할 일:

- API key redaction 전역화
- raw user data 저장 범위 제한
- user hard delete cascade 검증
- KOSHA/OSHA/Haas citation disclaimer 정리
- uploaded document access policy

## 22. 포트폴리오 설명용 핵심 문장

이 프로젝트에서는 제조 AI Agent를 단순 RAG 챗봇이 아니라, 공정 데이터 예측, 안전 게이트, 사용자별 context engineering, structured routing, RAG evidence grading, usage/cost observability를 포함한 LangGraph 기반 제조업 AI 시스템으로 확장했습니다.

초기에는 단순 개념 질문이 heavy analysis format으로 오염되고, "이것/왜/방금" 같은 follow-up 질문을 안정적으로 처리하지 못했지만, `ContextResolution`, `AnswerMemory`, `ContextPackBuilder`, `FormatterRegistry`, `SafetyPolicy`를 도입해 대화 맥락과 답변 경로를 구조화했습니다.

또한 AI4I CSV는 예측 모델용으로만 유지하고, OSHA/Haas/KOSHA 외부 문서는 RAG 근거용으로 분리해 Chroma Vector DB를 구축했습니다. 전체 수집이 아니라 현재 제조 데이터와 직접 관련 있는 정비/점검/회전부/방호/LOTO 문서를 우선 수집하는 `ai4i-mvp` profile을 설계해 검색 노이즈와 비용을 줄였습니다.

## 23. 결론

초반 작업은 "코드 부정 평가와 Streamlit UI 개선"에서 시작했지만, 현재는 다음 수준까지 정리되었다.

```text
User Management
+ User-scoped Context Engineering
+ LangGraph v2 Runtime
+ Structured Intent Routing
+ Formatter/Safety 분리
+ Heavy Manufacturing Module 분리
+ Usage/Cost Observability
+ RAG Source Pipeline
+ Chroma Vector DB
+ Portfolio Documentation
```

남은 핵심 과제는 Chroma DB를 실제 Agent RAG runtime에 연결하고, Streamlit에서 문서 업로드/벡터화까지 직접 제어할 수 있게 만드는 것이다.
