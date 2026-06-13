# LangGraph 최종 오케스트레이션 구조 정리

이 문서는 현재 제조 AI Agent에 구현된 LangGraph 기반 구조와, 다음 확장 설계를 논의하기 위한 기준 문서다.

핵심 방향은 다음이다.

```text
Raw User Message
→ ContextSubAgent
→ Intent Gateway
→ Fast Path 또는 PlanningSubAgent
→ 필요한 제조 Subgraph만 조건부 실행
→ RagEvidenceSubAgent / SafetySubAgent
→ Response / Documentation
→ MemorySubAgent
→ Audit / Persistence
```

현재 구현은 `RootManufacturingGraph`가 LangGraph `StateGraph`로 상위 orchestration을 담당한다. 제품 Agent endpoint는 `/agent/send`이며, legacy run endpoint는 제거됐다. Context, Planning, RAG Evidence, Safety, Memory는 각각 별도 LangGraph SubAgent가 담당하고 root graph는 내부 단계를 직접 호출하지 않는다.

---

## 1. 핵심 코드 위치

| 역할 | 파일 |
|---|---|
| Root LangGraph orchestration | `ai_server/app/agent/root_graph.py` |
| 공유 AgentState | `ai_server/app/agent/state.py` |
| 표준 trace helper | `ai_server/app/agent/trace.py` |
| Context SubAgent | `ai_server/app/agent/context_subagent/` |
| Planning SubAgent | `ai_server/app/agent/planning_subagent/` |
| RAG Evidence SubAgent | `ai_server/app/agent/rag_evidence/` |
| Safety SubAgent | `ai_server/app/agent/safety_subagent/` |
| Memory SubAgent | `ai_server/app/agent/memory_subagent/` |
| Chroma retriever infrastructure | `ai_server/app/services/chroma_retriever.py` |
| Intent Gateway | `ai_server/app/services/intent_gateway_service.py` |
| Follow-up reference resolution | `ai_server/app/services/reference_resolution_service.py` |
| User-scoped context | `ai_server/app/services/context_service.py` |
| User memory update | `ai_server/app/services/memory_service.py` |
| API entrypoint | `ai_server/app/main.py` |
| 회귀 테스트 | `ai_server/tests/test_intent_gateway.py` |

---

## 2. 현재 Root Graph 구조

현재 `RootManufacturingGraph._build_graph()`는 top-level routing 노드만 등록한다. SubAgent 내부 node 이름은 root graph가 알지 않는다.

```python
graph.add_node('request_context', self._request_context_node)
graph.add_node('intent_gateway', self._intent_gateway_node)
graph.add_node('fast_concept_answer', self._fast_concept_answer_node)
graph.add_node('unsupported_or_clarification', self._unsupported_or_clarification_node)
graph.add_node('supervisor_planning', self._supervisor_planning_node)
graph.add_node('manufacturing_analysis', self._manufacturing_analysis_node)
graph.add_node('evidence_retrieval', self._evidence_retrieval_node)
graph.add_node('safety', self._safety_node)
graph.add_node('response_synthesis', self._response_synthesis_node)
graph.add_node('response_packager', self._response_packager_node)
graph.add_node('focus_updater', self._focus_updater_node)
graph.add_node('audit_persistence', self._audit_persistence_node)
```

SubAgent 호출 boundary:

```text
request_context -> ContextSubAgent.invoke(ContextInput)
supervisor_planning -> PlanningSubAgent.invoke(PlanningInput)
evidence_retrieval -> RagEvidenceSubAgent.invoke(RagEvidenceInput)
safety -> SafetySubAgent.invoke(SafetyInput)
focus_updater -> MemorySubAgent.invoke(MemoryInput)
```

그래프 흐름은 아래와 같다.

```text
START
  ↓
request_context
  ↓
intent_gateway
  ├─ fast_concept_answer
  ├─ unsupported_or_clarification
  └─ supervisor_planning
        ↓
      manufacturing_analysis?
        ↓
      evidence_retrieval?
        ↓
      safety?
        ↓
      response_synthesis
        ↓
      response_packager
  ↓
focus_updater
  ↓
audit_persistence
  ↓
END
```

