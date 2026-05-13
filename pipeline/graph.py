"""LangGraph StateGraph assembly (US5, US6)."""
from langgraph.graph import StateGraph, END

from pipeline.etl_state import ETLState
from agents.scout import scout_node
from agents.architect import architect_node
from agents.engineer import engineer_generate_node, engineer_execute_node
from agents.loader import loader_node
from pipeline.router import engineer_router


def build_graph() -> StateGraph:
    """Full pipeline: Scout → Architect → Engineer (generate+execute) → Loader."""
    graph = StateGraph(ETLState)

    graph.add_node("scout", scout_node)
    graph.add_node("architect", architect_node)
    graph.add_node("engineer_generate", engineer_generate_node)
    graph.add_node("engineer_execute", engineer_execute_node)
    graph.add_node("loader", loader_node)

    graph.set_entry_point("scout")
    graph.add_edge("scout", "architect")
    graph.add_edge("architect", "engineer_generate")
    graph.add_edge("engineer_generate", "engineer_execute")

    graph.add_conditional_edges(
        "engineer_execute",
        engineer_router,
        {
            "loader": "loader",
            "engineer": "engineer_generate",
            "architect": "architect",
            "__end__": END,
        },
    )

    graph.add_edge("loader", END)

    return graph.compile()


def build_plan_graph() -> StateGraph:
    """HITL Phase 1: Scout → Architect only. Stops so the user can review the plan."""
    graph = StateGraph(ETLState)

    graph.add_node("scout", scout_node)
    graph.add_node("architect", architect_node)

    graph.set_entry_point("scout")
    graph.add_edge("scout", "architect")
    graph.add_edge("architect", END)

    return graph.compile()


def build_execute_graph() -> StateGraph:
    """HITL Phase 2 (single-step): Engineer (generate+execute) → Loader. Starts from a pre-approved plan."""
    graph = StateGraph(ETLState)

    graph.add_node("engineer_generate", engineer_generate_node)
    graph.add_node("engineer_execute", engineer_execute_node)
    graph.add_node("loader", loader_node)

    graph.set_entry_point("engineer_generate")
    graph.add_edge("engineer_generate", "engineer_execute")

    graph.add_conditional_edges(
        "engineer_execute",
        engineer_router,
        {
            "loader": "loader",
            "engineer": "engineer_generate",
            "architect": "engineer_generate",
            "__end__": END,
        },
    )

    graph.add_edge("loader", END)

    return graph.compile()


def build_generate_graph() -> StateGraph:
    """HITL Phase 2a: Engineer generate only. Stops so the user can review the code."""
    graph = StateGraph(ETLState)

    graph.add_node("engineer_generate", engineer_generate_node)

    graph.set_entry_point("engineer_generate")
    graph.add_edge("engineer_generate", END)

    return graph.compile()


def build_run_graph() -> StateGraph:
    """HITL Phase 2b: Execute approved code → Loader. Auto-retries via engineer_generate if execution fails."""
    graph = StateGraph(ETLState)

    graph.add_node("engineer_generate", engineer_generate_node)
    graph.add_node("engineer_execute", engineer_execute_node)
    graph.add_node("loader", loader_node)

    graph.set_entry_point("engineer_execute")

    graph.add_conditional_edges(
        "engineer_execute",
        engineer_router,
        {
            "loader": "loader",
            "engineer": "engineer_generate",   # auto-retry without HITL
            "architect": "engineer_generate",
            "__end__": END,
        },
    )

    graph.add_edge("engineer_generate", "engineer_execute")
    graph.add_edge("loader", END)

    return graph.compile()
