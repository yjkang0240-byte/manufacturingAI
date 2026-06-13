# Historical Record

This document records intermediate RAG/vector work. It is not the current
runtime contract. Current runtime uses `RagEvidenceSubAgent` and
`app.services.chroma_retriever.ChromaRetriever`.

# RAG Vector DB and Manufacturing Sub-Agent Architecture Record

이 문서는 제조 AI Agent 프로젝트에서 **외부 RAG 데이터 수집 및 Chroma Vector DB 구축**과 **제조 Sub-Agent 구조 분리**에 집중해 정리한 상세 기록이다.

목표는 단순히 “문서를 다운로드했다” 또는 “모듈을 나눴다”가 아니라, 아래 관점에서 설명하는 것이다.

- 기존 구조는 어떤 문제가 있었는가
- 왜 외부 문서 Vector DB가 필요한가
- 왜 전체 데이터를 다 받지 않고 AI4I와 관련된 문서부터 선별했는가
- 어떤 코드가 어떤 책임을 맡는가
- 실제 생성된 Vector DB 결과는 무엇인가
- Sub-Agent 구조가 어떻게 바뀌었는가
- 앞으로 어떤 연결 작업이 남았는가

---

## 1. 배경

현재 프로젝트는 AI4I 기반 제조 AI Agent다.

AI4I 데이터는 다음과 같은 공정 수치를 제공한다.

```text
type
air_temperature_k
process_temperature_k
rotational_speed_rpm
torque_nm
tool_wear_min
```

이 데이터는 예측 모델에는 적합하지만, 그 자체만으로는 다음 질문에 충분히 답하기 어렵다.

```text
토크가 높고 공구 마모가 큰데 어떤 점검을 해야 해?
정비 전에 어떤 안전 절차를 확인해야 해?
보고서에는 어떤 문구를 넣어야 해?
LOTO나 회전부 방호는 언제 확인해야 해?
```

즉, AI4I CSV는 **예측 모델 입력 데이터**이고, Vector DB에는 넣지 않는다.

Vector DB에는 다음 역할을 하는 외부 문서를 넣어야 한다.

```text
AI4I 예측 결과
  -> 고장모드/위험 신호
  -> 정비 절차
  -> 안전 확인
  -> 보고서 문구
```

이를 위해 OSHA, Haas, KOSHA 문서를 RAG source로 수집했다.

---

## 2. 기존 구조의 문제

### 2.1 RAG 근거 데이터가 부족했다

초기 구조에서는 RAG가 존재하더라도, 제조 도메인에서 실제로 쓸 수 있는 근거 corpus가 부족했다.

기존 문제:

```text
- AI4I 예측은 되지만 정비 절차 근거가 약함
- 안전 절차 설명이 일반 문구에 가까움
- OSHA/Haas/KOSHA 공식 문서 기반 citation이 부족함
- 보고서 문구를 뒷받침할 문서 metadata가 부족함
```

예를 들어 Agent가 OSF/TWF 가능성을 판단해도, 실제 답변에는 아래 근거가 필요하다.

```text
- 공구 마모 점검
- 스핀들 부하 점검
- 정비 전 에너지 차단
- 회전부 접근 전 방호장치 확인
- 자격 있는 담당자 확인
```

이 근거는 AI4I CSV row에서 나오는 것이 아니라 외부 문서에서 가져와야 한다.

### 2.2 외부 데이터를 무작정 많이 넣는 방식은 위험했다

처음에는 KOSHA 문서를 넓게 수집할 수 있었다.

하지만 전체 문서를 무작정 Vector DB에 넣으면 다음 문제가 생긴다.

```text
- 현재 AI4I MVP와 관련 없는 건설/보건/화학 문서가 검색될 수 있음
- 정비/점검 질문에 작업환경측정 문서가 섞일 수 있음
- token/cost 증가
- retrieval noise 증가
- safety 문서와 일반 보건 문서의 우선순위가 섞임
```

따라서 방향을 바꿨다.

