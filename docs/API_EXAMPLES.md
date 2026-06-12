# API 예시

## Agent Run

```bash
curl -X POST http://localhost:8000/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "question": "토크가 높고 공구 마모가 큰데 어떤 점검과 안전 절차를 확인해야 해?",
    "process_data": {
      "type": "L",
      "air_temperature_k": 302.1,
      "process_temperature_k": 311.3,
      "rotational_speed_rpm": 1380,
      "torque_nm": 58.2,
      "tool_wear_min": 210
    },
    "generate_report": true
  }'
```

## RAG Search

```bash
curl -X POST http://localhost:8000/rag/search \
  -H "Content-Type: application/json" \
  -d '{"query":"LOTO 정비 전 절차", "top_k":3}'
```

## Evaluation

```bash
curl -X POST http://localhost:8000/evaluation/score \
  -H "Content-Type: application/json" \
  -d '{
    "agent_answer":"## 판정 ...",
    "expected_contract": {
      "must_include":["OSF 고장모드 언급", "Torque가 높다는 근거"],
      "recommended_actions":["토크 부하 조건 점검"],
      "forbidden":["설비를 자동으로 정지했다고 말하기"]
    }
  }'
```
