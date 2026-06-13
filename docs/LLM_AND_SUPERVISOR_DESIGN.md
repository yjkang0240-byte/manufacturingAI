# 외부 LLM 연동 및 계층형 Supervisor 설계

## 1. 이번 업데이트의 목적

기존 MVP는 LLM API 없이도 동작하도록 템플릿 기반 응답을 사용했다. 이번 업데이트에서는 외부 LLM이 있다는 가정하에 다음을 보강했다.

```text
1. .env.example 기반 외부 LLM 설정
2. 공식 OpenAI Responses API 지원
3. OpenAI-compatible Chat Completions 지원
4. /agent/send 메인 API 추가
5. 계층형 Supervisor / Router 고도화
6. LLM Supervisor refinement + deterministic guardrail
7. Structured Output 기반 답변 생성
```

---

## 2. API 설계 결정

## 2.1 왜 `/agent/send`를 메인 API로 두는가?

제품 Agent API는 message/session 중심의 `/agent/send` 하나로 정리했다.

따라서 다음처럼 정리했다.

| API | 역할 | 권장 여부 |
|---|---|---|
| `POST /agent/send` | 사용자 메시지 기반 메인 Agent API | 권장 |
| `POST /predict` | 예측 Tool 단독 실행 | 내부/디버깅 |
| `POST /rag/search` | RAG 검색 단독 실행 | 내부/디버깅 |
| `POST /evaluation/score` | LLM 응답 평가 | 평가/테스트 |

---

## 2.2 `/agent/send` 요청 예시

```json
{
  "message": "토크가 높고 공구 마모가 큰데 어떤 점검과 안전 절차를 확인해야 해?",
  "session_id": "demo-session-001",
  "process_data": {
    "type": "L",
    "air_temperature_k": 302.1,
    "process_temperature_k": 311.3,
    "rotational_speed_rpm": 1380,
    "torque_nm": 58.2,
    "tool_wear_min": 210
  },
  "inspection_notes": "작업자가 공구 마모 증가와 냉각 성능 저하를 의심함",
  "mode": "auto",
  "llm_model": "gpt-5.4-mini"
}
```

---

## 3. 외부 LLM 설정

`.env.example`을 `.env`로 복사해서 설정한다.

```bash
cp .env.example .env
```

공식 OpenAI 사용:

```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-5.4-mini
OPENAI_API_KEY=your_openai_api_key_here
LLM_ENABLE_STRUCTURED_OUTPUT=true
AGENT_SUPERVISOR_LLM_REFINEMENT=true
```

OpenAI-compatible 서버 사용:

```env
LLM_PROVIDER=openai_compatible
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=dummy_or_provider_key
LLM_MODEL=your-model-name
```

API Key가 없으면 Agent 실행은 `llm_unavailable`로 실패한다.

---

## 4. LLM API 선택 근거

공식 OpenAI를 사용할 때는 Responses API를 사용한다.

이유:

```text
1. Agent workflow에 맞는 최신 인터페이스
2. function/tool calling과 결합 가능
3. Structured Output으로 JSON schema 강제 가능
4. 추후 file search, web search, MCP 등으로 확장 가능
```

OpenAI-compatible provider는 벤더마다 Responses API 지원 여부가 다르기 때문에 Chat Completions JSON mode를 사용한다.

---

## 5. 계층형 Supervisor 구조

이번 업데이트의 핵심은 Supervisor를 단순 키워드 라우터가 아니라 계층형 실행 계획 생성기로 바꾼 것이다.

```text
0. Input Layer
   └─ Input Normalizer

1. Supervisor Layer
   ├─ Intent Classifier
   └─ Route Planner

2. Prediction Layer
   ├─ Prediction Tool
   └─ Evidence Tool

3. Retrieval Layer
   ├─ RAG Query Builder
   └─ RAG Search Agent

4. Safety Layer
   └─ Safety Ops Agent

5. Reasoning Layer
   └─ Explanation Agent

6. Documentation Layer
   └─ Report Agent

7. Persistence Layer
   └─ History Store
```

---

## 6. 분기 처리 기준

| 신호 | 실행 계층 |
|---|---|
| `process_data` 있음 | Prediction Layer 필수 |
| 토크/공구/온도/불량/고장모드 키워드 | Prediction Layer |
| 매뉴얼/문서/도면/G-code/트러블슈팅 키워드 | Retrieval Layer |
| 안전/비상/LOTO/방호/인터록/회전부 키워드 | Safety Layer |
| 여러 신호가 함께 있음 | Hybrid intent |

외부 LLM이 route plan을 refinement하더라도 다음 hard signal은 제거할 수 없다.

```text
- process_data가 있으면 Prediction Layer 유지
- 안전 키워드가 있으면 Safety Layer 유지
- 보고서 형식 요청은 별도 route가 아니라 answer 본문 스타일로 처리
```

---

## 7. LLM 사용 위치

LLM은 예측을 직접 하지 않는다.

```text
Prediction Tool: 숫자 기반 예측
RAG Search Agent: 문서 검색
Safety Ops Agent: 안전 문맥 구성
LLM Explanation Agent: 위 결과를 근거로 설명 생성
LLM Report Agent: 보고서 초안 생성
```

즉, LLM은 tool 결과를 설명하는 역할이다. 이 구조가 hallucination을 줄인다.

---

## 8. Guardrail

LLM system prompt에 다음 제약을 넣었다.

```text
- 제공된 prediction, rag_contexts, actions 안의 사실만 사용
- 제공되지 않은 센서, 현장 이력, 법적 판단, 확률 생성 금지
- 설비 자동 정지/제어/수리 실행 표현 금지
- 담당자 점검 권고로 표현
- 한국어 Markdown 답변
- 판정, 주요 근거, 권장 조치, 주의 사항 섹션 포함
```

---

## 9. 수정된 주요 파일

| 파일 | 변경 내용 |
|---|---|
| `.env.example` | 외부 LLM 설정 추가 |
| `ai_server/.env.example` | AI 서버 단독 실행용 env 예시 추가 |
| `ai_server/app/config.py` | dotenv 로딩, LLM 설정 추가 |
| `ai_server/app/schemas.py` | AgentSendRequest, AgentPlan, AgentLayer 추가 |
| `ai_server/app/services/llm_service.py` | OpenAI Responses / OpenAI-compatible LLM adapter 추가 |
| `ai_server/app/services/supervisor_service.py` | 계층형 Supervisor 구현 |
| `ai_server/app/agent/graph.py` | 계층형 실행 흐름과 LLM 답변 생성 반영 |
| `ai_server/app/main.py` | `/agent/send` 추가, health에 LLM 상태 표시 |
| `backend_spring/*` | Spring Boot가 `/agent/send`를 호출하도록 보강 |
| `README.md` | 외부 LLM 설정과 API 설명 업데이트 |

---

## 10. 테스트 결과

현재 환경에는 실제 API Key가 없으므로 외부 LLM 호출은 수행하지 않았다.

확인한 항목:

```text
- Python compileall 성공
- 샘플 RAG chunk 인덱스 생성 성공
- /agent/send FastAPI TestClient 호출 성공
- 계층형 plan 생성 확인
- process_data + 안전 질문 + report 요청 시 hybrid intent 확인
- route에 Prediction / Retrieval / Safety / Explanation / Report / Persistence 계층 포함 확인
```

Maven은 현재 실행 환경에 설치되어 있지 않아 Spring Boot `mvn package`는 수행하지 못했다. Java 코드는 구조상 `/agent/send` 호출로 변경했다.