```text
전체 수집
  -> 현재 AI4I 데이터와 직접 관련 있는 문서 우선 수집
```

---

## 3. 현재 AI4I MVP 기준 RAG 수집 전략

### 3.1 AI4I 주요 신호

현재 MVP에서 특히 중요한 신호는 다음이다.

| 신호 | 의미 | 연결되는 문서 |
| --- | --- | --- |
| `torque_nm` | 회전 부하, 과부하 가능성 | 스핀들 부하, 절삭 저항, LOTO |
| `tool_wear_min` | 공구 마모 | 공구 점검, 공구 교체, 품질 저하 |
| `rotational_speed_rpm` | 회전수 | 회전부 방호, 스핀들 상태 |
| `air_temperature_k` | 주변 온도 | 방열, 작업환경 |
| `process_temperature_k` | 공정 온도 | 냉각/방열, 열 관련 이상 |

### 3.2 우선 수집 키워드

현재 `ai4i-mvp` profile은 다음 KOSHA 키워드만 우선 수집한다.

코드 위치:

```text
ai_server/scripts/run_rag_vector_pipeline.py
```

```python
AI4I_MVP_KOSHA_KEYWORDS = [
    '정비',
    '점검',
    '공작기계',
    '회전부',
    '방호',
    '안전장치',
    '끼임',
    '절삭',
    '에너지 차단',
    '잠금표지',
]
```

이 키워드를 선택한 이유는 다음과 같다.

| 키워드 | 선택 이유 |
| --- | --- |
| 정비 | 물리 점검/수리/교체 전 절차와 직접 연결 |
| 점검 | 고장 가능성 판단 후 확인해야 할 현장 조치 |
| 공작기계 | AI4I 설비를 CNC/공작기계 계열로 설명하기 좋음 |
| 회전부 | 스핀들, 공구, 축 등 회전 설비와 연결 |
| 방호 | 기계 방호장치, 회전부 접근 통제 |
| 안전장치 | 인터록, 비상정지, 방호장치 |
| 끼임 | 회전부/구동부 안전 위험 |
| 절삭 | 공구 마모, 절삭 저항, 토크 상승과 연결 |
| 에너지 차단 | LOTO와 직접 연결 |
| 잠금표지 | Lockout/Tagout 한국어 근거 |

### 3.3 우선 수집 static source

OSHA/Haas는 전체 사이트 크롤링을 하지 않고, manifest에 등록된 핵심 source만 받는다.

현재 `ai4i-mvp` profile에서 사용하는 static source:

```python
AI4I_MVP_STATIC_SOURCE_IDS = {
    'osha_loto_1910_147',
    'osha_machine_guarding_1910_212',
    'haas_mill_spindle_troubleshooting',
    'haas_spindle_drive_troubleshooting',
}
```

역할:

| Source | 역할 |
| --- | --- |
| OSHA 1910.147 | LOTO / 에너지 차단 근거 |
| OSHA 1910.212 | machine guarding / 회전부 방호 근거 |
| Haas mill spindle troubleshooting | 스핀들/공구/부하 점검 근거 |
| Haas spindle drive troubleshooting | spindle load, motor, dull tool 관련 근거 |

---

## 4. End-to-End RAG Vector Pipeline

### 4.1 실행 명령

기본 실행 명령:

```bash
cd ai_server

../.venv312/bin/python scripts/run_rag_vector_pipeline.py \
  --profile ai4i-mvp \
  --num-rows 20 \
  --pages 1 \
  --reset-chroma
```

이 명령은 현재 AI4I MVP에 필요한 범위만 수집한다.

넓게 수집하려면 다음 profile을 사용할 수 있다.

```bash
# KOSHA primary keyword 전체
../.venv312/bin/python scripts/run_rag_vector_pipeline.py \
  --profile primary \
  --num-rows 20 \
  --pages 1 \
  --reset-chroma

# primary + secondary 전체
../.venv312/bin/python scripts/run_rag_vector_pipeline.py \
  --profile full \
  --num-rows 50 \
  --pages 3 \
  --reset-chroma
```

