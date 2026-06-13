# 작업 내역 및 보완점

## 1. 이번 업데이트에서 작업한 내용

### 1.1 외부 LLM 연동 준비

- `.env.example` 확장
- `ai_server/.env.example` 추가
- `LLM_PROVIDER=openai` 설정 시 공식 OpenAI Responses API 사용
- `LLM_PROVIDER=openai_compatible` 설정 시 OpenAI-compatible Chat Completions 사용
- API Key가 없으면 Agent 실행은 `llm_unavailable`로 실패

### 1.2 API 설계 개선

- 신규 메인 API: `POST /agent/send`
- 기존 호환 API: `POST /agent/run`
- `/agent/send`는 `message`, `session_id`, `process_data`, `inspection_notes`, `generate_report`, `mode`, `llm_model`을 받음
- Spring Boot도 `/agent/send`를 호출하도록 수정

### 1.3 Supervisor 고도화

기존 단순 키워드 분기에서 계층형 계획 생성 방식으로 변경했다.

```text
0. Input Layer
1. Supervisor Layer
2. Prediction Layer
3. Retrieval Layer
4. Safety Layer
5. Reasoning Layer
6. Documentation Layer
7. Persistence Layer
```

Supervisor는 다음 신호를 보고 실행 계획을 만든다.

| 신호 | 실행 계층 |
|---|---|
| process_data | Prediction Layer |
| 토크/공구/온도/불량/고장모드 키워드 | Prediction Layer |
| 매뉴얼/문서/도면/트러블슈팅 키워드 | Retrieval Layer |
| 안전/비상/LOTO/방호 키워드 | Safety Layer |
| 보고서/점검 결과/초안 키워드 | Documentation Layer |

### 1.4 LLM refinement 추가

- 외부 LLM이 설정되어 있으면 Supervisor의 intent와 RAG query를 refinement할 수 있음
- 단, hard signal은 제거하지 못하게 guardrail 적용
- 예: `process_data`가 있으면 LLM이 잘못 판단해도 Prediction Layer는 유지

### 1.5 Structured Output 기반 LLM 응답

외부 LLM 응답은 다음 JSON 구조를 기대한다.

```json
{
  "answer": "Markdown 답변",
  "safety_guidance": "안전 안내 또는 null",
  "recommended_actions": ["권장 조치"],
  "report": "보고서 초안 또는 null",
  "warnings": ["주의사항"]
}
```

### 1.6 RAG 검색 경량화

- 기존 TF-IDF joblib 의존 방식에서 lightweight lexical scorer로 변경
- 제한된 실행 환경에서도 sample ingestion이 안정적으로 돌아가도록 변경
- 추후 Chroma/pgvector로 교체 가능하도록 Agent API는 유지

---

## 2. 확인한 테스트

```text
- python -m compileall app scripts 성공
- python scripts/ingest_docs.py --sample-only 성공
- FastAPI TestClient /health 성공
- FastAPI TestClient /agent/send 성공
- hybrid route 생성 확인
```

확인된 `/agent/send` 응답 특징:

```text
- plan.intent = hybrid
- route에 Prediction Tool, RAG Search Agent, Safety Ops Agent, Report Agent 포함
- LLM 호출 usage/cost 집계는 `llm_usage`에 포함
- response.plan에 계층형 실행 계획 포함
```

---

## 3. 아직 보완해야 할 점

### 3.1 실제 LLM API Key 기반 검증

현재 실행 환경에는 API Key가 없어서 실제 OpenAI Responses API 호출은 검증하지 못했다.

사용자가 해야 할 일:

```bash
cp .env.example .env
# .env에 OPENAI_API_KEY 입력
uvicorn app.main:app --reload --port 8000
```

이후 `/agent/send`를 호출하면 된다.

### 3.2 Spring Boot Maven 빌드 검증

현재 실행 환경에 Maven이 없어 `mvn package`는 실행하지 못했다.

사용자 로컬에서 확인할 명령:

```bash
cd backend_spring
mvn clean package
mvn spring-boot:run
```

### 3.3 Semantic Vector DB 교체

현재 RAG는 lightweight lexical scorer다. MVP에는 충분하지만 실제 품질을 높이려면 아래 중 하나로 교체하는 것이 좋다.

```text
- Chroma
- FAISS
- PostgreSQL + pgvector
- Supabase pgvector
```

### 3.4 실제 공개 문서 수집 검증

오프라인 샘플 문서는 포함되어 있다. 실제 Haas/OSHA/KOSHA 문서 수집은 다음 명령으로 수행한다.

```bash
python scripts/collect_rag_docs.py
python scripts/extract_text.py
python scripts/ingest_docs.py
```

사이트 구조 변경이나 PDF 접근 제한이 있을 수 있으므로 실제 실행 후 chunk 품질을 확인해야 한다.

### 3.5 사내 문서 필요

실제 회사 맞춤형 Agent로 만들려면 다음 자료는 사용자가 제공해야 한다.

```text
- 사내 설비 매뉴얼
- 실제 점검 보고서 양식
- 실제 안전 절차서
- 실제 P&ID/도면
- 사내 설비 분류체계
```

---

## 4. 최종 상태

현재 ZIP은 외부 LLM이 없어도 돌아가고, 외부 LLM Key를 넣으면 LLM 기반 Supervisor refinement와 답변 생성을 사용할 수 있는 상태다.

가장 중요한 변화는 다음이다.

```text
단순 순차 실행 Agent
→ 계층형 Supervisor 기반 멀티 에이전트 구조

템플릿 답변 전용
→ 외부 LLM Structured Output 지원

/agent/run 중심
→ /agent/send 중심 API 설계
```
