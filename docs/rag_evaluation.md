# RAG Evaluation Guide

이 문서는 제조 RAG/Agent 답변 품질을 감으로 확인하지 않고, golden dataset, LangSmith tracing, deterministic checks, Ragas, custom LLM judge로 비교하는 초기 평가 흐름을 설명한다.

## 1. 평가 구조 개요

- `golden dataset`: 시험지/정답지 역할을 한다. 질문, reference answer, 기대 source id, category, difficulty를 담는다.
- `LangSmith tracing`: 각 case 실행 trace, route, metadata, tag를 남겨 실험 간 비교와 원인 분석에 사용한다.
- `deterministic checks`: LLM judge 없이 확인 가능한 규칙이다. retrieval empty 여부, expected source recall, citation integrity, error 여부, response empty 여부를 본다.
- `Ragas`: RAG 답변의 faithfulness, relevancy, context precision/recall 같은 metric을 계산한다.
- `custom LLM judge`: 제품 기준에 맞춘 rubric으로 제조/안전 답변의 유용성, 근거성, 안전성, 장황함, citation 모순 여부를 평가한다.

## 2. 왜 지금은 notebook 하나로 시작하는가

현재 평가는 기준과 rubric이 아직 확정되지 않은 실험 단계다. `ai_server/notebooks/01_rag_eval_lab.ipynb` 하나에 로딩, 실행, 저장, 평가, 실패 분석을 모아두면 빠르게 바꿔보며 기준을 다듬을 수 있다.

평가 기준이 안정되면 notebook 내부 함수를 `eval/run_eval.py`, `eval/ragas_eval.py`, pytest deterministic checks, LangSmith dataset/experiment 흐름으로 분리할 수 있다. 지금 단계에서는 일부러 notebook 하나에 모아둔다.

## 3. 파일 구조

- `ai_server/eval/golden_rag_cases.jsonl`: RAG 평가용 golden dataset 샘플. Codex가 만든 임시 초안이다.
- `ai_server/eval/results/`: notebook 실행 결과가 저장되는 디렉토리다.
- `ai_server/notebooks/01_rag_eval_lab.ipynb`: 평가 실험 notebook이다.

## 4. 실행 방법

Notebook은 `ai_server` 디렉터리에서 실행하는 것을 기본으로 한다. Jupyter kernel은 `ai_server/.venv`의 Python을 선택한다. notebook, golden dataset, results, `.env.example`, requirements가 모두 `ai_server` 아래에 있어 같은 venv/env 공간을 공유한다. 기준 env 파일은 `ai_server/.env`다. notebook 내부에서 `ai_server` 디렉터리를 `sys.path`에 추가하므로 `app.main`, `app.agent.*` import가 동작한다.

1. repo root에서 `ai_server`로 이동한다.

```bash
cd /path/to/manufacturingAI
cd ai_server
```

2. `ai_server/.env.example`을 `ai_server/.env`로 복사하고 필요한 값을 설정한다.

```bash
cp .env.example .env
```

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=manufacturing-agent-eval
OPENAI_API_KEY=
```

3. 필요한 패키지를 현재 `ai_server` venv에 설치한다.

```bash
pip install -r requirements.txt
python -m ipykernel install --user --name manufacturing-ai-server --display-name "manufacturing-ai-server"
```

4. `notebooks/01_rag_eval_lab.ipynb`를 열고 kernel을 `manufacturing-ai-server` 또는 `ai_server/.venv` Python으로 선택한다.
5. working directory를 `ai_server`로 둔 상태에서 `Restart & Run All`로 깨끗한 kernel에서 실행하는 것을 권장한다.

Notebook은 `ai_server/.env`를 로드한 뒤 기존 FastAPI 실행 경로와 같은 `RootManufacturingGraph`를 사용한다. public `/agent/send` 응답 포맷은 바꾸지 않고, notebook에서 graph final state를 직접 정규화해 평가 필드를 만든다.

## 5. 결과 파일 설명

- `ai_server/eval/results/rag_raw_outputs_v1.jsonl`: case별 정규화된 RAG 실행 결과.
- `ai_server/eval/results/rag_raw_outputs_v1.csv`: 위 결과의 CSV 버전.
- `ai_server/eval/results/deterministic_check_results_v1.csv`: deterministic checks 결과.
- `ai_server/eval/results/ragas_scores_v1.csv`: Ragas metric 결과. Ragas import 또는 실행 실패 시 빈 파일일 수 있다.
- `ai_server/eval/results/custom_llm_judge_scores_v1.csv`: custom LLM judge 결과. LLM 설정이 없거나 실행을 건너뛰면 빈 파일일 수 있다.
- `ai_server/eval/results/merged_eval_results_v1.csv`: raw output, deterministic checks, Ragas, custom judge를 `id` 기준으로 합친 결과.
- `ai_server/eval/results/failure_cases_v1.csv`: 실패 또는 주의가 필요한 case만 모은 결과.

## 6. 사람이 검수해야 할 것

- `reference`: Codex가 만든 reference answer는 임시 초안이다. 실제 제품 기준과 현장 안전 기준에 맞게 사람이 검수해야 한다.
- `expected_source_ids`: 실제 Chroma/vector store chunk를 확인한 뒤 채워야 한다. 확실하지 않으면 빈 배열로 유지한다.
- `safety policy`: LOTO, 정비 안전, 위험 지시 제한, 법적 판단 경계 문구가 조직 기준과 맞는지 검토해야 한다.
- `good answer 기준`: Ragas와 LLM judge 점수만으로 품질을 확정하지 말고, 사람이 좋은 답변 기준을 정렬해야 한다.

## 7. 주의사항

Ragas와 custom LLM judge는 LLM 호출 비용이 들 수 있다. API key를 notebook이나 dataset에 직접 쓰지 말고 `ai_server/.env` 또는 shell 환경변수로만 제공한다.

Ragas 점수는 절대적인 정답이 아니라 같은 golden dataset에서 prompt, retrieval, chunking, rerank 변경 전후를 비교하는 추세 지표로 사용한다. LLM judge도 완벽하지 않으므로 사람 평가와 alignment가 필요하다.

Ragas, LangSmith, LangChain 계열 패키지는 버전 조합에 따라 metric 이름이나 dataset column contract가 달라질 수 있다. notebook은 가능한 metric만 실행하도록 작성되어 있지만, 충돌이 있으면 대규모 dependency upgrade보다 현재 환경에 맞춘 작은 조정을 우선한다.

## 8. 나중에 할 일

- notebook 로직을 `eval/run_eval.py`로 분리한다.
- deterministic checks를 pytest로 분리한다.
- LangSmith dataset/experiment로 확장한다.
- 실패 케이스를 golden dataset에 추가한다.
- 사람이 검수한 `reference`와 `expected_source_ids`로 golden dataset v2를 만든다.