단, 기본은 `ai4i-mvp`가 맞다.

이유:

```text
MVP에서는 많이 넣는 것보다 현재 질문/데이터와 직접 관련 있는 문서만 넣는 것이 중요하다.
```

### 4.2 파이프라인 흐름

```text
run_rag_vector_pipeline.py
  -> download_static_rag_sources.py
  -> download_kosha_sources.py
  -> build_rag_documents.py
  -> build_rag_chunks.py
  -> inspect_rag_corpus.py
  -> index_rag_chunks_chroma.py
```

상세 흐름:

```text
1. OSHA/Haas static source 다운로드
2. KOSHA API keyword 검색
3. KOSHA fileDownloadUrl 첨부 파일 다운로드
4. HTML/PDF/HWPX 텍스트 추출
5. 문서별 metadata 생성
6. rag_documents.jsonl 생성
7. chunk 생성
8. rag_chunks.jsonl 생성
9. corpus report 생성
10. OpenAI embedding 생성
11. Chroma collection upsert
```

### 4.3 주요 코드 책임

| 파일 | 책임 |
| --- | --- |
| `run_rag_vector_pipeline.py` | 전체 pipeline orchestration |
| `download_static_rag_sources.py` | OSHA/Haas manifest URL 다운로드 |
| `download_kosha_sources.py` | KOSHA API 조회 및 첨부 파일 다운로드 |
| `build_rag_documents.py` | raw file에서 document JSONL 생성 |
| `build_rag_chunks.py` | document text를 chunk로 분할 |
| `inspect_rag_corpus.py` | corpus 통계 report 생성 |
| `index_rag_chunks_chroma.py` | OpenAI embedding + Chroma upsert |
| `rag_pipeline_utils.py` | 공통 path/env/extract/chunk/write 유틸 |

---

## 5. KOSHA API 처리 상세

### 5.1 실제 응답 필드 차이 대응

초기 문서상 예상 필드는 다음이었다.

```text
fileDownlUrl
```

하지만 실제 KOSHA API 응답에서는 다음 필드가 내려왔다.

```text
fileDownloadUrl
```

따라서 둘 다 지원하도록 수정했다.

```python
def file_download_url(item: dict) -> str:
    return str(
        item.get('fileDownlUrl')
        or item.get('fileDownloadUrl')
        or item.get('file_download_url')
        or ''
    ).strip()
```

이 수정 전에는 KOSHA API 목록은 받아도 첨부 파일 다운로드가 0건이었다.

수정 후:

```text
KOSHA 문서: 40개
file_failures: 0
```

### 5.2 API key redaction

KOSHA 요청 URL에는 `serviceKey`가 포함된다.

에러 로그나 pipeline summary에 그대로 남으면 보안상 위험하다.

따라서 다음 처리를 추가했다.

```python
redacted = re.sub(r'(serviceKey=)[^&\s)]+', r'\1<redacted>', redacted)
```

검증:

```text
serviceKey / KOSHA_API_KEY / OPENAI_API_KEY 검색 결과: 0건
```

### 5.3 Atomic write

긴 다운로드 중 중단하면 JSONL이 깨질 수 있었다.

실제로 전체 수집 중 중단했을 때 `rag_documents.jsonl`이 partial write 상태가 되어 JSON decode error가 발생했다.

해결:

```python
tmp = path.with_suffix(path.suffix + '.tmp')
tmp.write_text(...)
tmp.replace(path)
```

이제 JSON/JSONL은 임시 파일에 먼저 쓴 뒤 replace한다.

---

## 6. Document and Chunk Generation

### 6.1 Document schema

`rag_documents.jsonl`의 각 line은 문서 단위다.

주요 필드:

