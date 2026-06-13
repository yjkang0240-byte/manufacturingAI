from __future__ import annotations

from langgraph.graph import END, StateGraph

from .nodes import RagEvidenceDeps, build_citations, build_payload, build_trace, filter_evidence, grade_evidence, plan_queries, retrieve
from .state import RagEvidenceInput, RagEvidenceOutput, RagEvidenceState, to_output, to_state


def build_rag_evidence_graph(deps: RagEvidenceDeps):
    graph = StateGraph(RagEvidenceState)
    graph.add_node('plan_queries', lambda state: plan_queries(state, deps))
    graph.add_node('retrieve', lambda state: retrieve(state, deps))
    graph.add_node('filter', lambda state: filter_evidence(state, deps))
    graph.add_node('grade', lambda state: grade_evidence(state, deps))
    graph.add_node('cite', lambda state: build_citations(state, deps))
    graph.add_node('build_payload', lambda state: build_payload(state, deps))
    graph.add_node('trace', lambda state: build_trace(state, deps))

    graph.set_entry_point('plan_queries')
    graph.add_edge('plan_queries', 'retrieve')
    graph.add_edge('retrieve', 'filter')
    graph.add_edge('filter', 'grade')
    graph.add_edge('grade', 'cite')
    graph.add_edge('cite', 'build_payload')
    graph.add_edge('build_payload', 'trace')
    graph.add_edge('trace', END)
    return graph.compile()


class RagEvidenceSubAgent:
    def __init__(self, deps: RagEvidenceDeps):
        self.graph = build_rag_evidence_graph(deps)

    def invoke(self, input_data: RagEvidenceInput) -> RagEvidenceOutput:
        return to_output(self.graph.invoke(to_state(input_data)))
