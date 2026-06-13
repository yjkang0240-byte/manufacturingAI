# Historical Record

This review may mention removed endpoints and legacy classes. It is not the
current runtime contract.

# 코드 부정 평가 및 보완 필요 사항

작성일: 2026-06-12

## 총평

현재 코드는 "제조 특화 AI Agent"라는 설명에 비해 실제 구현은 데모/MVP 수준에 가깝다. API, 예측 모델, RAG, 안전 게이트, 이력 저장, 평가 기능이 모두 존재하지만 대부분이 얕은 규칙과 파일 기반 처리에 의존한다. 제조 현장 의사결정 보조 시스템으로 보기에는 검증, 추적성, 장애 대응, 보안, 모델 신뢰도 관리가 부족하다.

가장 큰 문제는 코드가 기능을 많이 가진 것처럼 보이지만, 각 기능의 품질 보증 장치가 약하다는 점이다. 특히 안전과 정비를 다루는 시스템인데도 실패 시 동작, 입력 범위 검증, 근거 문서 품질, 모델 성능 검증, 감사 로그 보호가 충분하지 않다.

## 핵심 문제 요약

| 우선순위 | 영역 | 부정 평가 | 보완 방향 |
|---|---|---|---|
| P0 | 안전/운영 | 제조 안전 보조 시스템치고 방어 로직이 약하다. | 안전 게이트를 정책 엔진화하고 테스트 케이스로 고정해야 한다. |
| P0 | 예측 모델 | 모델 학습/검증/캘리브레이션이 부실하다. | 학습 파이프라인, 검증 지표, 모델 카드, 임계값 근거를 추가해야 한다. |
| P0 | API 보안 | CORS 전체 허용, 인증/권한 없음, 도메인 카탈로그 전체 노출이 있다. | 인증, 권한, CORS 제한, 운영/내부 API 분리가 필요하다. |
| P1 | RAG | 키워드 검색 수준이라 근거 검색 품질을 신뢰하기 어렵다. | 임베딩/하이브리드 검색, 출처 품질, citation 검증을 추가해야 한다. |
| P1 | 오류 처리 | 대부분 500으로 뭉개져 원인 분리와 사용자 대응이 어렵다. | 도메인별 예외, 4xx/5xx 분리, 구조화 로그가 필요하다. |
| P1 | 저장소 | JSONL 파일 저장은 동시성/무결성/개인정보 보호에 취약하다. | DB, 잠금, retention, 마스킹, 접근 통제를 적용해야 한다. |
| P1 | 테스트 | 단위/통합/회귀 테스트가 사실상 없다. | pytest 기반 테스트 스위트와 golden case를 CI에 붙여야 한다. |
| P2 | 구조 | 전역 싱글턴과 강한 결합이 많아 확장성과 테스트성이 낮다. | FastAPI dependency injection과 인터페이스 분리가 필요하다. |

## 상세 지적

### 1. API 보안 기본값이 위험하다

- `ai_server/app/main.py:31`에서 `allow_origins=['*']`, `allow_credentials=True`를 동시에 사용한다. 개발 편의 기본값으로는 이해되지만, 운영 API로는 부적절하다.
- `ai_server/app/main.py:58-95`는 도메인 카탈로그, 안전 게이트, 액션 카탈로그를 인증 없이 그대로 노출한다.
- `/history`와 `/history/{run_id}`도 인증 없이 실행 이력과 요청/응답 내용을 조회할 수 있다.
- `/agent/send`, `/agent/run`, `/predict`에 rate limit, API key, 사용자/세션 권한 검증이 없다.

보완 필요:

- 운영 환경에서는 CORS origin allowlist를 환경변수로 제한한다.
- 내부 관리성 API와 외부 사용자 API를 분리한다.
- 최소한 API key 또는 OAuth/JWT 기반 인증을 추가한다.
- `/history`는 사용자/세션 단위 권한 확인, 개인정보 마스킹, retention 정책을 적용한다.

### 2. 예외 처리가 너무 넓고 부정확하다

- `ai_server/app/main.py:115-120`, `ai_server/app/main.py:126-154`에서 모든 예외를 `HTTPException(500, detail=str(exc))`로 반환한다.
- 입력 오류, 모델 파일 누락, RAG 인덱스 손상, LLM 장애, 내부 버그가 모두 같은 500으로 보인다.
- `detail=str(exc)`는 내부 경로, 모델 파일명, 외부 provider 오류 등을 그대로 노출할 수 있다.

보완 필요:

- `ModelNotReady`, `InvalidProcessData`, `RagIndexUnavailable`, `LLMProviderError` 같은 도메인 예외를 분리한다.
- 사용자 입력 문제는 400/422, 의존 리소스 문제는 503, 내부 버그는 500으로 분리한다.
- 사용자 응답에는 안전한 메시지만 반환하고, 상세 원인은 구조화 로그에 남긴다.

