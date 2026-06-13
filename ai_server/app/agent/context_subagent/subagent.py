from __future__ import annotations

from langgraph.graph import END, StateGraph

from .nodes import ContextDeps, build_context_pack, emit_context_output, load_request_context, resolve_conversation_context, validate_context
from .state import ContextInput, ContextOutput, ContextState, to_output, to_state


def build_context_graph(deps: ContextDeps):
    graph = StateGraph(ContextState)
    graph.add_node('load_request_context', lambda state: load_request_context(state, deps))
    graph.add_node('resolve_conversation_context', lambda state: resolve_conversation_context(state, deps))
    graph.add_node('build_context_pack', lambda state: build_context_pack(state, deps))
    graph.add_node('validate_context', lambda state: validate_context(state, deps))
    graph.add_node('emit_context_output', lambda state: emit_context_output(state, deps))

    graph.set_entry_point('load_request_context')
    graph.add_edge('load_request_context', 'resolve_conversation_context')
    graph.add_edge('resolve_conversation_context', 'build_context_pack')
    graph.add_edge('build_context_pack', 'validate_context')
    graph.add_edge('validate_context', 'emit_context_output')
    graph.add_edge('emit_context_output', END)
    return graph.compile()


class ContextSubAgent:
    def __init__(self, deps: ContextDeps):
        self.graph = build_context_graph(deps)

    def invoke(self, input_data: ContextInput) -> ContextOutput:
        return to_output(self.graph.invoke(to_state(input_data)))
