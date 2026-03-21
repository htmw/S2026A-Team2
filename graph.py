"""LangGraph StateGraph assembly (US5, US6)."""
from langgraph.graph import StateGraph, END

from etl_state import ETLState
from agents.scout import scout_node
from agents.architect import architect_node
from agents.engineer import engineer_node
from agents.loader import loader_node
from router import engineer_router


def build_graph() -> StateGraph:
    graph = StateGraph(ETLState)

    # Register nodes
    graph.add_node("scout", scout_node)
    graph.add_node("architect", architect_node)
    graph.add_node("engineer", engineer_node)
    graph.add_node("loader", loader_node)

    # Linear edges
    graph.set_entry_point("scout")
    graph.add_edge("scout", "architect")
    graph.add_edge("architect", "engineer")

    # Conditional routing post-Engineer
    graph.add_conditional_edges(
        "engineer",
        engineer_router,
        {
            "loader": "loader",
            "engineer": "engineer",
            "architect": "architect",
            "__end__": END,
        },
    )

    graph.add_edge("loader", END)

    return graph.compile()