`?`가 붙은 노드는 `AgentPlan`과 routing function에 따라 조건부로 실행된다.

---

## 3. Short-Term Memory 구조

현재 short-term memory는 LangGraph SQLite checkpointer와 `thread_id = user_id:session_id` 원칙을 따른다.

```python
checkpointer = SqliteSaver.from_conn_string(str(checkpoint_path))
return graph.compile(checkpointer=self.checkpointer)
```

실행 시 config:

```python
config = {
    'configurable': {
        'thread_id': f'{user_id}:{session_id}',
        'user_id': user_id,
        'session_id': session_id,
    }
}
final_state = self.graph.invoke(state, config=config)
```

중요한 점:

- `run_id`는 매 실행마다 새로 생성된다.
- `user_id:session_id`는 LangGraph `thread_id`로 사용된다.
- 같은 `user_id + session_id` 조합이면 `recent_turns`, `rolling_summary`, `last_answer_memory`, `session_last_process_data`가 이어진다.
- 다른 사용자가 같은 `session_id`를 써도 thread가 분리된다.
- 후속 질문의 “이것/그것/지난번” 해석은 history DB보다 먼저 `last_answer_memory`를 본다.
- 서버 재시작 후에도 SQLite checkpoint DB가 남아 있으면 같은 user/session의 short-term state를 복원할 수 있다.

---

## 4. AgentState

현재 `AgentState`는 graph 전체에서 공유되는 실행 상태다.

```python
class AgentState(TypedDict):
    run_id: str
    user_id: str
    session_id: str
    current_user_message: str
    send_request: AgentSendRequest

    request: NotRequired[AgentRequest]
    user_context: NotRequired[dict[str, Any]]
    context_resolution: NotRequired[dict[str, Any]]
    context_packs: NotRequired[dict[str, Any]]
    compressed_context: NotRequired[dict[str, Any]]
    last_answer_memory: NotRequired[dict[str, Any]]
    turn_process_data: NotRequired[dict[str, Any] | None]
    previous_turn_process_data: NotRequired[dict[str, Any] | None]
    session_last_process_data: NotRequired[dict[str, Any] | None]
    process_data_reference_policy: NotRequired[dict[str, Any]]

    intent_gateway: NotRequired[dict[str, Any]]
    selected_path: NotRequired[SelectedPath]

    plan: NotRequired[AgentPlan]
    route: NotRequired[list[str]]
    prediction: NotRequired[PredictionResponse | None]
    manufacturing_context: NotRequired[ManufacturingContext]
    retrieved_documents: NotRequired[list[RagChunk]]
    structured_answer_payload: NotRequired[dict[str, Any]]
    safety_guidance: NotRequired[str | None]
    answer: NotRequired[str]
    report: NotRequired[str | None]

    response: NotRequired[AgentResponse]
    warnings: list[str]
    errors: list[dict[str, Any]]
    usage_records: list[LLMUsageRecord]
    trace: list[dict[str, Any]]
    replan_count: int
```

설계 원칙:

- 노드는 전체 state를 새로 만들지 않고 필요한 key만 갱신한다.
- SubAgent 내부 state는 root `AgentState`와 분리한다.
- `last_answer_memory`는 follow-up 질문 해석의 1순위 신호다.
- `user_context`는 supporting evidence이며 현재 입력, 현재 RAG, 현재 safety gate보다 우선하지 않는다.
- 이전 턴의 `process_data`는 session state에 저장하되, 단순 개념 질문에는 자동 주입하지 않는다.

---

## 5. ContextSubAgent

`request_context` root node는 `ContextInput`을 만들고 `ContextSubAgent.invoke(...)`만 호출한다.

```text
User validation
→ session upsert
→ user_context build
→ conversation context resolution
→ context pack build
→ context validation
→ AgentRequest 생성
```

