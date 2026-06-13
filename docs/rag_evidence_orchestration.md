# RAG Evidence SubAgent

RAG Evidence is a LangGraph `StateGraph` subagent. It is separate from the
AI4I prediction tool: AI4I process data drives risk prediction, while OSHA,
Haas, and KOSHA documents provide maintenance, safety, and troubleshooting
evidence.

## Runtime Shape

```text
RootManufacturingGraph
  -> manufacturing analysis
  -> RagEvidenceSubAgent.invoke(...)
       -> plan_queries
       -> retrieve
       -> filter
       -> grade
       -> cite
       -> build_payload
       -> trace
  -> safety / formatting
```

The root graph does not call RAG internals directly. It converts root
`AgentState` into `RagEvidenceInput`, invokes the compiled subagent graph, and
copies the resulting documents, citations, grade, context, warnings, and trace
back into canonical root state fields.

## State

Graph state is request-scoped and lives in `app.agent.rag_evidence.state`.
It carries only the active request, plan, prediction/context snapshot, query
specs, retrieved chunks, filtered/selected chunks, grade, citations, warnings,
trace, and output.

No request-specific state is stored on services.

## Query Fan-Out

Fan-out is deterministic and bounded to four query specs:

- `primary`
- `maintenance_check`
- `troubleshooting`
- `safety_loto_guarding`

Torque, tool wear, OSF/TWF, spindle, maintenance, and safety cues add the extra
specs. The policy does not call an LLM.

## Selection And Trace

Evidence selection prefers usable, relevant chunks first, then failure/signal or
safety-gate alignment, high/medium priority, and finally limited diversity.

The trace is compact and log-safe. It includes query spec names, backend,
counts, selected sources, selected safety gates, warnings, and corpus count
mismatch status. It does not include raw chunk text, API keys, full prompts, or
large local paths.

Chroma failures do not fall back to JSONL search in the RAG Evidence path.
Failures produce empty evidence plus explicit warnings.

## Chroma Health

The expected local corpus has 727 JSONL chunks and 727 Chroma vectors after
rebuild. If a different environment reports a mismatch, runtime requests emit:

```text
Chroma collection count mismatch: expected 727, actual <actual>. Retrieval continues. Reindex corpus separately.
```

This subagent does not sync, reindex, download, or mutate the corpus.

## Not Included

- Streamlit upload/vectorize UI
- corpus versioning
- ingestion redesign
- Chroma sync or automatic reindex
- Safety or formatter subgraph migration
