# flow_manager/flows/reasoning_test.py
from typing import TypedDict, Dict, Any, List
from langgraph.graph import StateGraph, START, END
from .nodes import reasoning_completion_node
from .flow_helper import extract_query, run_flow


class ReasoningTestState(TypedDict, total=False):
    context: dict
    query: Dict[str, Any]
    stream: bool

    # pulled from query
    prompt: str
    fid: str

    # open-ai style
    messages: List[Dict[str, str]]
    file_ids: List[str]

    reasoning_result: Dict[str, Any]


def run(context=None, query=None, file_id=None, stream=False):
    state: ReasoningTestState = {
        "context": context,
        "query":   query or {},
        "stream":  stream,
    }
    builder = StateGraph(ReasoningTestState)

    # 1) pull "prompt" and "file_id" out of query
    builder.add_node("pull",
        extract_query({"prompt": "prompt", "file_id": "fid"}))
    builder.add_edge(START, "pull")

    # 2) build messages / file_ids lists
    def mk_openai(st):
        prompt = st.get("prompt", "")
        fid    = st.get("fid", "")
        yield {
            "messages": [{"role": "user", "content": prompt}],
            "file_ids": [fid] if fid else []
        }

    builder.add_node("format", mk_openai)
    builder.add_edge("pull", "format")

    # 3) reasoning agent
    builder.add_node("reason",
        reasoning_completion_node(
            input_key_map={"messages":"messages", "file_ids":"file_ids", "stream":"stream"},
            output_key="reasoning_result"))
    builder.add_edge("format", "reason")
    builder.add_edge("reason", END)

    app = builder.compile()
    yield from run_flow(app, state, stream)

