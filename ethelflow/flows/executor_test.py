from typing import Any, Dict, TypedDict, Optional
from langgraph.graph import StateGraph
from ethelflow.agents.executor.node_adapter import executor_node


class ExecutorTestState(TypedDict, total=False):
    image: str
    type: str
    expr: str
    code: str
    execution_result: Optional[Dict[str, Any]]


async def run(context=None, query=None, file_id=None, stream=False):
    type = context.get("type")
    if type not in ["python", "maxima"]:
        raise ValueError(
            "Invalid or missing 'type' in context. Must be 'python' or 'maxima'."
        )

    code: str = ""
    expr: str = ""
    image: str = ""
    if type == "python":
        if context.get("code") is None:
            raise ValueError("Missing 'code' in context for python execution")
        code = context.get("code")
        image = "python:3.12-slim"
    elif type == "maxima":
        if context.get("expr") is None:
            raise ValueError("Missing 'expr' in context for maxima execution")
        expr = context.get("expr")
        image = "maxima-executor:latest"

    initial_state: ExecutorTestState = {
        "image": image,
        "type": type,
        "expr": expr,
        "code": code,
    }

    flow = StateGraph(ExecutorTestState)

    flow.add_node("executor", executor_node())

    flow.set_entry_point("executor")
    flow.set_finish_point("executor")

    # Compile the graph
    app = flow.compile()

    if stream:
        async for item in app.astream_events(initial_state, version="v2"):
            if item["event"] == "on_chain_stream":
                yield item["data"]["chunk"]["reasoning_response"]
    else:
        yield await app.ainvoke(initial_state)
