# 제조 AI RAG 문서 데이터 확보 및 구축 계획

> 목적: Haas / OSHA / KOSHA 문서를 어디서 얻고, 어떻게 저장하고, 어떻게 RAG 검색용 데이터로 만드는지 명확하게 정리한다.
>
> 핵심 결론: 이 문서들은 `ai4i2020.csv`처럼 정리된 데이터셋이 아니라, 공식 웹사이트에 공개된 매뉴얼·규정·안전자료를 직접 수집해서 RAG용 문서 코퍼스로 만드는 방식이다.

---

# 1. 전체 구조 요약

## 1.1 데이터의 역할 구분

| 구분 | 데이터/문서 | 역할 |
|---|---|---|
| 정형 예측 데이터 | AI4I 2020 | 공정 변수 기반 불량/고장 예측 |
| 설비 매뉴얼 | Haas 문서 | CNC 장비 조작, 트러블슈팅, 예방정비 Q&A |
| 안전 규정/절차 | OSHA 문서 | 비상대응, 기계 방호, 안전 절차 Q&A |
| 한국어 안전/기술 기준 | KOSHA 문서 | 기술문서 구성, 안전장치, 위험기계 분류, 점검 문서 기준 |
| 제조 테스트베드 문서 | NIST SMS Test Bed | 제조 테스트베드 데이터, 기술 패키지, MTConnect 구조 참고 |
| 도면 QA 데이터 | PIDQA | P&ID 도면 이미지 기반 질의응답 확장용 |

---

## 1.2 가장 중요한 개념

```text
AI4I = 모델 예측용 데이터
Haas / OSHA / KOSHA = RAG 검색용 문서
골든 데이터셋 = LLM 답변 평가용 정답 세트
```

즉, Haas / OSHA / KOSHA 문서는 모델 학습용 CSV가 아니다.

이 문서들은 다음 기능에 사용된다.

```text
1. 공정·설비 지식 기반 Q&A
2. 안전·비상 대응 안내
3. 기술 문서 요약
4. 점검·정비 보고서 초안 생성
5. 답변 근거 문서 citation 제공
```

---

# 2. 어디서 문서를 얻는가?

## 2.1 Haas 문서

## 용도

Haas는 CNC 장비 제조사다. 공식 서비스 페이지에서 CNC 장비 관련 매뉴얼과 점검 문서를 제공한다.

Haas 문서는 다음 기능에 적합하다.

```text
- CNC 장비 조작 방법 Q&A
- G-code / M-code / 설정 설명
- 트러블슈팅 안내
- 예방정비 안내
- 점검 보고서 생성
```

## 확보 위치

| 문서 종류 | 설명 | 사용 목적 |
|---|---|---|
| Operator’s Manuals | 장비 조작 매뉴얼 | 조작 방법, 기본 기능 설명 |
| How-To Procedures | 절차형 문서 | 특정 작업 순서 안내 |
| Troubleshooting Guides | 고장/증상 대응 문서 | 이상 상황 대응 Q&A |
| Preventive Maintenance | 예방정비 문서 | 점검 항목, 정비 주기 안내 |
| G-Code / M-Code / Settings | CNC 코드 및 설정 문서 | 제어 코드, 설정값 설명 |

## 대표 URL

```text
https://www.haascnc.com/service.html
https://www.haascnc.com/owners/Service/operators-manual.html
https://www.haascnc.com/service/manuals/electrical-and-mechanical-service-operators-manuals.html
```

## 예시 질문

```text
“CNC 냉각수 펌프 이상이면 무엇을 먼저 확인해야 해?”
“Tool changer 문제가 생기면 어떤 순서로 점검해야 해?”
“G-code와 M-code는 무슨 차이야?”
“예방정비 항목에는 무엇이 있어?”
```

## 주의점

Haas 문서에는 일부 정비/수리 절차는 자격 있는 인원이 수행해야 한다는 안전 주의가 포함되어 있다.

따라서 Agent는 다음처럼 말해야 한다.

```text
가능:
“담당자가 필터, 펌프 작동음, 냉각수 잔량을 점검하는 것을 권장합니다.”

불가능:
“제가 설비를 정지하고 펌프를 교체하겠습니다.”
```

---

# 3. OSHA 문서

## 3.1 OSHA 문서의 역할