```json
{
  "doc_id": "kosha_C-C-52-2026",
  "source": "KOSHA",
  "title": "가동전 안점점검에 관한 기술지원규정",
  "url": "...",
  "local_path": "...",
  "doc_type": "korean_maintenance_guidance",
  "safety_gate": "maintenance_check",
  "failure_modes": ["OSF", "TWF", "PWF", "HDF"],
  "related_signals": ["torque_nm", "tool_wear_min", "..."],
  "project_priority": "high",
  "retrieval_scope": "default",
  "use_case": "정비/점검/유지관리 질문 및 보고서 보조",
  "text": "..."
}
```

### 6.2 Chunk schema

`rag_chunks.jsonl`의 각 line은 검색 단위다.

주요 필드:

```json
{
  "chunk_id": "kosha_C-C-52-2026_0001",
  "doc_id": "kosha_C-C-52-2026",
  "source": "KOSHA",
  "title": "...",
  "doc_type": "korean_maintenance_guidance",
  "safety_gate": "maintenance_check",
  "failure_modes": ["OSF", "TWF", "PWF", "HDF"],
  "related_signals": ["torque_nm", "tool_wear_min"],
  "project_priority": "high",
  "retrieval_scope": "default",
  "chunk_index": 0,
  "text": "..."
}
```

### 6.3 Chunking policy

현재 기본값:

```text
chunk_size = 1000
chunk_overlap = 150
```

문장 경계를 최대한 유지하는 `sentence_aware_chunks()`를 사용한다.

metadata-only 문서는 chunking 대상에서 제외된다.

---

## 7. Chroma Vector DB 구축

### 7.1 Embedding provider

기본 embedding provider:

```text
openai
```

기본 embedding model:

```text
text-embedding-3-small
```

환경변수:

```env
RAG_EMBEDDING_PROVIDER=openai
RAG_EMBEDDING_MODEL=text-embedding-3-small
CHROMA_COLLECTION=manufacturing_rag
CHROMA_PERSIST_DIR=ai_server/data/vector_db/chroma
```

### 7.2 Indexing flow

`index_rag_chunks_chroma.py`는 다음을 수행한다.

```text
rag_chunks.jsonl 읽기
  -> chunk text 추출
  -> metadata normalize
  -> OpenAI embeddings.create(...)
  -> Chroma PersistentClient
  -> collection.upsert(...)
```

### 7.3 Metadata normalization

Chroma metadata는 primitive type 위주로 받아야 하므로 list/dict를 변환한다.

예:

```python
if isinstance(value, list):
    return ','.join(str(item) for item in value)
if isinstance(value, dict):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
```

이렇게 해야 Chroma metadata filter와 collection 저장이 안정적으로 동작한다.

### 7.4 실제 생성 결과

최종 실행 결과:

```text
profile: ai4i-mvp
KOSHA documents: 40
total documents: 44
chunks: 727
Chroma vectors: 727
collection: manufacturing_rag
embedding model: text-embedding-3-small
persist dir: ai_server/data/vector_db/chroma
```

Chroma count 확인:

```bash
cd ai_server
../.venv312/bin/python -c "import chromadb; c=chromadb.PersistentClient(path='data/vector_db/chroma').get_collection('manufacturing_rag'); print(c.count())"
```

출력:

```text
727
```

---

## 8. Corpus Report 결과

생성 파일:

```text
ai_server/data/processed/rag_corpus_report.md
```

현재 요약:

```text
전체 문서 수: 44
전체 chunk 수: 727
```

source별 문서 수:

```text
KOSHA: 40
OSHA: 2
Haas: 2
```

source별 chunk 수:

```text
KOSHA: 657
OSHA: 45
Haas: 25
```

doc_type별 문서 수:

```text
korean_machine_safety: 21
korean_maintenance_guidance: 18
safety_standard: 2
troubleshooting: 2
korean_safety_reference: 1
```

safety_gate별 chunk 수:

```text
maintenance_check: 334
machine_guarding: 307
loto: 41
qualified_maintenance: 25
general_safety: 20
```

이 결과는 현재 목표와 잘 맞는다.

이유:

