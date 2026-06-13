# Portfolio Roadmap

작성일: 2026-06-13

이 문서는 포트폴리오 검토자가 프로젝트의 현재 완성도, 설계 의도, 남은 개선 방향을 빠르게 이해하도록 정리한 문서입니다. 과거 구현 이력은 `docs/archive/`를 참고하고, 현재 운영 구조는 이 문서를 기준으로 봅니다.

## 1. 프로젝트 한 줄 소개

AI4I 제조 공정 예측, OSHA/Haas/KOSHA 문서 기반 RAG, YAML 안전 게이트, LangGraph SubAgent orchestration, token/cost 관측을 결합한 제조 특화 AI Agent 서버입니다.

## 2. 현재 제품 구조

```text
POST /agent/send
  -> RootManufacturingGraph(StateGraph)
      -> ContextSubAgent
      -> PlanningSubAgent
      -> manufacturing_analysis
      -> RagEvidenceSubAgent
      -> SafetySubAgent
      -> response_synthesis
      -> response_packager
      -> MemorySubAgent
      -> audit_persistence
```

`/rag/search`는 Root graph 답변 경로가 아니라 Chroma 검색을 확인하기 위한 API/debug seam입니다.

## 3. 포트폴리오에서 강조할 구현 포인트

| 영역 | 현재 구현 | 강조 포인트 |
| --- | --- | --- |
| FastAPI 제품 API | `/agent/send`, `/agent/send/stream`, `/rag/search` | 실제 서버 API와 Streamlit 데모 UI가 분리됨 |
| LangGraph orchestration | Root graph + 5개 SubAgent | 큰 graph를 책임별 StateGraph로 분리 |
| AI4I prediction | 6개 필수 feature가 완전할 때만 예측 | 불완전하면 clarification으로 종료하고 RAG를 실행하지 않음 |
| RAG Evidence | Chroma `manufacturing_rag`, 727 vectors | AI4I CSV가 아니라 OSHA/Haas/KOSHA 문서만 corpus로 사용 |
| Adaptive RAG | prediction_plus_rag, rag_only_safety, troubleshooting_rag, concept_explanation | 질문 유형별 retrieval profile과 evidence selection 분리 |
| Safety gate | `safety_gate_matrix.yaml` + `SafetySubAgent` | LOTO, 회전부 방호, 정비 자격 등 deterministic policy 적용 |
| 안전 검증 | Safety validator + replan/차단 | 필수 안전 내용 누락 또는 금지 표현을 최종 응답 전에 차단 |
| Context/Memory | ContextSubAgent, MemorySubAgent, checkpoint/history | user/session별 follow-up context 유지 |
| Observability | llm usage, trace, run history | token, cost, route, citation, warnings를 내부 기록으로 보존 |
| Streamlit UI | Agent 실행, 진행 trace, RAG 확인 | 데모와 디버깅에 필요한 화면 제공 |

## 4. 중요한 설계 경계

### AI4I와 RAG 분리

AI4I 데이터는 예측 입력입니다. Vector DB에 넣지 않습니다.

```text
AI4I feature
  -> PredictionService

OSHA / Haas / KOSHA documents
  -> rag_chunks.jsonl
  -> Chroma
  -> RagEvidenceSubAgent
```

### 사용자 답변과 debug 정보 분리

사용자-facing answer에는 `run_id`, model, token, cost, calls, raw score, chunk id, safety gate id를 출력하지 않습니다. 이 정보는 response debug, trace, history, Streamlit 상세 패널에서만 확인합니다.

### 보고서 옵션 제거

`generate_report`는 사용자/API/UI 입력에서 제거했습니다. 내부 실행 기록은 계속 저장하지만, 사용자는 항상 일반 답변을 받습니다. “보고서 형식으로 정리해줘”는 별도 report mode가 아니라 Markdown 답변 스타일로 처리합니다.

## 5. 현재 검증 상태

```text
Full test snapshot: 93 passed
RAG corpus: rag_chunks.jsonl 727
Chroma collection: manufacturing_rag 727 vectors
```

Chroma vector DB는 git ignored입니다. 새 환경에서는 `docs/RAG_INDEX_RUNBOOK.md` 절차로 `rag_chunks.jsonl`에서 재색인합니다.

## 6. 데모 시나리오

1. AI4I + RAG
   - 6개 feature를 모두 포함한 질문
   - prediction_called=true
   - prediction_plus_rag profile
   - 공구 마모/TWF 해석 + 안전 확인 + citation

2. RAG-only safety
   - 드릴기/공구 교체/방호덮개/비상정지 질문
   - prediction_called=false
   - AI4I 확률 문구 없음
   - rag_only_safety profile
   - 장비명 title/metadata supplement로 관련 KOSHA 문서 우선

3. AI4I clarification
   - Type, Torque만 주고 예측 요청
   - missing_ai4i_features
   - RAG 실행 없이 누락 feature만 재요청

4. Haas troubleshooting
   - 스핀들 이상음, 진동, 경보 질문
   - troubleshooting_rag profile
   - Haas troubleshooting + 필요한 안전 문서 citation

## 7. 남은 개선 우선순위

| Priority | 항목 | 이유 | 완료 기준 |
| --- | --- | --- | --- |
| P0 | Golden evaluation set | RAG/안전/예측 품질 회귀 방지 | 대표 질의 30개, 기대 route/citation/safety 기준 |
| P0 | 답변 품질 평가 자동화 | LLM 답변은 테스트만으로 품질 보장이 어려움 | unsupported claim, citation coverage, safety omission 측정 |
| P1 | 운영 모니터링 | token/cost/latency/error를 장기 추적해야 함 | OTLP exporter 또는 dashboard 연결 |
| P1 | History schema versioning | 응답 구조 변경 시 과거 이력 해석 필요 | `schema_version`, migration policy |
| P1 | Corpus metadata 강화 | 설비/업종/문서 적용 범위를 더 정교하게 필터링 | source version, equipment scope, effective date |
| P2 | Admin/debug UI | 운영자가 corpus 상태와 run trace를 쉽게 확인 | 별도 admin panel 또는 read-only dashboard |
| P2 | Corpus versioning | 현재는 runbook 기반 재색인 | corpus manifest, vector count audit, release note |
| P2 | 배포 패키징 | 포트폴리오 재현성 강화 | Docker compose, healthcheck, env template |

## 8. 포트폴리오 참고 문서

검토자는 아래 순서로 보면 됩니다.

1. `README.md`
2. `docs/PORTFOLIO_REVIEW_GUIDE.md`
3. `docs/DEMO_SCRIPT.md`
4. `docs/LANGGRAPH_FINAL_ARCHITECTURE.md`
5. `docs/rag_evidence_orchestration.md`
6. `docs/archive/TROUBLESHOOTING_AND_ARCHITECTURE_EVOLUTION_2026-06-13.md`

`docs/archive/` 문서는 현재 운영 매뉴얼이 아니라 문제 해결과 구조 진화 기록입니다.
