from typing import TypedDict, Any, Dict, List
from langgraph.graph import StateGraph, START, END

from .nodes import reasoning_completion_node


class ReasoningTestState(TypedDict, total=False):
    # Inputs from the Flow Manager
    context: dict
    query: Dict[str, Any]    # expecting { "prompt": str, "file_id": str }
    stream: bool

    # Transient fields we build
    messages: List[Dict[str, str]]
    file_ids: List[str]

    # Final output
    reasoning_result: Dict[str, Any]


def run(context=None, query=None, file_id=None, stream=False):
    """
    1) Pull “prompt” and “file_id” out of state["query"].
    2) Construct messages=[{"role":"user","content":<prompt>}], file_ids=[<file_id>].
    3) Call reasoning_completion_node → state["reasoning_result"].
    """
    state: ReasoningTestState = {
        "context": context,
        "query": query or {},
        "stream": stream,
    }

    builder = StateGraph(ReasoningTestState)

    # ─── Node #1 ───
    # Extract “prompt” and “file_id” from state["query"], build messages & file_ids
    def prep_node(state_dict: dict):
        q = state_dict.get("query", {}) or {}
        prompt = ""
        fid = ""
        if isinstance(q, dict):
            prompt = q.get("prompt", "") or ""
            fid = q.get("file_id", "") or ""
        # Build the OpenAI‐style messages list:
        user_msg = {"role": "user", "content": prompt}
        # Build file_ids list:
        file_ids = [fid] if (isinstance(fid, str) and fid) else []
        yield {
            "messages": [user_msg],
            "file_ids": file_ids
        }

    # ─── Node #2 ───
    # Call reasoning_completion_node, which expects `messages`, `file_ids`, and `stream`
    reasoning_node = reasoning_completion_node(
        input_key_map={
            "messages": "messages",
            "file_ids": "file_ids",
            "stream": "stream",
        },
        output_key="reasoning_result"
    )

    # ─── Wire it up ───
    builder.add_node("prep", prep_node)
    builder.add_node("reason", reasoning_node)

    builder.add_edge(START, "prep")
    builder.add_edge("prep", "reason")
    builder.add_edge("reason", END)

    app = builder.compile()

    if state.get("stream"):
        for update in app.stream(state):
            yield update
    else:
        yield app.invoke(state)

