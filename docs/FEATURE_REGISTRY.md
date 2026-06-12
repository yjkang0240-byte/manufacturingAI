# Feature Registry

기능을 추가할 때마다 이 문서에 누적한다.

## F-001: LLM-only Agent Runtime

- Status: done
- User value: 실제 LLM 기반 Agent 동작만 유지해 데모/운영 경로를 명확히 함
- Main files: `ai_server/app/services/llm_service.py`, `ai_server/app/agent/graph.py`, `ai_server/app/schemas.py`, `streamlit_app.py`
- API/UI entry: `/agent/send`, Streamlit Agent tab
- Data dependency: `OPENAI_API_KEY`
- Cost impact: 모든 Agent 실행이 실제 LLM 비용을 발생시킬 수 있음
- Safety impact: template/mock 응답으로 안전 검증을 흐리지 않음
- Observability: LLM usage span, agent run span
- Tests: compileall, pytest, `/health`, `/llm/models`
- Demo steps: Streamlit에서 모델 선택 후 Agent 실행
- Follow-up: 요청당 max cost guard 추가

## F-002: Supervisor Re-plan Loop

- Status: done
- User value: 근거 부족, 파싱 실패, 안전 검증 실패 시 재계획 후 재시도
- Main files: `ai_server/app/services/supervisor_service.py`, `ai_server/app/agent/graph.py`
- API/UI entry: `/agent/send/stream`, Streamlit 진행 trace
- Data dependency: RAG search results, safety validation errors
- Cost impact: re-plan과 retry가 LLM 호출 수를 늘릴 수 있음
- Safety impact: 안전 검증 실패를 반영한 재시도 가능
- Observability: `llm_usage.replan_count`
- Tests: RAG weak-context scenario, safety validator test
- Demo steps: 근거가 약한 질문에서 `Supervisor Re-plan` trace 확인
- Follow-up: re-plan 사유별 통계 추가

## F-003: Token/Cost Meter

- Status: done
- User value: 요청별 LLM 사용량과 예상 비용 확인
- Main files: `ai_server/app/services/llm_service.py`, `ai_server/app/services/observability_service.py`, `streamlit_app.py`
- API/UI entry: Agent response `llm_usage`, Streamlit metric
- Data dependency: OpenAI response `usage`
- Cost impact: 비용 가시화
- Safety impact: 없음
- Observability: `gen_ai.usage.*`, `gen_ai.request.model`
- Tests: 실제 LLM 호출 시 usage 확인, compileall, pytest
- Demo steps: Agent 실행 후 Estimated cost 확인
- Follow-up: 누적 budget, 사용자별 비용 집계

## F-004: Model Selection Policy

- Status: done
- User value: 사용 가능한 모델을 선택하되 고비용 모델은 비활성화
- Main files: `ai_server/app/config.py`, `ai_server/app/services/llm_service.py`, `ai_server/app/main.py`, `streamlit_app.py`
- API/UI entry: `/llm/models`, Streamlit model selectbox
- Data dependency: `LLM_MODEL_CATALOG`
- Cost impact: 고비용 모델 선택 방지
- Safety impact: 없음
- Observability: selected model recorded in usage records
- Tests: `/llm/models`에서 `gpt-5.5 selectable=false` 확인
- Demo steps: 모델 선택창에서 비활성 모델 목록 확인
- Follow-up: org/user role 기반 모델 정책