### 3. 예측 모델은 신뢰성 근거가 부족하다

- `ai_server/app/services/prediction_service.py:78-97`에서 전체 데이터를 바로 학습하고 저장한다. train/test split, cross validation, class imbalance 평가, calibration이 없다.
- `ai_server/app/services/prediction_service.py:145-169`의 failure threshold `0.5`, mode threshold `0.35`, risk threshold `0.2/0.4/0.7`은 근거가 코드에 박혀 있다.
- `MODEL_METRICS`에는 `trained_rows`, `features`, `modes`만 저장된다. 정확도, recall, precision, PR-AUC, confusion matrix가 없다.
- AI4I 공개 데이터는 데모 데이터 성격이 강한데, 응답에서는 제조 현장 판단처럼 보일 수 있다.

보완 필요:

- 학습/검증/테스트 분리와 고정 seed 기반 재현성을 확보한다.
- failure mode별 recall, false negative rate, calibration curve를 저장한다.
- 임계값은 비즈니스 위험 기준에 따라 설정하고 문서화한다.
- 모델 카드에 데이터 한계, 적용 불가 조건, 성능 지표, drift 감지 기준을 명시한다.

### 4. 입력 검증이 너무 약하다

- `ProcessData`는 필수 필드 타입만 강제하고, 물리적으로 말이 안 되는 값이나 단위 범위를 제한하지 않는다.
- `type`은 설명상 `L/M/H`인데 실제 스키마에서는 임의 문자열을 받을 수 있다.
- `top_k`, `message`, `inspection_notes`, `session_id` 길이 제한이 약하다.
- 제조 안전/정비 시스템에서 비정상 입력이 들어왔을 때 "예측 실패"가 아니라 "그럴듯한 잘못된 답변"을 만들 수 있다.

보완 필요:

- Pydantic `Literal['L', 'M', 'H']`, `Field(ge=..., le=...)`, 길이 제한을 적용한다.
- 단위 변환과 입력 provenance를 명시한다.
- 입력값이 학습 데이터 분포 밖이면 예측보다 "범위 밖" 경고를 우선 반환한다.

### 5. RAG 품질이 낮고 근거 신뢰성이 부족하다

- `ai_server/app/services/rag_service.py:40-46`은 단순 토큰 카운터와 IDF를 메모리에 만든다.
- `ai_server/app/services/rag_service.py:77-78`은 검색 결과가 없으면 점수 0인 문서를 그대로 반환한다. 이는 잘못된 citation을 만들어낼 수 있다.
- 문서의 최신성, 출처 권위, 언어, 장비 타입, 섹션 중요도, 안전 표준 우선순위가 검색 랭킹에 제대로 반영되지 않는다.
- citation은 "검색된 문서"를 의미할 뿐, 답변 문장과 실제 근거 문장 사이의 정합성을 검증하지 않는다.

보완 필요:

- 최소 BM25, 가능하면 임베딩 + BM25 하이브리드 검색을 도입한다.
- 결과 없음과 낮은 신뢰도를 명확히 반환하고, 점수 0 문서는 citation으로 쓰지 않는다.
- 문서 metadata schema를 강화하고, 안전 표준/제조사 매뉴얼/내부 절차의 우선순위를 정책화한다.
- 답변 문장별 citation 매핑과 citation coverage 평가를 추가한다.

### 6. 안전 게이트가 규칙 흉내에 가깝다

- `DomainKnowledgeService`는 키워드와 catalog 조합으로 안전 게이트를 고른다.
- 안전 요구사항은 코드, YAML, LLM prompt, 평가 루브릭에 분산되어 있다.
- "정비", "점검", "전기", "비상" 같은 키워드 기반 판단은 누락과 오탐이 모두 쉽다.
- LLM 답변이 안전 게이트를 실제로 지켰는지 강제하는 하드 가드는 약하다. 현재는 prompt와 사후 warning에 의존한다.

보완 필요:

- 안전 게이트를 별도 정책 엔진으로 분리하고, 입력 조건과 필수 출력 조건을 명시적으로 검증한다.
- 안전 관련 답변은 최종 응답 전에 rule-based validator를 통과해야만 반환한다.
- LOTO, 전기 격리, 회전부 방호, 고온 표면, 비상 대응에 대한 positive/negative test case를 고정한다.
- 안전 문구는 "권고"와 "금지"를 구분해 구조화된 필드로 제공한다.

### 7. 이력 저장 방식이 운영에 부적합하다

