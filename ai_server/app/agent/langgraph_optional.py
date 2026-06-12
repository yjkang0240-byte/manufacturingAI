from __future__ import annotations

def build_demo_graph():
    """Optional LangGraph graph skeleton.

    The production-ready MVP uses ManufacturingAgentGraph for stability. This function
    shows how the same route can be represented with LangGraph when desired.
    """
    try:
        from langgraph.graph import END, StateGraph
    except Exception as exc:
        raise RuntimeError('langgraph is not installed. Install ai_server/requirements.txt') from exc
    def passthrough(state: dict):
        state.setdefault('route', []).append('node')
        return state
    graph = StateGraph(dict)
    for name in ['supervisor','prediction','rag_search','safety_ops','explanation','report']:
        graph.add_node(name, passthrough)
    graph.set_entry_point('supervisor')
    graph.add_edge('supervisor','prediction')
    graph.add_edge('prediction','rag_search')
    graph.add_edge('rag_search','safety_ops')
    graph.add_edge('safety_ops','explanation')
    graph.add_edge('explanation','report')
    graph.add_edge('report', END)
    return graph.compile()