```text
AI4I MVP에서 필요한 주요 RAG 근거는
정비/점검, machine guarding, LOTO, 공작기계 안전 문서이기 때문이다.
```

---

## 9. RAG Vector DB가 Agent에서 맡는 역할

Vector DB는 예측 모델을 대체하지 않는다.

역할은 다음과 같다.

```text
Prediction Tool
  -> 현재 process_data 기반 위험/고장 가능성 판단

Vector DB / RAG
  -> 그 판단을 설명할 정비/안전/문서 근거 제공
```

예시:

```text
Input:
  torque_nm 높음
  tool_wear_min 높음

Prediction:
  OSF/TWF 가능성 증가

RAG:
  Haas spindle/tool wear troubleshooting
  KOSHA 공작기계 정비/방호 기술지침
  OSHA LOTO / machine guarding

Answer:
  공구 상태 확인
  스핀들 부하 확인
  회전부 접근 전 방호 확인
  물리 점검 전 LOTO 확인
  담당자 점검 필요
```

즉, RAG Vector DB는 다음 layer다.

```text
Evidence Layer
```

---

## 10. Sub-Agent 구조 구축 배경

### 10.1 기존 구조

초기에는 `ManufacturingAgentGraph.run()` 안에 많은 책임이 있었다.

대략 다음 흐름이었다.

```text
ManufacturingAgentGraph.run()
  -> plan
  -> prediction
  -> domain context
  -> RAG query
  -> retrieval
  -> safety guidance
  -> recommendation
  -> answer payload
  -> formatter
```

문제:

```text
- 함수 하나가 너무 많은 책임을 가짐
- RAG query와 retrieval/evidence grading/citation이 섞임
- safety gate와 safety message가 섞임
- recommendation과 answer formatting이 섞임
- private helper wrapper가 실제 책임 위치를 숨김
- LangGraph subgraph로 확장하기 어려움
```

### 10.2 목표 구조

목표는 각 책임을 sub-agent 또는 subgraph 후보 단위로 분리하는 것이었다.

```text
RootManufacturingGraph
  -> Context Subsystem
  -> Intent/Routing Subsystem
  -> Manufacturing Analysis Subsystem
  -> RAG Evidence Subsystem
  -> Safety Subsystem
  -> Response Formatting Subsystem
  -> Memory/Persistence Subsystem
```

---

## 11. 현재 Sub-Agent / Module 구조

현재는 모든 것이 LangGraph subgraph로 완전히 분리된 것은 아니지만, 코드 책임은 sub-agent 단위로 나뉘었다.

### 11.1 Context Subsystem

```text
ContextResolver
ContextPackBuilder
ContextCompressor
ContextValidator
AnswerMemoryWriter
```

역할:

```text
사용자 질문이 신규 질문인지 follow-up인지 판단
필요한 context만 classifier/answer/rag/safety/memory writer에 전달
답변 후 다음 턴에서 사용할 AnswerMemory 생성
```

### 11.2 Intent / Routing Subsystem

```text
IntentGatewayService
IntentClassifierService
IntentPolicyValidator
GateRegistry
Hard Gates
```

역할:

```text
단순 개념 질문인지
일반 lightweight 질문인지
현재 공정 판단인지
RAG 문서 근거 요청인지
안전/정비/보고서 요청인지 결정
```

### 11.3 Manufacturing Analysis Subsystem

```text
DiagnosticPlanner
DiagnosticFallbackPolicy
DiagnosticPlanToAgentPlanTranslator
PlanRefiner
Prediction Tool
SafetyGateBuilder
RecommendationBuilder
StructuredAnswerPayloadBuilder
```

역할:

```text
현재 process_data가 필요한지 판단
prediction/RAG/safety/report 필요 여부 결정
고장모드/위험도/조치계획과 답변 payload 구성
```

### 11.4 RAG Evidence Subsystem

```text
RagQueryPlanner
RagEvidenceSubAgent
EvidenceFilter
EvidenceGrader
CitationBuilder
```

