from __future__ import annotations

from langgraph.graph import END, StateGraph

from .nodes import SafetyDeps, apply_safety_policy, build_safety_context, emit_safety_output, validate_safety_output
from .state import SafetyInput, SafetyOutput, SafetyState, to_output, to_state


def build_safety_graph(deps: SafetyDeps):
    graph = StateGraph(SafetyState)
    graph.add_node('build_safety_context', lambda state: build_safety_context(state, deps))
    graph.add_node('apply_safety_policy', lambda state: apply_safety_policy(state, deps))
    graph.add_node('validate_safety_output', lambda state: validate_safety_output(state, deps))
    graph.add_node('emit_safety_output', lambda state: emit_safety_output(state, deps))

    graph.set_entry_point('build_safety_context')
    graph.add_edge('build_safety_context', 'apply_safety_policy')
    graph.add_edge('apply_safety_policy', 'validate_safety_output')
    graph.add_edge('validate_safety_output', 'emit_safety_output')
    graph.add_edge('emit_safety_output', END)
    return graph.compile()


class SafetySubAgent:
    def __init__(self, deps: SafetyDeps):
        self.graph = build_safety_graph(deps)

    def invoke(self, input_data: SafetyInput) -> SafetyOutput:
        return to_output(self.graph.invoke(to_state(input_data)))