- `ai_server/app/storage/json_store.py:10-12`는 JSONL 파일에 append만 수행한다. 동시 요청 시 파일 무결성 보장이 약하다.
- `ai_server/app/storage/json_store.py:13-19`는 조회할 때 파일 전체를 읽고, `get`은 최대 10000개를 역순 탐색한다.
- 요청/응답 전체를 저장하므로 공정 데이터, 점검 메모, 사용자 질문 등 민감 정보가 그대로 남는다.
- retention, 삭제, 암호화, 접근 제어가 없다.

보완 필요:

- SQLite/PostgreSQL 같은 DB 저장소로 교체한다.
- run_id, session_id, created_at, user_id, risk_level, route 등을 인덱싱한다.
- 민감 필드는 마스킹하거나 별도 암호화한다.
- 보존 기간과 삭제 정책을 구현한다.

### 8. 전역 싱글턴 구조가 테스트와 운영 확장에 불리하다

- `ai_server/app/main.py:33-38`에서 서비스가 모듈 import 시점에 생성된다.
- 모델 로드, YAML 로드, RAG 로드가 앱 초기화와 강하게 묶여 있어 장애 격리와 테스트 fixture 교체가 어렵다.
- `ManufacturingAgentGraph` 내부에서도 `DomainKnowledgeService`, `ReportService`, `JsonLineStore`를 직접 생성해 의존성 주입이 불완전하다.

보완 필요:

- FastAPI lifespan과 dependency injection으로 서비스 초기화 시점을 명확히 한다.
- 프로토콜/인터페이스를 정의해 prediction, rag, llm, storage를 테스트에서 쉽게 교체한다.
- readiness check에서 모델, RAG, domain catalog 상태를 분리해 반환한다.

### 9. 평가 서비스가 실제 품질 보증으로 부족하다

- `evaluation_service.py`는 문자열 포함 여부 중심의 점수 계산이다.
- 금지 표현 탐지도 단순 substring이라 우회/오탐이 쉽다.
- 근거 문서와 답변 문장 사이의 factual consistency를 평가하지 않는다.
- 안전 게이트 준수도 일부 단어가 답변에 있으면 통과할 수 있다.

보완 필요:

- golden dataset 기반 회귀 평가를 pytest/CI에 연결한다.
- 답변 섹션별 필수 구조, citation coverage, unsafe instruction 탐지를 분리한다.
- 안전 관련 평가는 deterministic validator를 우선하고, LLM judge는 보조로만 사용한다.

### 10. 테스트 체계가 거의 없다

- 기존 단일 실행 검증 스크립트는 제거했으며, 검증은 pytest 단위/통합 테스트로 고정해야 한다.
- 핵심 서비스인 prediction, rag, domain, supervisor, evaluation에 대한 단위 테스트가 없다.
- API endpoint 테스트도 없다.
- 안전 게이트와 회귀 품질은 테스트로 고정되어 있지 않다.

보완 필요:

- `tests/`를 만들고 pytest 기반으로 다음을 우선 추가한다.
- `PredictionService`: 정상 입력, 범위 밖 입력, 모델 누락, threshold 경계값.
- `RagService`: 결과 없음, filter 동작, 낮은 점수 문서 미반환.
- `DomainKnowledgeService`: LOTO/전기/회전부/비상 키워드별 안전 게이트.
- API: `/predict`, `/agent/send`, `/history` 권한/오류 응답.
- Golden case: 제조 안전 답변에서 필수 금지/주의 문구 누락 방지.

## 우선 보완 로드맵

### 1단계: 운영 위험 차단

- CORS 제한, 인증 추가, `/history` 보호.
- 모든 endpoint의 예외 응답을 분리.
- 입력 범위 검증 추가.
- RAG 결과 없음일 때 점수 0 문서 반환 금지.
- 안전 게이트 validator를 최종 응답 직전에 추가.

### 2단계: 신뢰성 확보

- pytest 테스트 스위트 추가.
- 예측 모델 train/test split과 성능 지표 저장.
- golden dataset 기반 회귀 테스트 추가.
- JSONL history를 DB로 이전.

### 3단계: 제품화 수준 개선

- 하이브리드 RAG 검색과 citation 검증 도입.
- 서비스 의존성 주입 구조 정리.
- 모델 카드, 데이터 카드, 안전 정책 문서 작성.
- 관측성: 구조화 로그, request id, latency, 실패율, LLM error rate, RAG hit rate 추가.

## 결론

현재 코드는 데모로는 설득력이 있지만, 제조 도메인 AI Agent라는 이름으로 운영하기에는 아직 부족하다. 특히 안전과 예측을 다루는 시스템이므로 "답변이 그럴듯한가"보다 "틀렸을 때 피해를 줄이는가"가 더 중요하다. 지금 가장 먼저 해야 할 일은 기능 추가가 아니라 보안, 입력 검증, 안전 게이트 강제, 테스트, 모델 검증을 통해 실패 가능성을 낮추는 것이다.
