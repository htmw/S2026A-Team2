"""Conditional router — post-Engineer routing logic (US5)."""


def engineer_router(state: dict) -> str:
    """
    Routes based on engineer_verdict:
      pass      -> loader
      retry     -> engineer
      escalate  -> architect
      terminate -> __end__
    """
    verdict = state.get("engineer_verdict", "terminate")
    routes = {
        "pass": "loader",
        "retry": "engineer",
        "escalate": "architect",
        "terminate": "__end__",
    }
    return routes.get(verdict, "__end__")
