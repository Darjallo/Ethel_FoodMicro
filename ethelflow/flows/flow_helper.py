"""
flow_helper.py  — common utilities for Ethel flows
"""
from typing import Callable, Dict, Iterator, List, Tuple, Any
from langgraph.graph import StateGraph, START, END


# ------------- unchanged helpers ---------------------------------
def extract_query(mapping: Dict[str, str]) -> Callable[[dict], Iterator[dict]]:
    def _node(state_dict: dict) -> Iterator[dict]:
        q = state_dict.get("query", {}) or {}
        out = {dst: (q.get(src, "") if isinstance(q.get(src, ""), str) else "")
               for src, dst in mapping.items()}
        yield out
    return _node


def linear(builder: StateGraph,
           ordered_nodes: List[Tuple[str, Callable]]) -> None:
    for idx, (name, fn) in enumerate(ordered_nodes):
        builder.add_node(name, fn)
        if idx == 0:
            builder.add_edge(START, name)
        else:
            builder.add_edge(ordered_nodes[idx - 1][0], name)
    builder.add_edge(ordered_nodes[-1][0], END)


# ------------- FIXED run_flow ------------------------------------
def run_flow(app, state: dict, stream: bool):
    """
    • If stream=True  → yield chunks directly from app.stream.
    • If stream=False → iterate app.stream internally, yield the
      *last* chunk (so pause payload is preserved).
    """
    if stream:
        yield from app.stream(state)
    else:
        last = None
        for upd in app.stream(state):
            last = upd
        # Fallback: if the graph ended without emitting updates
        if last is None:
            last = app.invoke(state)
        yield last