SubAgent 내부 node:

```text
load_request_context
→ resolve_conversation_context
→ build_context_pack
→ validate_context
→ emit_context_output
```

여기서 중요한 점은 원문 질문과 해석 결과가 분리된다는 것이다.

```json
{
  "original_question": "그렇다면 이것의 단점은?",
  "standalone_query": "토크의 단점은?",
  "is_followup": true,
  "followup_target": "토크",
  "followup_type": "previous_concept"
}
```

---

## 6. Intent Gateway

`intent_gateway`는 모든 질문을 무겁게 처리하지 않기 위한 1차 분기점이다.

대표 분기:

| 질문 유형 | selected_path | Prediction | RAG | Safety |
|---|---|---:|---:|---:|
| `토크가 뭐야?` | `fast_concept_answer` | false | false | false |
| `이것의 단점은?` after `토크가 뭐야?` | `fast_concept_answer` | false | false | false |
| `LOTO 기준 문서로 알려줘` | `supervisor_planning` | false | true | optional |
| `이 토크 값 위험해?` + process_data | `supervisor_planning` | true | optional | possible |
| `설비 멈춰줘` | `unsupported_or_clarification` | false | false | false |

현재 테스트로 보장하는 정책:

- `process_data`가 있어도 `토크가 뭐야?`는 prediction을 실행하지 않는다.
- `이 토크 값 위험해?`는 prediction path로 간다.
- `토크가 뭐야? → 이것의 단점은?`은 `last_answer_memory.focus=토크`로 해석한다.
- `토크와 공구 마모의 차이는? → 이것의 단점은?`은 clarification으로 보낸다.

---

## 7. Fast Path

Fast Path는 일반 개념 질문을 처리한다.

```text
request_context
→ intent_gateway
→ fast_concept_answer
→ focus_updater
→ audit_persistence
```

사용하는 것:

- `standalone_query`
- `context_resolution`
- 일반 제조/기계 지식
- 최소 LLM payload

사용하지 않는 것:

- Prediction Tool
- Manufacturing Analysis
- Safety Gate
- Report Agent

Fast Path system prompt의 핵심 정책:

```text
정의, 장단점, 한계, 원리 질문에는 일반 제조/기계 지식으로 답한다.
현재 설비 상태, 고장 확률, 안전 상태는 공정 데이터와 검증 근거 없이는 단정하지 않는다.
```

---

## 8. Heavy Path

복합 제조 업무 질문은 `supervisor_planning`부터 heavy path로 들어간다.

```text
supervisor_planning
→ manufacturing_analysis
→ evidence_retrieval
→ safety
→ response_synthesis
→ response_packager
```

### 8.1 PlanningSubAgent

`supervisor_planning` root node는 `PlanningInput`을 만들고 `PlanningSubAgent.invoke(...)`만 호출한다.

```text
build_planning_context
→ run_diagnostic_planner
→ validate_plan
→ emit_planning_output
```

`AgentPlan`의 주요 필드:

```python
prediction_required: bool
rag_required: bool
safety_required: bool
asset_context_required: bool
process_condition_required: bool
failure_mode_required: bool
safety_gate_required: bool
action_plan_required: bool
required_nodes: list[str]
layers: list[AgentLayer]
rag_query: str
```

### 8.2 Manufacturing Analysis

`manufacturing_analysis`는 현재 다음을 수행한다.

```text
Prediction Tool
→ Domain Context build
→ Asset / Process / Failure / Risk context 생성
```

코드 수준:

```python
if plan.prediction_required and request.process_data:
    prediction = self.heavy_graph.prediction_service.predict(request.process_data)

manufacturing_context = self.heavy_graph.domain_service.build_context(
    request,
    prediction,
    doc_count=0,
)
```

결과는 state에 저장된다.

```python
state['prediction'] = prediction
state['manufacturing_context'] = manufacturing_context
```

### 8.3 Evidence Retrieval

