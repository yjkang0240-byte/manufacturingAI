from __future__ import annotations

from langgraph.graph import END, StateGraph

from .nodes import PlanningDeps, build_planning_context, emit_planning_output, run_diagnostic_planner, validate_plan
from .state import PlanningInput, PlanningOutput, PlanningState, to_output, to_state


def build_planning_graph(deps: PlanningDeps):
    graph = StateGraph(PlanningState)
    graph.add_node('build_planning_context', lambda state: build_planning_context(state, deps))
    graph.add_node('run_diagnostic_planner', lambda state: run_diagnostic_planner(state, deps))
    graph.add_node('validate_plan', lambda state: validate_plan(state, deps))
    graph.add_node('emit_planning_output', lambda state: emit_planning_output(state, deps))

    graph.set_entry_point('build_planning_context')
    graph.add_edge('build_planning_context', 'run_diagnostic_planner')
    graph.add_edge('run_diagnostic_planner', 'validate_plan')
    graph.add_edge('validate_plan', 'emit_planning_output')
    graph.add_edge('emit_planning_output', END)
    return graph.compile()


class PlanningSubAgent:
    def __init__(self, deps: PlanningDeps):
        self.graph = build_planning_graph(deps)

    def invoke(self, input_data: PlanningInput) -> PlanningOutput:
        return to_output(self.graph.invoke(to_state(input_data)))
