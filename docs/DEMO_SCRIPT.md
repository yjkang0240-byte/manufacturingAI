# Demo Script

포트폴리오 시연용 순서.

## 1. 서버 상태 확인

```bash
curl http://localhost:8000/health
```

설명 포인트:

- LLM provider/model
- RAG chunk count
- domain catalog loading status
- expensive model policy

## 2. 모델 정책 확인

```bash
curl http://localhost:8000/llm/models
```

설명 포인트:

- `gpt-5.4-mini` 추천
- `gpt-5.5`는 high-cost 모델이라 `selectable=false`

## 3. Streamlit 실행

```bash
streamlit run streamlit_app.py
```

브라우저:

```text
http://localhost:8501
```

## 4. Agent 시연 질문

```text
토크가 높고 공구 마모가 큰데 어떤 점검과 안전 절차를 확인해야 해?
```

설정:

- 공정 데이터 포함 ON
- 모델: GPT-5.4 mini

## 5. 진행 과정 설명

Streamlit 진행 trace에서 아래 순서를 설명한다.

```text
Input Normalizer
Manufacturing Supervisor / Router
Prediction Tool
Asset Context Agent
Process Condition Agent
Failure Mode Agent
Risk & Priority Agent
Procedure Retrieval Agent
Safety Gate Agent
Action Planner Agent
Explanation Agent
Safety Validator
Report Agent
Evaluation / Audit Agent
```

## 6. 비용/토큰 설명

답변 위 metric에서 확인한다.

```text
LLM calls
Re-plans
Input tokens
Output tokens
Total tokens
Estimated cost
```

## 7. History 확인

History 탭에서 실행 이력을 불러온다.

설명 포인트:

- 실행 trace 저장
- LLM usage 저장
- 예상 비용 저장
- 답변/보고서/근거 문서 저장

## 8. 안전성 설명

강조할 점:

- 설비 직접 제어 없음
- LOTO, 회전부, 전기 격리 등 safety gate 반영
- 안전 검증 실패 시 re-plan 후 최종 차단
- 실제 작업은 담당자/안전관리자 검토 필요