`evidence_retrieval`은 RAG 내부 단계를 직접 실행하지 않는다. Root graph는
`RagEvidenceInput`을 만들고 LangGraph 기반 `RagEvidenceSubAgent`를 invoke한
뒤, 결과를 canonical state fields에 복사한다.

```text
RagEvidenceSubAgent
  -> plan_queries
  -> retrieve
  -> filter
  -> grade
  -> cite
  -> build_payload
  -> trace
```

현재 trace node:

```text
retrieval.rag_evidence_subagent
retrieval.evidence_grader
```

### 8.4 Safety

`safety` root node는 `SafetyInput`을 만들고 `SafetySubAgent.invoke(...)`만 호출한다.

```text
build_safety_context
→ apply_safety_policy
→ validate_safety_output
→ emit_safety_output
```

현재 trace node:

```text
safety.safety_subgraph
```

SafetySubAgent는 최종 답변 문장을 렌더링하지 않고 safety payload만 만든다.

### 8.5 Response Synthesis

`response_synthesis`는 LLM 답변 생성과 안전 검증을 담당한다.

```python
llm_result = self.llm_service.generate_json(
    schema_name='manufacturing_domain_agent_response',
    schema=ANSWER_SCHEMA,
    system_prompt=self.heavy_graph._answer_system_prompt(),
    payload=self.structured_payload_builder.build(...),
    operation='answer_generation',
)
```

LLM 답변 후 safety validation:

```python
validation = self.heavy_graph.safety_validator.validate_answer(
    answer or '',
    manufacturing_context,
)
```

검증 실패 시 parent replan:

```python
plan = self.heavy_graph.supervisor.replan(
    request,
    plan,
    validation.errors,
    attempt=llm_attempt + 1,
)
```

현재 trace node:

```text
response.answer_composer
supervisor.parent_replan
```

### 8.6 Documentation

별도 documentation/report node는 현재 runtime에서 사용하지 않는다. 사용자가
보고서 형식을 요청하면 `answer` 본문을 Markdown 스타일로 구성하며, 내부
run metadata와 trace는 history/debug payload에만 남긴다.

### 8.7 Response Packager

`response_packager`는 최종 `AgentResponse`를 만든다.

포함 항목:

- `answer`
- `prediction`
- `manufacturing_context`
- `retrieved_documents`
- `safety_guidance`
- `report`
- `citations`
- `warnings`
- `trace`
- `plan`
- `llm_usage`
- `context_used`

---

## 9. MemorySubAgent

`focus_updater` root node는 `MemoryInput`을 만들고 `MemorySubAgent.invoke(...)`만 호출한다. MemorySubAgent는 다음 턴의 follow-up 처리를 위해 `AnswerMemory`와 최근 turn state를 저장한다.

```text
extract_memory_candidates
→ update_focus
→ write_answer_memory
→ emit_memory_output
```

정책:

- answer memory extraction과 audit persistence를 섞지 않는다.
- MemoryService write 실패는 response 생성을 막지 않고 warning/diagnostic으로 남긴다.
- RootGraph는 memory 내부 extraction 규칙을 알지 않는다.

이 구조 덕분에 아래 대화가 동작한다.

```text
User: 토크가 뭐야?
Agent: ...
User: 그렇다면 이것의 단점은?
Agent: 여기서 "이것"은 직전 질문의 "토크"를 의미한다고 보고 답변...
```

---

## 10. Audit / Persistence

`audit_persistence`는 다음을 수행한다.

```text
trace 정규화
usage summary 보정
history 저장
context metadata 보정
```

현재 저장 대상:

- `agent_runs`
- `user_memories`
- `user_sessions`

주의:

- Fast Path 응답도 history에 저장된다.
- Memory update는 `MemorySubAgent`에서 처리되고 audit persistence는 history 저장만 맡는다.
- trace에는 raw user_id 대신 hash를 쓰는 방향이 운영 기준이다. 현재 observability 확장 시 이 정책을 유지해야 한다.

---

## 11. API 진입점

현재 주요 API:

