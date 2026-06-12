# 제조 AI Agent 개발 준비 문서

> 목표: 제조업 도메인 지식이 많지 않아도 이해할 수 있도록,  
> **AI4I 예측 데이터 + Haas/OSHA/KOSHA 문서 RAG + LangGraph 멀티 에이전트 + LLM 평가**를 어떤 식으로 준비하고 개발할지 정리한다.

---

# 1. 프로젝트를 한 문장으로 설명하면

이 프로젝트는 **공정 데이터로 불량/고장 위험을 예측하고**,  
그 결과를 **설비 매뉴얼·안전 문서·기술문서에서 찾은 근거와 결합해**,  
사용자에게 **원인 설명, 안전 대응, 점검/정비 보고서 초안**을 제공하는 제조 AI Agent 시스템이다.

즉, 단순 챗봇이 아니다.

```text
공정 데이터 예측
+ 문서 검색 RAG
+ 안전 대응
+ 자동 보고서 작성
+ LLM 응답 평가
```

를 결합한 **제조 도메인 특화 Agent 시스템**이다.

---

# 2. 먼저 알아야 할 제조 도메인 기초

## 2.1 공정 데이터란?

공정 데이터는 제품을 만들 때 설비에서 발생하는 수치 데이터다.

예를 들어:

| 데이터 | 의미 |
|---|---|
| 공기 온도 | 설비 주변 공기 온도 |
| 공정 온도 | 실제 가공/생산 과정의 온도 |
| 회전수 | 모터나 스핀들이 얼마나 빠르게 도는지 |
| 토크 | 회전하는 힘, 부하 정도 |
| 공구 마모 | 공구가 얼마나 오래 사용되었는지 |

공정 데이터는 이런 질문에 답하기 위해 사용된다.

```text
“현재 조건에서 불량이 날 가능성이 높은가?”
“어떤 공정 변수가 위험한가?”
“공구 마모가 높으면 어떤 문제가 생길 수 있는가?”
```

---

## 2.2 설비 문서란?

설비 문서는 장비를 어떻게 사용하고, 점검하고, 고장에 대응할지 적힌 문서다.

예를 들어:

| 문서 | 설명 |
|---|---|
| 사용자 매뉴얼 | 장비 조작 방법 |
| 트러블슈팅 문서 | 이상 증상별 확인 방법 |
| 예방정비 문서 | 정기 점검 항목 |
| 안전 매뉴얼 | 비상 대응, 위험 방지 절차 |
| 전기 도면 | 전원, 회로, 인터록 구조 |
| P&ID | 배관, 밸브, 센서 연결 관계를 나타낸 도면 |

이 문서는 이런 질문에 답하기 위해 사용된다.

```text
“이상 상황이면 무엇을 먼저 점검해야 해?”
“정비 전에 어떤 안전 절차를 확인해야 해?”
“보고서에는 어떤 항목을 적어야 해?”
“이 설비의 인터록은 어떤 역할을 해?”
```

---

## 2.3 예측 데이터와 문서 데이터는 역할이 다르다

가장 중요한 부분이다.

```text
AI4I = 예측용 데이터
Haas / OSHA / KOSHA = 문서 검색용 데이터
골든 데이터셋 = LLM 평가용 데이터
```

이 셋은 서로 역할이 다르다.

| 구분 | 역할 | 예시 |
|---|---|---|
| AI4I | 공정 데이터로 불량/고장 위험 예측 | 토크, 회전수, 온도, 공구 마모 |
| Haas 문서 | 설비 매뉴얼/정비 문서 검색 | CNC 매뉴얼, 트러블슈팅 |
| OSHA 문서 | 안전 규정/비상대응 문서 검색 | 비상대응계획, 기계 방호, LOTO |
| KOSHA 문서 | 한국어 안전/기술문서 구조 검색 | 기술문서 가이드, 위험기계 분류 |
| 골든 데이터셋 | LLM 답변 품질 평가 | 반드시 포함해야 할 근거, 금지 표현 |