OSHA는 미국 산업안전보건청이다. 공개 규정과 eTool 자료가 많아서 Safety Ops 기능에 적합하다.

OSHA 문서는 다음 기능에 사용한다.

```text
- 비상대응 절차 안내
- 대피계획 안내
- 기계 방호 기준 설명
- Lockout/Tagout 절차 설명
- 안전 관련 근거 문서 citation
```

---

## 3.2 확보할 문서

| 문서 | 용도 | 대표 URL |
|---|---|---|
| Emergency Action Plans, 1910.38 | 비상대응계획 기준 | https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.38 |
| Evacuation Plans and Procedures | 대피계획/eTool | https://www.osha.gov/etools/evacuation-plans-procedures/eap |
| Machine Guarding, 1910.212 | 기계 방호 기준 | https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.212 |
| Lockout/Tagout, 1910.147 | 에너지 차단/잠금 표지 기준 | https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.147 |
| Machine Guarding Overview | 기계 방호 개요 | https://www.osha.gov/machine-guarding |

---

## 3.3 예시 질문

```text
“비상상황 발생 시 어떤 절차로 대응해야 해?”
“Emergency Action Plan에는 어떤 항목이 들어가야 해?”
“기계 방호 장치는 왜 필요한가?”
“회전부 근처 작업 시 어떤 안전 조치를 확인해야 해?”
“정비 전 Lockout/Tagout은 왜 필요한가?”
```

---

# 4. KOSHA 문서

## 4.1 KOSHA 문서의 역할

KOSHA는 한국산업안전보건공단이다. 한국어 안전자료와 기술문서 구조를 잡는 데 유용하다.

KOSHA 문서는 다음 기능에 사용한다.

```text
- 한국어 안전 Q&A
- 기술문서 구성 기준
- 위험기계/안전장치 분류체계
- LOTO, 비상정지, 인터록 관련 설명
- 점검 보고서 템플릿 설계
```

---

## 4.2 KOSHA 기술문서 가이드란?

KOSHA 기술문서 가이드는 산업용 기계·설비의 기술문서를 어떻게 구성해야 하는지 알려주는 안내서다.

쉽게 말하면:

```text
“설비 기술문서에는 어떤 항목이 들어가야 하는가?”
```

에 대한 기준표다.

## 기술문서에 포함되는 항목 예시

| 항목 | AI 프로젝트에서의 활용 |
|---|---|
| 기계·설비 도면 | 설비 구조 Q&A |
| 전기 관련 도면 | 전원, 회로, 인터록 Q&A |
| 유체·가스 관련 도면 | 배관, P&ID, 압력, 유량 Q&A |
| 사용자 매뉴얼 | 조작 방법, 안전 주의사항 설명 |
| 설계 기준 및 강도 계산 자료 | 기술 문서 요약 |
| 시험성적서 | 인증/검사 문서 검색 |
| 체크리스트 | 점검 보고서 생성 |
| 비상정지 회로 | Safety Ops |
| 인터록 리스트 | 이상 상황 대응 |
| 이상 상황과 대책 | 조치 추천 |
| 점검 간격과 점검 목록 | 예방정비 안내 |

---

## 4.3 대표 URL

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

## 4.4 예시 질문

```text
“기술문서에는 어떤 도면이 필요해?”
“인터록 리스트에는 어떤 항목이 들어가야 해?”
“비상정지 회로 설명은 어디에 들어가야 해?”
“위험기계류에는 어떤 설비가 포함돼?”
“점검 보고서에는 어떤 항목을 넣어야 해?”
“LOTO 절차는 정비 전에 왜 필요한가?”
```

---

# 5. NIST SMS Test Bed 문서

## 5.1 역할

NIST Smart Manufacturing Systems Test Bed는 제조 테스트베드 관련 자료를 제공한다.

이 저장소에는 다음 자료가 포함된다.

```text
- raw 제조 데이터
- MTConnect adapter / agent 구성
- Technical Data Packages
- 테스트베드 설정 및 문서
```

## 대표 URL

```text
NIST SMS Test Bed 소개
https://www.nist.gov/laboratories/tools-instruments/smart-manufacturing-systems-sms-test-bed

GitHub 저장소
https://github.com/usnistgov/smstestbed
```

## 사용 목적