```text
POST /agent/send
POST /agent/send/stream
POST /agent/intent
POST /agent/plan
GET  /users/{user_id}/context
GET  /users/{user_id}/history
```

`/agent/send`는 실제 LangGraph root를 실행한다.

```python
@app.post('/agent/send')
def send_agent(req: AgentSendRequest):
    return root_graph.run(req)
```

`/agent/send/stream`은 trace event를 newline-delimited JSON으로 흘려준다.

```json
{"type": "start"}
{"type": "trace", "step": {"step": "supervisor.route_planner", "detail": "..."}}
{"type": "final", "response": {...}}
```

---

## 12. 현재 테스트 보장 범위

현재 `test_intent_gateway.py`에서 보장하는 핵심 회귀:

```text
1. 명시적 개념 질문은 follow-up으로 오해하지 않음
2. 설비 제어 요청은 gateway에서 차단
3. process_data가 있어도 일반 개념 질문은 prediction 실행 안 함
4. 현재 값 위험도 질문은 prediction 필요
5. 같은 session의 last_answer_memory로 "이것" 해석
6. 비교 질문 뒤의 "이것"은 ambiguous 처리
7. heavy path가 Subgraph trace node를 생성
```

heavy path trace 테스트는 아래 노드를 검증한다.

```python
assert 'supervisor.route_planner' in trace_steps
assert 'manufacturing.prediction_tool' in trace_steps
assert 'manufacturing.analysis_subgraph' in trace_steps
assert 'retrieval.evidence_grader' in trace_steps
assert 'safety.safety_subgraph' in trace_steps
assert 'response.answer_composer' in trace_steps
```

---

## 13. 현재 구현의 한계

현재 구조는 RootGraph를 top-level orchestrator로 두고 Context, Planning, RAG Evidence, Safety, Memory를 실제 LangGraph SubAgent로 분리한 상태다. 남은 한계는 아래 정도다.

### 13.1 LangGraph Send 기반 병렬 검색 미구현

현재 RAG Evidence SubAgent는 bounded fan-out query를 순차 실행한다.

목표:

```python
from langgraph.types import Send

def dispatch_retrieval(state: AgentState):
    return [
        Send("document_retriever", {"retrieval_request": req})
        for req in state["retrieval_requests"]
    ]
```

사용처:

- 정비 문서 query
- 안전 문서 query
- 설비 매뉴얼 query
- 보고서 템플릿 query

### 13.2 Safety answer validation은 response_synthesis에 남아 있음

현재:

```text
SafetySubAgent에서 safety payload 생성
response_synthesis에서 validate_answer 실행
```

목표:

```text
Safety Subgraph
 ├─ gate_builder
 ├─ constraint_injector
 ├─ action_safety_validator
 ├─ answer_safety_validator
 ├─ report_safety_validator
 └─ escalation_decision
```

### 13.3 Report-style output

별도 documentation/report node는 현재 runtime에서 사용하지 않는다. 사용자가
보고서 형식을 요청하면 `answer` 본문을 간결한 Markdown 스타일로 구성한다.
내부 run metadata, trace, citations, usage는 history/debug payload에만 남긴다.

### 13.4 Checkpointer는 MVP용 SQLite

현재:

```python
self.checkpointer = SqliteSaver.from_conn_string(...)
```

운영 목표:

```text
SQLite / Postgres / Redis checkpointer
```

현재 SQLite persistent checkpointer는 Local/MVP에는 충분하지만, 동시 요청이 많아지는 운영 환경에서는 lock, connection pooling, horizontal scaling을 고려해 Postgres/Redis checkpointer 전환이 필요하다.

---

## 14. 다음 AI와 의논할 확장 과제

아래 순서로 확장하는 것이 가장 안전하다.

### Phase A. RAG Subgraph 실제 분리

목표:

```text
evidence_retrieval_node를 여러 LangGraph node로 분해
```

추가 state:

```python
rag_query_plan: dict
retrieval_requests: list[dict]
retrieved_documents: list[RagChunk]
evidence_candidates: list[dict]
evidence_scores: list[dict]
citations: list[dict]
```

