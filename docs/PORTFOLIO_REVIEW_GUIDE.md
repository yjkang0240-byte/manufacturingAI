# Portfolio Review Guide

포트폴리오 제출 또는 면접 시 어떤 문서를 어떤 순서로 보여줄지 정리한 안내서입니다.

## 1. 10분 Quick Review

빠르게 프로젝트의 목적과 현재 구조를 보려면 아래 순서로 읽습니다.

1. `README.md`
2. `docs/PORTFOLIO_ROADMAP.md`
3. `docs/DEMO_SCRIPT.md`

이 세 문서만 봐도 제품 목적, 실행 방법, 데모 질문, 현재 구현 범위를 설명할 수 있습니다.

## 2. Architecture Review

LangGraph/FastAPI/Agent 구조를 평가받을 때 참고할 문서입니다.

1. `docs/LANGGRAPH_FINAL_ARCHITECTURE.md`
2. `docs/rag_evidence_orchestration.md`
3. `docs/CURRENT_BACKEND_ARCHITECTURE_AUDIT.md`
4. `docs/architecture.md`

강조할 포인트:

- `RootManufacturingGraph`는 top-level LangGraph orchestrator
- `ContextSubAgent`, `PlanningSubAgent`, `RagEvidenceSubAgent`, `SafetySubAgent`, `MemorySubAgent`는 각각 독립 StateGraph
- Root graph는 RAG 내부 planner/retriever/filter/grader/citation 단계를 직접 호출하지 않음
- `/rag/search`는 제품 답변 경로가 아니라 API/debug seam

## 3. RAG / Corpus Review

RAG 품질과 운영 재현성을 보여줄 때 참고합니다.

1. `docs/rag_evidence_orchestration.md`
2. `docs/RAG_INDEX_RUNBOOK.md`
3. `docs/archive/TROUBLESHOOTING_AND_ARCHITECTURE_EVOLUTION_2026-06-13.md`

강조할 포인트:

- AI4I CSV는 prediction input이고 vector DB corpus가 아님
- RAG corpus는 OSHA/Haas/KOSHA 외부 제조 문서
- `rag_chunks.jsonl 727`과 Chroma `manufacturing_rag 727 vectors` 상태
- Chroma vector DB는 git ignored이므로 runbook으로 재색인

## 4. Troubleshooting / Engineering Maturity

프로젝트를 단순 구현물이 아니라 문제를 발견하고 고친 과정으로 보여줄 때 참고합니다.

1. `docs/archive/TROUBLESHOOTING_AND_ARCHITECTURE_EVOLUTION_2026-06-13.md`
2. `docs/ARCHITECTURE_DECISIONS.md`
3. `docs/QUALITY_CHECKLIST.md`

강조할 포인트:

- service orchestrator였던 RAG Evidence를 실제 LangGraph SubAgent로 전환
- lightweight RAG, legacy retriever, silent fallback 제거
- Chroma 702/727 불일치 진단과 복구
- `generate_report` 제거와 사용자 답변/debug 정보 분리
- AI4I incomplete feature 요청을 RAG-only 답변으로 우회하지 않도록 clarification route 적용

## 5. Live Demo 순서

1. `/health`, `/ready`, `/llm/models` 확인
2. Streamlit Agent tab 실행
3. AI4I + RAG 질문 실행
4. RAG-only safety 질문 실행
5. AI4I feature 누락 clarification 질문 실행
6. `/rag/search`로 Chroma 검색 상태 확인
7. History/debug panel에서 trace, citations, llm_usage 확인

## 6. 제출 시 추천 문서 묶음

포트폴리오에 링크할 문서는 아래 6개를 추천합니다.

```text
README.md
docs/PORTFOLIO_REVIEW_GUIDE.md
docs/PORTFOLIO_ROADMAP.md
docs/DEMO_SCRIPT.md
docs/LANGGRAPH_FINAL_ARCHITECTURE.md
docs/archive/TROUBLESHOOTING_AND_ARCHITECTURE_EVOLUTION_2026-06-13.md
```

아래 문서는 보조 자료로 둡니다.

```text
docs/rag_evidence_orchestration.md
docs/RAG_INDEX_RUNBOOK.md
docs/ARCHITECTURE_DECISIONS.md
docs/CURRENT_BACKEND_ARCHITECTURE_AUDIT.md
docs/QUALITY_CHECKLIST.md
```

## 7. 현재 문서로 쓰지 말 것

`docs/archive/` 아래 문서는 historical record입니다. 현재 운영 구조 설명에는 사용하지 말고, 문제 해결 과정이나 리팩터링 이력을 설명할 때만 참조합니다.