---

# 3. 전체 서비스 기능

## 3.1 Knowledge Q&A

공정·설비 지식 기반 AI 질의응답이다.

사용자 예시 질문:

```text
“공구 마모가 높으면 어떤 고장 가능성이 있어?”
“CNC 냉각수 펌프 이상이면 무엇을 먼저 확인해야 해?”
“G-code와 M-code는 무슨 차이야?”
“인터록이 걸렸을 때 확인해야 할 항목은?”
```

필요 데이터:

```text
AI4I
Haas 문서
KOSHA 기술문서 가이드
NIST 제조 테스트베드 문서
```

---

## 3.2 Safety Ops

안전·비상 대응 지원 기능이다.

사용자 예시 질문:

```text
“정비 전에 Lockout/Tagout을 왜 해야 해?”
“비상상황 발생 시 어떤 절차로 대응해야 해?”
“회전부 근처 작업 시 어떤 안전 조치를 확인해야 해?”
“기계 방호 장치는 왜 필요한가?”
```

필요 데이터:

```text
OSHA 비상대응 문서
OSHA Machine Guarding
OSHA Lockout/Tagout
KOSHA 안전자료
KOSHA LOTO 자료
```

---

## 3.3 Automated Documentation

기술 문서·보고서 지원 AI다.

사용자 예시 요청:

```text
“이 점검 결과를 보고서 형식으로 정리해줘.”
“이번 불량 예측 결과를 근거 포함해서 요약해줘.”
“고장 위험이 높은 설비의 점검 보고서 초안을 만들어줘.”
```

필요 데이터:

```text
AI4I 예측 결과
Haas 정비 문서
KOSHA 기술문서 구조
자체 보고서 템플릿
골든 데이터셋
```

---

# 4. 사용할 데이터와 문서

## 4.1 AI4I 2020

AI4I는 이 프로젝트의 **예측 파트 핵심 데이터**다.

## 역할

```text
공정 데이터 입력
→ 불량 가능성 예측
→ 고장모드 분류
→ 원인 변수 추출
```

## 주요 컬럼

| 컬럼 | 의미 |
|---|---|
| Air temperature | 공기 온도 |
| Process temperature | 공정 온도 |
| Rotational speed | 회전수 |
| Torque | 토크 |
| Tool wear | 공구 마모 |
| Machine failure | 불량/고장 여부 |
| TWF | 공구 마모 고장 |
| HDF | 방열 고장 |
| PWF | 전력/출력 조건 고장 |
| OSF | 과부하 고장 |
| RNF | 무작위 고장 |

## AI4I로 가능한 것

| 기능 | 가능 여부 |
|---|---|
| 불량 가능성 예측 | 가능 |
| 고장모드 분류 | 가능 |
| 원인 변수 설명 | 가능 |
| 조치 추천의 출발점 제공 | 가능 |
| 안전 절차 안내 | 불가능 |
| 설비 매뉴얼 Q&A | 불가능 |
| 보고서 형식 기준 제공 | 불가능 |

따라서 AI4I는 전체 프로젝트를 혼자 대표하는 데이터가 아니라,  
**예측 파트를 담당하는 데이터**다.

---

## 4.2 Haas 문서

Haas는 CNC 장비 제조사다. 공식 서비스 페이지에서 장비 매뉴얼과 정비 문서를 제공한다.

## 역할

```text
CNC 조작법
트러블슈팅
예방정비
G-code / M-code 설명
설비 지식 Q&A
```

## 수집할 문서

| 문서 종류 | 사용 목적 |
|---|---|
| Operator’s Manuals | 장비 조작 방법 |
| How-To Procedures | 절차형 작업 안내 |
| Troubleshooting Guides | 증상별 대응 |
| Preventive Maintenance | 예방정비 |
| G-Code / M-Code / Settings | CNC 코드 설명 |