완료 기준:

- trace에 `retrieval.rag_query_planner`, `retrieval.document_retriever`, `retrieval.evidence_grader`, `retrieval.citation_builder`가 분리 표시된다.
- weak evidence일 때 RAG 내부에서 local replan한다.

### Phase B. Chroma PDF Ingestion 연결

목표:

```text
PDF upload
→ chunking
→ embedding
→ Chroma collection 저장
→ RAG retriever가 Chroma 사용
```

추가 API 후보:

```text
POST /documents/upload
POST /documents/ingest
GET  /documents
DELETE /documents/{document_id}
```

추가 UI:

```text
Streamlit Documents 탭
PDF 업로드
인덱싱 상태
문서별 chunk count
검색 테스트
```

### Phase C. Safety Subgraph 세분화

목표:

```text
조치 계획, 최종 답변, 보고서를 각각 검증
```

완료 기준:

- action list는 안전하지만 답변이 위험한 경우를 잡는다.
- 답변은 안전하지만 보고서가 LOTO를 누락한 경우를 잡는다.
- 반복 실패 시 human escalation으로 보낸다.

### Phase D. 운영용 Checkpointer 전환

목표:

```text
동시 요청과 배포 환경을 견디는 persistent checkpointer
```

고려안:

- Postgres checkpointer
- Redis checkpointer
- user hard delete 시 checkpoint namespace 삭제 정책

완료 기준:

- 같은 `user_id + session_id`로 재접속해도 `last_answer_memory`가 유지된다.
- user hard delete 시 checkpoint도 함께 삭제된다.

### Phase E. Async Job / Event Stream

목표:

긴 작업을 `/agent/send` 동기 request에서 분리한다.

후보 API:

```text
POST /agent/jobs
GET  /agent/jobs/{job_id}
GET  /agent/jobs/{job_id}/events
POST /agent/jobs/{job_id}/cancel
```

사용처:

- 다중 문서 RAG 검색
- PDF ingestion
- multi-step evaluation

---

## 15. 다른 AI에게 전달할 핵심 요약

현재 제조 AI Agent는 `RootManufacturingGraph`를 중심으로 LangGraph `StateGraph`를 사용한다. `user_id:session_id`를 `thread_id`로 사용하고 SQLite persistent checkpointer를 붙여 같은 user/session의 `recent_turns`, `rolling_summary`, `last_answer_memory`, `session_last_process_data`를 이어간다. `ContextSubAgent`에서 user-scoped context와 follow-up resolution을 수행하고, `intent_gateway`에서 단순 개념 질문은 Fast Path로 보내며, 현재 공정 판단/점검/문서 근거 요청만 heavy path로 보낸다.

Fast Path는 토크/공구 마모/스핀들/회전수 같은 MVP 핵심 용어에 대해 glossary/template 기반 No-LLM 응답을 우선 사용한다. 따라서 단순 개념 질문은 Prediction/RAG/Safety/LLM을 호출하지 않는다. 이전 턴의 `process_data`는 “방금 데이터”, “이 토크 값”, “그 조건”처럼 명시 참조가 있을 때만 prediction에 사용된다.

Heavy path는 현재 `PlanningSubAgent → manufacturing_analysis → RagEvidenceSubAgent → SafetySubAgent → response_synthesis → response_packager`로 분리되어 trace에 Subgraph 단위로 표시된다. Prediction, domain context, RAG 검색, safety guidance, LLM answer generation은 state에 중간 산출물로 저장된다.

다음 확장의 핵심은 response synthesis까지 SubAgent boundary를 적용할지 결정하고, RAG fan-out을 LangGraph `Send` 기반 병렬 retrieval로 바꿀 필요가 있는지 검토하는 것이다. 운영 품질을 위해서는 SQLite checkpointer를 Postgres/Redis checkpointer로 전환하고, user hard delete 시 checkpoint/history/memory/vector namespace를 함께 삭제하는 정책이 필요하다.