역할:

```text
질문과 제조 context 기반 query 생성
문서 검색 실행
약한 근거 필터링
근거 품질 평가
citation 생성
```

### 11.5 Safety Subsystem

```text
SafetyPolicy
SafetyContextBuilder
SafetyFormatter
SafetyGateBuilder
```

역할:

```text
안전이 필요하다고 결정된 경우,
필수 포함 문구와 금지 표현,
전문가 확인 필요 여부,
LOTO/방호/정비 전 확인 사항을 구성
```

### 11.6 Response Subsystem

```text
FormatterRegistry
FastConceptFormatter
HeavyAnalysisFormatter
RagFormatter
SafetyFormatter
RecommendedActionFormatter
FallbackFormatter
```

역할:

```text
이미 결정된 selected_path / answer_type을 렌더링
질문 문자열을 다시 해석하지 않음
```

---

## 12. 제거한 Legacy / Wrapper / Facade

Sub-Agent 구조를 만들면서 가장 중요했던 것은 “얇은 wrapper를 남기지 않는 것”이었다.

삭제한 것:

```text
RagEvidencePlanner
rag_evidence_planner import/export
self.rag_evidence_planner
make_query(...)
DiagnosticPlanner.last_diagnostic_plan
self.last_diagnostic_plan
DiagnosticPlanner의 요청별 instance state
self.supervisor._intent(...)
self.supervisor._layers(...)
self.supervisor._llm_refine(...)
req.user_context["current_turn"] heavy 직접 참조
ManufacturingAgentGraph legacy helper wrapper
```

기존 wrapper 예:

```text
_make_rag_query
_contexts_match_user_terms
_collect_action_phrases
_safety_guidance
_warnings
_llm_payload
```

이제는 전용 모듈을 직접 호출한다.

예:

```text
RagQueryPlanner.plan(...)
EvidenceFilter.filter(...)
EvidenceGrader.grade(...)
CitationBuilder.build(...)
SafetyGateBuilder.safety_guidance(...)
RecommendationBuilder.collect_action_phrases(...)
StructuredAnswerPayloadBuilder.build(...)
```

성과:

```text
실제 로직 위치가 명확해짐
테스트가 책임 단위로 가능해짐
향후 LangGraph node/subgraph 전환이 쉬워짐
```

---

## 13. Planning 구조 변경

### 13.1 기존 문제

기존에는 `DiagnosticPlanner.plan()`이 `AgentPlan`만 반환하고, diagnostic snapshot은 instance state에 저장했다.

나쁜 구조:

```python
plan = diagnostic_planner.plan(...)
diagnostic = diagnostic_planner.last_diagnostic_plan
```

문제:

```text
요청별 state가 service instance에 남음
동시 요청에서 오염 가능
테스트가 불안정
```

### 13.2 변경 구조

현재는 `PlanningResult`를 반환한다.

```python
class PlanningResult(BaseModel):
    diagnostic_plan: DiagnosticPlan
    agent_plan: AgentPlan
```

흐름:

```python
planning_result = diagnostic_planner.plan(...)
state["diagnostic_plan"] = planning_result.diagnostic_plan.model_dump()
state["plan"] = planning_result.agent_plan.model_dump()
```

성과:

```text
request-scoped planning result
instance state 제거
root graph state에 명시 저장
```

---

## 14. RAG Sub-Agent 분리 상세

### 14.1 RagQueryPlanner

역할:

```text
검색 query 생성만 담당
검색 실행하지 않음
evidence grading하지 않음
citation 만들지 않음
```

입력 후보:

```text
question
asset_context
failure_modes
risk_assessment
safety_gates
diagnostic_plan.rag_reason
```

출력:

```text
query string 또는 query plan
```

### 14.2 RagEvidenceSubAgent Retrieval Node

역할:

```text
RagService / ChromaRetriever 호출과 retrieval trace 수집
```