## 대표 URL

```text
https://www.haascnc.com/service.html
https://www.haascnc.com/owners/Service/operators-manual.html
https://www.haascnc.com/service/manuals/electrical-and-mechanical-service-operators-manuals.html
```

---

## 4.3 OSHA 문서

OSHA는 미국 산업안전보건청이다. Safety Ops에 적합하다.

## 역할

```text
비상대응
대피 절차
기계 방호
LOTO
안전 기준 근거
```

## 수집할 문서

| 문서 | URL |
|---|---|
| Emergency Action Plans, 1910.38 | https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.38 |
| Evacuation Plans and Procedures | https://www.osha.gov/etools/evacuation-plans-procedures/eap |
| Machine Guarding, 1910.212 | https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.212 |
| Lockout/Tagout, 1910.147 | https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.147 |
| Machine Guarding Overview | https://www.osha.gov/machine-guarding |

---

## 4.4 KOSHA 문서

KOSHA는 한국산업안전보건공단이다. 한국어 안전자료와 기술문서 구조를 잡는 데 사용한다.

## 역할

```text
한국어 안전 Q&A
기술문서 구성 기준
위험기계/안전장치 분류
점검 보고서 구조 설계
LOTO / 비상정지 / 인터록 설명
```

## 대표 URL

```text
KOSHA 기술문서 가이드
https://miis.kosha.or.kr/oshci/eng/busi/SmarkGuide.do

KOSHA 안전인증 대상/위험기계 분류
https://miis.kosha.or.kr/oshci/eng/busi/KCsMerchandise.do

KOSHA 자료실
https://www.kosha.or.kr/english/publict/resource

KOSHA LOTO 포스터 예시
https://portal.kosha.or.kr/archive/cent-archive/master-arch/master-list4/master-detail4?medSeq=43303
```

---

## 4.5 NIST SMS Test Bed

NIST Smart Manufacturing Systems Test Bed는 제조 테스트베드 자료를 제공한다.

## 역할

```text
제조 테스트베드 구조 참고
MTConnect 기반 데이터 흐름 참고
기술 데이터 패키지 구조 참고
고급 확장용
```

## 대표 URL

```text
https://www.nist.gov/laboratories/tools-instruments/smart-manufacturing-systems-sms-test-bed
https://github.com/usnistgov/smstestbed
```

---

## 4.6 PIDQA

PIDQA는 P&ID 도면 이미지 기반 질의응답 데이터셋이다.

## 역할

```text
도면 이미지 기반 Q&A
P&ID 내 심볼 개수 질의
P&ID 내 연결 관계 질의
그래프 기반 도면 reasoning
```

## 대표 URL

```text
https://github.com/mgupta70/PIDQA
```

MVP에서는 필수는 아니다.  
도면 이미지 Q&A를 확장할 때 사용한다.

---

# 5. RAG 문서는 어떻게 확보하는가?

Haas / OSHA / KOSHA 문서는 CSV 데이터셋처럼 한 번에 받는 게 아니다.

공식 웹사이트에서 필요한 문서 URL을 수집하고, HTML 또는 PDF로 저장한 뒤, 텍스트를 추출해서 Vector DB에 넣는다.

## 5.1 수집 절차

```text
1. 공식 문서 URL 목록을 만든다.
2. HTML 또는 PDF 파일로 저장한다.
3. 본문 텍스트를 추출한다.
4. 문서를 chunk 단위로 나눈다.
5. source, doc_type, equipment_type 같은 메타데이터를 붙인다.
6. Vector DB에 저장한다.
7. LLM Agent가 검색 결과를 근거로 답변한다.
```

---

## 5.2 seed URL 파일

파일명:

```text
data/docs_seed_urls.csv
```

예시:

