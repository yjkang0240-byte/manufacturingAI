# Architecture Decisions

## ADR-001: LLM-only Runtime

- Date: 2026-06-12
- Status: accepted
- Context: template/mock 경로와 `use_llm=false` 옵션이 실제 운영 경로와 테스트 경로를 혼재시켰다.
- Decision: Agent 실행은 OpenAI 또는 OpenAI-compatible LLM 설정이 있어야 가능하게 한다.
- Alternatives: API key가 없을 때 템플릿 답변으로 대체.
- Consequences: 포트폴리오 데모는 실제 LLM 비용이 발생하지만, 동작 경로가 명확해진다.
- Related features: F-001

## ADR-002: Usage-based Cost Calculation

- Date: 2026-06-12
- Status: accepted
- Context: 토큰 추정은 실제 과금과 오차가 크다.
- Decision: OpenAI 응답 `usage`에서 input/output/cached tokens를 읽고, 내부 가격표로 예상 비용을 계산한다.
- Alternatives: tokenizer 기반 사전 추정, OpenTelemetry metric만 사용.
- Consequences: 응답을 받은 뒤 비용을 정확히 집계할 수 있다. 사전 예산 차단은 별도 기능이 필요하다.
- Related features: F-003

## ADR-003: Domain Catalog as YAML

- Date: 2026-06-12
- Status: accepted
- Context: 설비, 고장모드, 안전 절차는 계속 바뀌며 코드보다 설정으로 관리하는 편이 낫다.
- Decision: equipment taxonomy, failure mode, safety gate, action catalog를 YAML로 분리한다.
- Alternatives: Python 코드에 하드코딩, DB 관리.
- Consequences: 포트폴리오 데모에서는 읽기 쉽고, 운영 확장 시 DB/관리 UI로 이전 가능하다.
- Related features: Domain Modeling

## ADR-004: Safety Failure Blocks Response

- Date: 2026-06-12
- Status: accepted
- Context: 안전 검증 실패를 조용히 대체 답변으로 숨기면 위험한 응답 품질 문제가 드러나지 않는다.
- Decision: 안전 검증 실패는 re-plan 후 재시도하고, 최종 실패 시 차단한다.
- Alternatives: 템플릿 안전 답변으로 대체.
- Consequences: 실패가 사용자에게 노출될 수 있지만, 안전 기준을 우선한다.
- Related features: F-002

## ADR-005: Expensive Model Disabled by Policy

- Date: 2026-06-12
- Status: accepted
- Context: 포트폴리오 데모 중 고비용 모델을 실수로 선택할 수 있다.
- Decision: 모델 catalog에 `selectable` 정책을 두고 UI/API 양쪽에서 제한한다.
- Alternatives: UI에서만 숨김, 사용자에게 경고만 표시.
- Consequences: 정책이 서버에서 강제되므로 UI 우회 요청도 막을 수 있다.
- Related features: F-004

## ADR-006: User Context Is Supporting Evidence Only

- Date: 2026-06-12
- Status: accepted
- Context: 유저별 과거 대화와 memory를 LLM에 넣으면 편의성은 좋아지지만, 과거 정보가 현재 센서값이나 안전 판단을 덮어쓸 위험이 있다.
- Decision: user context는 supporting evidence로만 사용하고, 현재 입력, 현재 RAG 문서, 현재 safety gate를 최우선으로 둔다.
- Alternatives: 최근 대화 전체를 prompt에 그대로 삽입.
- Consequences: context 품질은 더 안정적이지만, ContextBuilder와 MemoryService 구현이 필요하다.
- Related features: F-005

## ADR-007: RAG Evidence Is A LangGraph SubAgent

- Date: 2026-06-13
- Status: accepted
- Context: 기존 RAG Evidence 흐름은 class method pipeline에 가까워 Root graph와 책임 경계가 불명확했다.
- Decision: query planning, retrieval, filtering, grading, citation, payload, trace를 `RagEvidenceSubAgent(StateGraph)` node로 분리한다.
- Alternatives: service orchestrator 유지, Root graph 내부에서 RAG 단계를 직접 호출.
- Consequences: Root graph는 RAG 내부 단계를 몰라도 되며, RAG runtime state와 trace를 독립적으로 테스트할 수 있다.
- Related features: F-003, F-004

## ADR-008: Single Agent-Internal RAG Production Path

- Date: 2026-06-13
- Status: accepted
- Context: lightweight RAG, legacy retriever, lexical fallback, direct `RagService.search()` 호출이 섞이면 답변 경로가 불명확해진다.
- Decision: agent 내부 RAG production path는 `RagEvidenceSubAgent` 하나로 통일하고, `/rag/search`는 API/debug seam으로만 유지한다.
- Alternatives: lightweight RAG와 heavy RAG를 병행 유지.
- Consequences: 구조는 단순해지고 silent fallback 위험은 줄지만, RAG 품질 문제는 SubAgent 안에서 직접 해결해야 한다.
- Related features: F-003, F-004

## ADR-009: Public Report Option Removed

- Date: 2026-06-13
- Status: accepted
- Context: `generate_report` 옵션은 사용자 입력, route, formatter, UI를 복잡하게 만들었고 일반 답변과 긴 보고서가 혼재됐다.
- Decision: 사용자/API/UI에서 report generation option을 제거하고, run metadata와 trace는 내부 history/debug에만 저장한다.
- Alternatives: checkbox 기본값을 true로 변경, report route를 adapter로 유지.
- Consequences: 사용자 답변은 간결해지고 endpoint contract가 단순해진다. “보고서 형식” 요청은 별도 mode가 아니라 Markdown 답변 스타일로 처리한다.
- Related features: F-009

## ADR-010: Chroma Index Is Rebuilt From JSONL Source Of Truth

- Date: 2026-06-13
- Status: accepted
- Context: vector DB는 git ignored이고 한 환경에서 `rag_chunks.jsonl 727`과 Chroma 702 불일치가 발생했다.
- Decision: `rag_chunks.jsonl`을 source of truth로 보고, 새 환경에서는 `scripts/index_rag_chunks_chroma.py --reset`으로 Chroma를 재색인한다.
- Alternatives: vector DB를 git에 포함, 자동 sync/repair tool 추가.
- Consequences: repository는 가벼워지고 재현 절차가 명확해진다. 단, 새 환경에서는 OpenAI embedding key와 runbook 실행이 필요하다.
- Related features: F-008