```text
- 제조 테스트베드 구조 참고
- MTConnect 기반 데이터 흐름 참고
- 설비 데이터와 문서 패키지 구조 참고
- 고급 확장용
```

---

# 6. PIDQA 도면 QA 데이터

## 6.1 역할

PIDQA는 P&ID, 즉 배관계장도 이미지를 대상으로 한 질의응답 데이터셋이다.

이 데이터는 다음 기능에 적합하다.

```text
- 도면 이미지 기반 Q&A
- P&ID 내 심볼 개수 질의
- P&ID 내 연결 관계 질의
- 그래프 기반 도면 reasoning
```

## 대표 URL

```text
https://github.com/mgupta70/PIDQA
```

## 주의점

PIDQA는 실제 제조 현장 문서라기보다는 연구용 데이터셋이다.

따라서 MVP에서는 필수는 아니고, 도면 이미지 기반 Q&A를 확장할 때 사용한다.

---

# 7. 실제 수집 절차

## 7.1 1단계: seed URL 목록 만들기

처음부터 크롤러를 크게 만들 필요 없다.

먼저 공식 문서 URL 목록을 수동으로 만든다.

파일명 예시:

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

## 7.2 2단계: HTML/PDF 다운로드

수집 폴더 구조는 다음처럼 잡는다.

```text
data/
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

HTML 문서 다운로드 예시:

```python
import requests
from pathlib import Path

docs = [
    {
        "source": "OSHA",
        "title": "Emergency Action Plan 1910.38",
        "url": "https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.38",
        "path": "data/raw_docs/osha/emergency_action_plan/1910_38.html"
    }
]

