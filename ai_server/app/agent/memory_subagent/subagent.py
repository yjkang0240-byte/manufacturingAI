from __future__ import annotations

from langgraph.graph import END, StateGraph

from .nodes import MemoryDeps, emit_memory_output, extract_memory_candidates, update_focus, write_answer_memory
from .state import MemoryInput, MemoryOutput, MemoryState, to_output, to_state


def build_memory_graph(deps: MemoryDeps):
    graph = StateGraph(MemoryState)
    graph.add_node('extract_memory_candidates', lambda state: extract_memory_candidates(state, deps))
    graph.add_node('update_focus', lambda state: update_focus(state, deps))
    graph.add_node('write_answer_memory', lambda state: write_answer_memory(state, deps))
    graph.add_node('emit_memory_output', lambda state: emit_memory_output(state, deps))

    graph.set_entry_point('extract_memory_candidates')
    graph.add_edge('extract_memory_candidates', 'update_focus')
    graph.add_edge('update_focus', 'write_answer_memory')
    graph.add_edge('write_answer_memory', 'emit_memory_output')
    graph.add_edge('emit_memory_output', END)
    return graph.compile()


class MemorySubAgent:
    def __init__(self, deps: MemoryDeps):
        self.graph = build_memory_graph(deps)

    def invoke(self, input_data: MemoryInput) -> MemoryOutput:
        return to_output(self.graph.invoke(to_state(input_data)))
