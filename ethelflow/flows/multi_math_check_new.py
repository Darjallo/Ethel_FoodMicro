from typing import TypedDict, Dict, Any
from langgraph.graph import StateGraph

from ethelflow.agents.executor.models import ExecutionResult
from ethelflow.agents.executor.node_adapter import executor_node
from ethelflow.agents.reasoning.node_adapter import reasoning_node



# ──────────── State schema ─────────────────────────────────────
class MultiMathState(TypedDict, total=False):
    # expression & per-lang scripts
    expression: str
    maxima_script: str
    python_script: str
    r_script: str
    maxima_type: str
    python_type: str

    maxima_image: str
    python_image: str

    # raw agent outputs
    maxima_results: Dict[str, Any]
    python_results: Dict[str, Any]
    r_results: Dict[str, Any]


# ──────────── Flow entrypoint ──────────────────────────────────
async def run(context=None, query=None, file_id=None, stream=False):
    if context.get("expression") is None:
        raise ValueError("Missing 'expression' in context")

    state: MultiMathState = {
        "expression": context.get("expression"),
        "maxima_image": "maxima-executor:latest",
        "python_image": "python:3.12-slim",
        "maxima_type": "maxima",
        "python_type": "python",
    }

    flow = StateGraph(MultiMathState)

    def normalise(st):
        expr = st.get("expression", "") or ""
        yield {
            "maxima_script": f"{expr};",
            "python_script": f"print({expr.replace('^', '**')})",
            "r_script": f"print({expr})",
        }

    flow.add_node("norm", normalise)

    flow.add_node(
        "python",
        executor_node(
            image_key="python_image",
            type_key="python_type",
            code_key="python_script",
            output_key="python_results",
        ),
    )

    flow.add_node(
        "maxima",
        executor_node(
            image_key="maxima_image",
            type_key="maxima_type",
            expr_key="maxima_script",
            output_key="maxima_results",
        ),
    )

    def build_prompt(st: MultiMathState):
        maxima_result: ExecutionResult = ExecutionResult.model_validate(
            st.get("maxima_results")
        )
        python_result: ExecutionResult = ExecutionResult.model_validate(
            st.get("python_results")
        )
        prompt = (
            "Here are two outputs from math processors. "
            "Do they agree, why or why not? Ignore warning messages from the interpreters\n\n"
            f"Maxima: {maxima_result.stdout}\n"
            f"Python: {python_result.stdout}\n"
        )
        yield {"prompt": prompt}


    flow.add_node("prompt", build_prompt)

    flow.set_entry_point("norm")
    flow.add_edge("norm", "python")
    flow.add_edge("norm", "maxima")
    flow.add_edge("python", "prompt")
    flow.add_edge("maxima", "prompt")
    flow.set_finish_point("prompt")

    app = flow.compile(concurrency=2)

    if stream:
        async for item in app.astream_events(state, version="v2"):
            if item["event"] == "on_chain_stream":
                yield item["data"]["chunk"]["reasoning_response"]
    else:
        yield await app.ainvoke(state)