for doc in docs:
    html = requests.get(doc["url"], timeout=20).text
    path = Path(doc["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
```

PDF 다운로드 예시:

```python
import requests
from pathlib import Path

url = "PDF_URL"
path = Path("data/raw_docs/haas/manuals/manual.pdf")

res = requests.get(url, timeout=30)
path.parent.mkdir(parents=True, exist_ok=True)
path.write_bytes(res.content)
```

---

## 7.3 3단계: 텍스트 추출

HTML은 BeautifulSoup으로 본문만 추출한다.

PDF는 PyMuPDF, pypdf, unstructured 등을 사용할 수 있다.

예시:

```python
from bs4 import BeautifulSoup
from pathlib import Path

html_path = Path("data/raw_docs/osha/emergency_action_plan/1910_38.html")
html = html_path.read_text(encoding="utf-8")

soup = BeautifulSoup(html, "html.parser")

for tag in soup(["script", "style", "nav", "footer"]):
    tag.decompose()

text = soup.get_text("\n")
cleaned = "\n".join(line.strip() for line in text.splitlines() if line.strip())

Path("data/processed_docs/osha_1910_38.txt").write_text(cleaned, encoding="utf-8")
```

---

## 7.4 4단계: chunking

문서를 그대로 Vector DB에 넣지 않는다.

일정 길이로 나누고, 각 chunk에 메타데이터를 붙인다.

예시 chunk:

```json
{
  "chunk_id": "osha_1910_38_0001",
  "source": "OSHA",
  "document_title": "Emergency Action Plan 1910.38",
  "doc_type": "safety_procedure",
  "equipment_type": "general",
  "section": "Minimum elements of an emergency action plan",
  "language": "en",
  "text": "An emergency action plan must include procedures for reporting a fire or other emergency...",
  "url": "https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.38"
}
```

---

## 7.5 5단계: Vector DB에 저장

Vector DB 후보:

```text
- Chroma
- FAISS
- Supabase pgvector
- PostgreSQL + pgvector
```

처음 MVP는 Chroma가 가장 쉽다.

Spring Boot와 연결하려면 PostgreSQL + pgvector 또는 Supabase pgvector도 좋다.

---

# 8. 최소 MVP 문서 세트

처음부터 많이 모을 필요 없다.

아래 정도만 모아도 충분하다.

| 출처 | 문서 종류 | 개수 | 역할 |
|---|---|---:|---|
| Haas | Operator Manual | 1~2개 | CNC 조작/설비 지식 Q&A |
| Haas | Troubleshooting Guide | 3~5개 | 이상 증상 대응 |
| Haas | Preventive Maintenance | 2~3개 | 예방정비/점검 안내 |
| OSHA | Emergency Action Plan | 1개 | 비상대응 Safety Ops |
| OSHA | Machine Guarding | 1개 | 기계 방호/안전장치 Q&A |
| OSHA | Lockout/Tagout | 1개 | 정비 전 에너지 차단 절차 |
| KOSHA | 기술문서 가이드 | 1개 | 문서 구조/보고서 기준 |
| KOSHA | 위험기계/안전장치 분류 | 1개 | 설비 분류체계/메타데이터 |
| KOSHA | LOTO/안전 포스터 | 1~3개 | 한국어 안전 대응 자료 |
| NIST | SMS Test Bed 문서 | 선택 | 제조 테스트베드 확장 |
| PIDQA | P&ID QA 데이터 | 선택 | 도면 이미지 Q&A 확장 |

---

# 9. 최종 RAG 데이터 구조

## 9.1 문서 메타데이터 테이블

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

## 9.2 chunk 테이블

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

# 10. 실제 서비스 흐름

## 예시 질문

```text
“토크가 높고 공구 마모가 큰데 어떤 점검을 해야 해?”
```

## 처리 흐름

```text
1. AI4I 예측 Tool 실행
   - 고장 위험도 계산
   - OSF 가능성 판단
   - Torque high, Tool wear high 근거 추출

2. RAG 검색
   - Haas 예방정비 문서 검색
   - KOSHA 점검/정비 문서 구조 검색
   - OSHA/KOSHA 안전 절차 검색

3. LLM Agent 응답 생성
   - 과부하 가능성 설명
   - 공구 마모 및 토크 부하 조건 점검 권장
   - 정비 전 안전 절차 확인 안내
   - 근거 문서 링크 제공

4. 자동 문서화
   - 점검 보고서 초안 생성
   - 예측 결과와 참고 문서 저장
```

---

# 11. 구현 우선순위

## 1단계: 예측 + 문서 검색 MVP

```text
AI4I CSV
+ OSHA 2개 문서
+ KOSHA 2개 문서
+ Haas 3~5개 문서
```

기능:

```text
- 공정 데이터 입력
- 고장 위험/고장모드 예측
- 관련 문서 검색
- 근거 포함 답변 생성
- 결과 저장
```

---

## 2단계: Safety Ops 강화

추가 문서:

```text
- OSHA Lockout/Tagout
- OSHA Machine Guarding
- KOSHA LOTO 자료
- KOSHA 위험기계/안전장치 분류
```

기능:

```text
- 비상상황 질문 대응
- 정비 전 안전 절차 안내
- 설비 분류별 안전장치 검색
```

---

## 3단계: Automated Documentation

기능:

```text
- 점검 결과 입력
- 관련 문서 자동 검색
- 점검 보고서 초안 생성
- 보고서 저장/조회
```

---

## 4단계: 도면 이미지 Q&A 확장

추가 데이터:

```text
PIDQA
P&ID 샘플 이미지
```

기능:

```text
- 도면 이미지 업로드
- 도면 내 심볼/연결 관계 질의응답
- P&ID 기반 그래프 검색
```

---

# 12. 최종 결론

Haas / OSHA / KOSHA 문서는 이미 정리된 CSV 데이터셋이 아니다.

이 문서들은 다음 방식으로 확보한다.

```text
1. 공식 웹사이트에서 문서 URL을 수집한다.
2. HTML 또는 PDF 파일로 저장한다.
3. 본문 텍스트를 추출한다.
4. chunk 단위로 나눈다.
5. source, doc_type, equipment_type 같은 메타데이터를 붙인다.
6. Vector DB에 저장한다.
7. LLM Agent가 검색 결과를 근거로 답변한다.
```

최소 MVP는 다음 조합이 가장 현실적이다.

```text
AI4I 2020
+ Haas CNC 매뉴얼/트러블슈팅 문서
+ OSHA 비상대응/기계방호/LOTO 문서
+ KOSHA 기술문서 가이드/위험기계 분류/안전자료
```

이렇게 만들면 다음 세 기능을 모두 구현할 수 있다.

```text
1. 공정·설비 지식 기반 AI 질의응답
2. 안전·비상 대응 지원
3. 기술 문서·보고서 지원 AI
```

다만 자동 문서화의 품질 평가는 공개 데이터만으로는 부족하므로, 점검 결과와 기대 보고서로 구성된 자체 골든 데이터셋을 별도로 만들어야 한다.