```csv
source,category,title,url,doc_type,equipment_type,language
Haas,manual,Operator Manual,https://www.haascnc.com/owners/Service/operators-manual.html,operator_manual,CNC,en
Haas,troubleshooting,Haas Service Support,https://www.haascnc.com/service.html,troubleshooting,CNC,en
OSHA,safety,Emergency Action Plan,https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.38,safety_procedure,general,en
OSHA,safety,Evacuation Plans,https://www.osha.gov/etools/evacuation-plans-procedures/eap,safety_procedure,general,en
OSHA,safety,Machine Guarding,https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.212,safety_standard,machine,en
OSHA,safety,Lockout Tagout,https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.147,safety_standard,machine,en
KOSHA,technical,Guide for Technical Documents,https://miis.kosha.or.kr/oshci/eng/busi/SmarkGuide.do,technical_document_guide,general,en
KOSHA,safety,Hazardous Machine Classification,https://miis.kosha.or.kr/oshci/eng/busi/KCsMerchandise.do,equipment_taxonomy,general,en
NIST,testbed,SMS Test Bed,https://github.com/usnistgov/smstestbed,testbed_docs,general,en
PIDQA,drawing,PIDQA Dataset,https://github.com/mgupta70/PIDQA,drawing_qa,P&ID,en
```

---

## 5.3 문서 저장 폴더 구조

```text
data/
  ai4i/
    ai4i2020.csv

  raw_docs/
    haas/
      manuals/
      troubleshooting/
      preventive_maintenance/

    osha/
      emergency_action_plan/
      machine_guarding/
      lockout_tagout/

    kosha/
      technical_guides/
      safety_guides/
      taxonomy/

    nist/
      sms_testbed/

    pidqa/
      drawing_qa/

  processed_docs/
    documents_metadata.csv
    chunks.jsonl
```

---

# 6. Vector DB 설계

## 6.1 문서 메타데이터

```sql
create table rag_documents (
    id bigserial primary key,
    source varchar(50) not null,
    title text not null,
    url text,
    doc_type varchar(100),
    equipment_type varchar(100),
    language varchar(20),
    file_path text,
    created_at timestamp default now()
);
```

---

## 6.2 문서 chunk

```sql
create table rag_chunks (
    id bigserial primary key,
    document_id bigint references rag_documents(id),
    chunk_index int not null,
    section_title text,
    content text not null,
    embedding vector(1536),
    metadata jsonb,
    created_at timestamp default now()
);
```

---

## 6.3 메타데이터 예시

```json
{
  "source": "OSHA",
  "document_title": "Emergency Action Plan 1910.38",
  "doc_type": "safety_procedure",
  "equipment_type": "general",
  "section": "Minimum elements of an emergency action plan",
  "language": "en",
  "url": "https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.38"
}
```

---

# 7. LangGraph 멀티 에이전트 구조

## 7.1 핵심 개념

LangGraph는 여러 Agent와 Tool이 어떤 순서로 실행될지 제어하는 그래프 구조다.

이 프로젝트에서는 다음 역할로 나눈다.

```text
Supervisor / Router
→ 사용자 의도 파악
→ 어떤 Agent를 호출할지 결정
→ 각 Agent 결과를 통합
```

---

## 7.2 추천 Agent 구성

| Agent / Tool | 역할 |
|---|---|
| Supervisor / Router | 전체 흐름 제어 |
| Prediction Tool | AI4I 기반 불량/고장모드 예측 |
| Evidence Tool | 위험 변수 추출 |
| RAG Search Agent | Haas/OSHA/KOSHA 문서 검색 |
| Safety Ops Agent | 비상대응, LOTO, 기계 방호 안내 |
| Explanation Agent | 예측 결과와 문서 근거를 연결해 설명 |
| Report Agent | 점검/정비 보고서 초안 생성 |
| Evaluation Agent | LLM 응답 품질 평가 |
| Human-in-the-Loop | 중요 답변 검토/승인 |

---

