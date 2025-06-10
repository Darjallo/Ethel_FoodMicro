"""
Reusable utilities so individual flows stay concise.

Key helpers
===========

extract_query(mapping) -> Callable
    • Build a node that copies selected keys from state["query"] into state.

linear(builder, ordered_nodes)
    • Wire up START -> n1 -> n2 -> ... -> END in one go.

run_flow(app, state, stream) -> generator
    • Shared streaming or one-shot semantics.
"""
from typing import Callable, Dict, Iterator, List, Tuple, Any
from langgraph.graph import StateGraph, START, END


# ------------------------------------------------------------
# 1)  Build a query-extraction node
# ------------------------------------------------------------
def extract_query(mapping: Dict[str, str]) -> Callable[[dict], Iterator[dict]]:
    """
    mapping = { "query_key": "state_key", ... }
    Returns a node that yields {state_key: query[query_key], ...}
    Missing keys → "" (empty str).
    """
    def _node(state_dict: dict) -> Iterator[dict]:
        q = state_dict.get("query", {}) or {}
        out = {dst: (q.get(src, "") if isinstance(q.get(src, ""), str) else "")
               for src, dst in mapping.items()}
        yield out
    return _node


# ------------------------------------------------------------
# 2)  Wire a linear chain in a builder
# ------------------------------------------------------------
def linear(builder: StateGraph,
           ordered_nodes: List[Tuple[str, Callable]]) -> None:
    """
    ordered_nodes = [("name", node_func), ...]
    Adds nodes & edges START→n1→…→END.
    """
    for idx, (name, fn) in enumerate(ordered_nodes):
        builder.add_node(name, fn)
        if idx == 0:
            builder.add_edge(START, name)
        else:
            builder.add_edge(ordered_nodes[idx - 1][0], name)
    builder.add_edge(ordered_nodes[-1][0], END)


# ------------------------------------------------------------
# 3)  Common run helper
# ------------------------------------------------------------
def run_flow(app, state: dict, stream: bool):
    """Yield updates or final result according to stream flag."""
    if stream:
        yield from app.stream(state)
    else:
        yield app.invoke(state)