현재 Agent RAG path는 RagEvidenceSubAgent 내부 retrieval node에서 Chroma DB를 검색한다.

예상 흐름:

```text
RagEvidenceSubAgent.retrieve
  -> Chroma collection query
  -> top_k chunks 반환
```

### 14.3 EvidenceFilter

역할:

```text
검색 결과 중 사용할 수 없는 문서 제거
```

예:

```text
retrieval_scope=restricted 문서를 기본 질문에서 제거
emergency_only 문서를 일반 정비 질문에서 제거
현재 failure_mode와 무관한 문서 제거
```

### 14.4 EvidenceGrader

역할:

```text
근거 품질 평가
```

평가 기준:

```text
relevance
failure_mode_alignment
safety_alignment
actionability
citation_quality
```

### 14.5 CitationBuilder

역할:

```text
graded evidence를 사용자 답변 citation으로 변환
```

출력 예:

```json
{
  "source": "KOSHA",
  "title": "유해위험설비의 점검·정비·유지관리에 관한 기술지원규정",
  "doc_type": "korean_maintenance_guidance",
  "safety_gate": "maintenance_check",
  "reason": "정비/점검 절차 근거"
}
```

---

## 15. RAG Vector DB와 Sub-Agent의 연결 목표

현재 상태:

```text
Vector DB 생성 완료
Chroma collection: manufacturing_rag
vectors: 727
```

다음 목표:

```text
RagQueryPlanner
  -> ChromaRetriever
  -> EvidenceFilter
  -> EvidenceGrader
  -> CitationBuilder
  -> Answer Payload
```

예상 query:

```text
question:
토크가 높고 공구 마모가 큰데 어떤 점검과 안전 절차를 확인해야 해?

failure_modes:
OSF, TWF

safety_gates:
loto, machine_guarding
```

예상 retrieval filter:

```json
{
  "failure_modes": ["OSF", "TWF"],
  "safety_gate": ["maintenance_check", "machine_guarding", "loto"],
  "retrieval_scope": "default",
  "project_priority": ["high", "medium"]
}
```

예상 답변 근거:

```text
KOSHA 정비/점검 기술지원규정
KOSHA 회전기계 끼임/절단재해 예방 기술지원규정
OSHA Lockout/Tagout 1910.147
OSHA Machine Guarding 1910.212
Haas spindle troubleshooting
```

---

## 16. 실제 성과 요약

### 16.1 RAG/Vector DB 성과

```text
외부 문서 source를 AI4I 예측 데이터와 분리
현재 제조 MVP와 관련 있는 문서만 우선 수집
KOSHA API 실제 필드 대응
첨부 파일 다운로드 정상화
HTML/PDF/HWPX 텍스트 추출
문서 metadata 정리
chunk 727개 생성
OpenAI embedding으로 Chroma vector 727개 생성
corpus report 생성
```

### 16.2 Sub-Agent 구조 성과

```text
ManufacturingAgentGraph helper 비대화 완화
RAG query/retrieval/filter/grading/citation 책임 분리
PlanningResult로 request instance state 제거
SupervisorService private method 의존 제거
legacy wrapper/facade 제거
Formatter/Safety/Context/Memory 책임 분리
```

### 16.3 테스트 성과

```bash
../.venv312/bin/python -m pytest tests/test_kosha_download_utils.py tests/test_rag_document_building.py tests/test_rag_chunking.py -q
# 6 passed

../.venv312/bin/python -m pytest -q
# 62 passed
```

---

## 17. 앞으로 해야 할 일

### 17.1 ChromaRetriever 구현

현재 가장 중요한 다음 작업이다.

해야 할 일:

```text
app/agent/heavy/chroma_retriever.py 또는 app/services/chroma_rag_service.py 추가
Chroma PersistentClient 연결
collection=manufacturing_rag 검색
query embedding 생성
metadata filter 적용
RagService / ChromaRetriever에 연결
```

### 17.2 Metadata filter 정책

현재 chunk metadata는 준비되어 있다.

활용할 필드:

```text
source
doc_type
safety_gate
failure_modes
related_signals
project_priority
retrieval_scope
```

filter 예:

```text
OSF/TWF 질문
  -> failure_modes contains OSF/TWF

정비 전 안전 질문
  -> safety_gate in loto, machine_guarding, maintenance_check

일반 설명 질문
  -> retrieval_scope restricted 제외

비상 질문
  -> retrieval_scope emergency_only 허용
```

### 17.3 RAG 품질 테스트

추가해야 할 테스트:

```text
test_chroma_retriever_returns_loto_for_maintenance_safety_question
test_chroma_retriever_returns_machine_guarding_for_rotating_part_question
test_chroma_retriever_returns_kosha_maintenance_for_tool_wear_question
test_restricted_docs_are_not_default_retrieval_results
test_citation_builder_uses_chroma_metadata
```

### 17.4 Streamlit PDF Upload / Vectorize UI

CLI만으로는 demo가 약하다.

UI에 추가할 것:

```text
RAG 관리 탭
PDF/HWPX/HTML 업로드
업로드 파일 metadata 입력
문서 build/chunk/index 버튼
Chroma collection count 표시
corpus report 표시
```

### 17.5 RAG subgraph LangGraph node화

현재는 모듈 분리 상태다.

다음은 LangGraph node/subgraph로 승격하는 것이다.

목표:

```text
Evidence Retrieval Subgraph
  -> rag_query_planner_node
  -> retriever_node
  -> evidence_filter_node
  -> evidence_grader_node
  -> citation_builder_node
```

나중에는 `Send` 패턴으로 query별 병렬 검색이 가능하다.

### 17.6 Corpus versioning

운영형으로 가려면 다음이 필요하다.

```text
corpus_version
collection_version
embedding_model_version
source_manifest_hash
chunk_config_hash
```

이 정보가 없으면 나중에 “어떤 문서와 embedding으로 답했는지” 추적하기 어렵다.

---

## 18. 포트폴리오 설명 문장

이 작업은 단순히 외부 문서를 Vector DB에 넣은 것이 아니다.

포트폴리오에서는 다음처럼 설명할 수 있다.

```text
AI4I 예측 모델은 공정 수치 기반 위험 신호를 판단하고,
OSHA/Haas/KOSHA 문서 기반 Chroma Vector DB는 그 판단을 정비 절차와 안전 확인 근거로 변환하는 evidence layer로 설계했습니다.

또한 ManufacturingAgentGraph 내부에 섞여 있던 RAG query, retrieval, evidence grading, citation, safety, recommendation 책임을 sub-agent 후보 모듈로 분리해,
향후 LangGraph subgraph와 병렬 retrieval 구조로 확장 가능한 기반을 만들었습니다.
```

더 짧게는 이렇게 말할 수 있다.

```text
예측 모델과 RAG 근거 계층을 분리하고, 제조 업무 흐름을 Diagnostic, RAG Evidence, Safety, Recommendation, Formatter 모듈로 나누어 LangGraph 기반 제조 Agent의 sub-agent 아키텍처를 설계했습니다.
```

---

## 19. 결론

이번 작업의 핵심은 두 가지다.

첫째, Vector DB를 만들 때 전체 데이터를 무작정 넣지 않고, 현재 AI4I 제조 예측정비 MVP와 직접 관련 있는 문서만 우선 수집했다.

둘째, RAG Vector DB가 들어갈 자리를 Agent 구조 안에 만들기 위해 `ManufacturingAgentGraph` 내부 책임을 sub-agent 후보 모듈로 분리했다.

현재 상태:

```text
RAG corpus 준비 완료
Chroma vector DB 생성 완료
Sub-Agent 후보 모듈 분리 완료
```

다음 핵심 단계:

```text
ChromaRetriever를 Agent RAG runtime에 연결
RAG Evidence Subgraph를 LangGraph node로 승격
Streamlit에서 문서 업로드/벡터화 UI 제공
```