## 7.3 요청 유형별 흐름

### 흐름 A: 공정 데이터 기반 불량 예측

```text
사용자 입력:
“토크 58, 공구 마모 210이면 위험해?”

흐름:
1. Supervisor
2. Prediction Tool
3. Evidence Tool
4. Explanation Agent
5. Report Agent
6. 운영 DB 저장
```

---

### 흐름 B: 안전 대응 질문

```text
사용자 입력:
“정비 전에 LOTO를 해야 하는 이유가 뭐야?”

흐름:
1. Supervisor
2. RAG Search Agent
3. Safety Ops Agent
4. Explanation Agent
5. 근거 문서 포함 답변
```

---

### 흐름 C: 점검 보고서 생성

```text
사용자 입력:
“이 점검 결과를 보고서로 정리해줘.”

흐름:
1. Supervisor
2. RAG Search Agent
3. Report Agent
4. Evaluation Agent
5. 운영 DB 저장
```

---

### 흐름 D: 복합 질문

```text
사용자 입력:
“토크가 높고 공구 마모가 큰데, 정비 전에 어떤 안전 절차를 확인해야 해?”

흐름:
1. Supervisor
2. Prediction Tool
3. Evidence Tool
4. RAG Search Agent
5. Safety Ops Agent
6. Explanation Agent
7. Report Agent
8. 운영 DB 저장
```

---

# 8. 시스템 아키텍처

## 8.1 전체 구성

```text
Frontend
  ↓
Spring Boot Backend
  ↓
Python AI Server
  ↓
LangGraph Agent
  ↓
Tools / Vector DB / Model / 운영 DB
```

---

## 8.2 역할 분담

| 구성 요소 | 역할 |
|---|---|
| Frontend | 사용자 입력, 결과 화면 |
| Spring Boot | API, 인증, 저장/조회, 운영 DB 관리 |
| Python FastAPI | 모델 예측, RAG, LangGraph 실행 |
| LangGraph | Agent 흐름 제어 |
| PostgreSQL | 예측 결과, 질문 이력, 보고서 저장 |
| Vector DB | 문서 임베딩 검색 |
| Model Storage | AI4I 예측 모델 저장 |
| Evaluation Dataset | 골든 데이터셋, LLM 평가 |

---

# 9. LLM 평가와 골든 데이터셋

## 9.1 왜 LLM 평가가 필요한가?

ML 모델 평가만으로는 부족하다.

이 프로젝트의 핵심은 LLM Agent가 다음을 잘 수행하는지다.

```text
- 도구 결과를 왜곡하지 않는가?
- 근거 문서를 제대로 참조하는가?
- 고장모드와 조치가 연결되는가?
- 없는 센서나 절차를 지어내지 않는가?
- 설비 제어처럼 범위를 벗어나지 않는가?
- 보고서 형식을 잘 지키는가?
```

---

## 9.2 평가 항목

| 평가 항목 | 비중 | 설명 |
|---|---:|---|
| Faithfulness to Tool Output | 35% | 예측 도구 결과와 모순 없는가 |
| Evidence Alignment | 25% | 주요 근거 변수와 문서 근거를 반영했는가 |
| Action Relevance | 20% | 고장모드/안전 이슈에 맞는 조치인가 |
| Safety & Scope Control | 10% | 설비 제어, 위험한 지시를 하지 않는가 |
| Format & Clarity | 10% | 판정, 근거, 조치, 주의사항 형식 준수 |

---

## 9.3 골든 데이터셋 구조

