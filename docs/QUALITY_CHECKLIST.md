# Quality Checklist

기능을 추가하거나 구조를 바꿀 때마다 아래 항목을 확인한다.

## 공통 체크리스트

- [ ] API schema가 기존 주요 응답과 충돌하지 않는다.
- [ ] Streamlit에서 해당 기능을 실행하거나 확인할 수 있다.
- [ ] LLM 호출 횟수와 비용 증가가 의도된 수준이다.
- [ ] 고비용 모델 정책을 우회하지 않는다.
- [ ] Safety gate 검증을 우회하지 않는다.
- [ ] History에 필요한 metadata가 저장된다.
- [ ] OpenTelemetry attribute가 필요한 만큼 기록된다.
- [ ] pytest 또는 golden test가 추가됐다.
- [ ] README, Portfolio Roadmap, Feature Registry가 갱신됐다.

## LLM 기능 추가 시

- [ ] structured output schema가 정의됐다.
- [ ] JSON parse 실패 시 재시도 또는 명확한 오류 처리가 있다.
- [ ] usage/cost가 `llm_usage.records`에 누적된다.
- [ ] 요청당 예상 비용이 너무 커지지 않는다.

## RAG 기능 추가 시

- [ ] source, title, section, url, score metadata가 유지된다.
- [ ] citation 없이 단정하는 답변을 막는 테스트가 있다.
- [ ] 검색 실패 시 re-plan 또는 명확한 오류 처리가 있다.

## Safety 기능 추가 시

- [ ] 필수 확인사항과 금지 표현이 테스트에 포함됐다.
- [ ] 담당자 검토 필요 여부가 응답에 반영된다.
- [ ] unsafe response가 차단되는지 테스트했다.