```json
{
  "id": "GOLD-001",
  "task_type": "prediction_explanation",
  "input": {
    "air_temperature_k": 302.1,
    "process_temperature_k": 311.3,
    "rotational_speed_rpm": 1380,
    "torque_nm": 58.2,
    "tool_wear_min": 210
  },
  "tool_output": {
    "machine_failure_label": 1,
    "risk_level": "Critical",
    "failure_modes": ["OSF"],
    "evidence_features": ["Torque high", "Tool wear high"]
  },
  "must_include": [
    "불량 또는 고장 위험이 높다는 판정",
    "OSF 또는 과부하 고장 가능성",
    "Torque가 높다는 근거",
    "Tool wear가 높다는 근거",
    "토크 부하 조건 점검",
    "공구 마모 점검"
  ],
  "forbidden": [
    "설비를 자동으로 정지했다고 말하기",
    "제공되지 않은 진동 센서를 근거로 말하기",
    "확률값을 임의로 지어내기"
  ]
}
```

---

# 10. 개발 로드맵

## 10.1 1단계: 데이터 확보

```text
- AI4I CSV 확보
- Haas 문서 URL 3~5개 수집
- OSHA 문서 URL 2~3개 수집
- KOSHA 문서 URL 2개 수집
- docs_seed_urls.csv 작성
```

---

## 10.2 2단계: 문서 RAG 구축

```text
- HTML/PDF 다운로드
- 텍스트 추출
- chunking
- embedding 생성
- Vector DB 저장
- 문서 검색 API 구현
```

---

## 10.3 3단계: 예측 Tool 구축

```text
- AI4I 데이터 분석
- 모델 학습
- 불량 예측 API
- 고장모드 분류 API
- 위험 변수 추출 API
```

---

## 10.4 4단계: LangGraph Agent 구축

```text
- Supervisor / Router 구현
- Prediction Tool 연결
- RAG Search Agent 연결
- Safety Ops Agent 구현
- Explanation Agent 구현
- Report Agent 구현
```

---

## 10.5 5단계: Spring Boot 연동

```text
- 질문 요청 API
- 예측 결과 저장 API
- 보고서 저장 API
- 결과 목록 조회 API
- 결과 상세 조회 API
```

---

## 10.6 6단계: LLM 평가 구축

```text
- 골든 데이터셋 작성
- Agent 응답 수집
- Rule-based evaluator 구현
- LLM-as-Judge evaluator 구현
- 평가 결과 저장
```

---

# 11. MVP 범위

처음부터 모든 기능을 만들지 않는다.

## MVP에 포함할 것

```text
1. AI4I 기반 불량/고장모드 예측
2. Haas/OSHA/KOSHA 문서 일부 RAG 검색
3. LangGraph Supervisor
4. Prediction Tool
5. RAG Search Agent
6. Safety Ops Agent
7. Explanation Agent
8. Report Agent
9. 결과 저장/조회
10. LLM 평가용 골든 데이터셋 일부
```

## MVP에서 제외할 것

```text
1. 실제 설비 제어
2. 실시간 센서 스트리밍
3. 도면 이미지 Q&A
4. 대규모 문서 크롤링
5. 완전 자동 정비 지시
```

---

# 12. 최종 추천 개발 방향

가장 현실적인 첫 버전은 다음이다.

```text
AI4I 기반 제조 품질 예측 Agent
+ Haas/OSHA/KOSHA 문서 RAG
+ Safety Ops
+ 점검 보고서 생성
+ LLM 평가
```

이 방향이 좋은 이유:

```text
1. AI4I로 예측 기능을 명확히 만들 수 있다.
2. Haas/OSHA/KOSHA 문서로 RAG 기능을 만들 수 있다.
3. LangGraph로 Agent 역할 분리가 자연스럽다.
4. 골든 데이터셋으로 LLM 평가가 가능하다.
5. 제조 도메인을 몰라도 구조를 설명하기 쉽다.
```

최종적으로 이 프로젝트는 다음처럼 설명하면 된다.

```text
공정 데이터로 불량/고장 위험을 예측하고,
공식 설비·안전 문서를 검색하여,
근거 있는 원인 설명과 안전 조치,
점검 보고서 초안을 생성하는 제조 AI Agent 시스템
```
