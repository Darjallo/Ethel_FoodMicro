"""
multi_math_check
================
• Pulls "expression" from state["query"].
• Normalises that expression into three language-specific scripts.
• Runs Maxima, Python, R *in parallel*.
• Builds a single reasoning prompt that asks if outputs agree.
• Streams the reasoning agent’s answer if state["stream"] is True.
"""

from typing import TypedDict, Dict, Any, List
from langgraph.graph import StateGraph, START, END

from ethelflow.agents.maxima_processor.node_adapter import maxima_processor_node
from ethelflow.agents.python_processor.node_adapter import python_processor_node
from ethelflow.agents.r_processor.node_adapter import r_processor_node
from ethelflow.agents.reasoning_completion.node_adapter import reasoning_completion_node

from ethelflow.flows.flow_helper import extract_query, run_flow


# ──────────── State schema ─────────────────────────────────────
class MultiMathState(TypedDict, total=False):
    # inputs
    context: dict
    query: Dict[str, Any]
    stream: bool

    # expression & per-lang scripts
    expression: str
    maxima_script: str
    python_script: str
    r_script: str

    # raw agent outputs
    maxima_results: Dict[str, Any]
    python_results: Dict[str, Any]
    r_results: Dict[str, Any]

    # reasoning
    messages: List[Dict[str, str]]
    reasoning_result: Dict[str, Any]


# ──────────── Flow entrypoint ──────────────────────────────────
def run(context=None, query=None, file_id=None, stream=False):
    state: MultiMathState = {"context": context, "query": query or {}, "stream": stream}
    builder = StateGraph(MultiMathState)

    # 1) pull "expression" out of query
    builder.add_node("prep", extract_query({"expression": "expression"}))
    builder.add_edge(START, "prep")

    # 2) normalise into three scripts
    def normalise(st):
        expr = st.get("expression", "") or ""
        yield {
            "maxima_script": f"{expr};",
            "python_script": f"print({expr.replace('^', '**')})",
            "r_script": f"print({expr})",
        }

    builder.add_node("norm", normalise)
    builder.add_edge("prep", "norm")

    # 3) fan-out to processors
    builder.add_node(
        "maxima",
        maxima_processor_node(input_key="maxima_script", output_key="maxima_results"),
    )
    builder.add_node(
        "python",
        python_processor_node(input_key="python_script", output_key="python_results"),
    )
    builder.add_node(
        "r", r_processor_node(input_key="r_script", output_key="r_results")
    )

    builder.add_edge("norm", "maxima")
    builder.add_edge("norm", "python")
    builder.add_edge("norm", "r")

    # 4) gather outputs and craft prompt
    def gather(st):
        max_out = (st.get("maxima_results", {}) or {}).get("stdout", "").strip()
        py_out = (st.get("python_results", {}) or {}).get("stdout", "").strip()
        r_out = (st.get("r_results", {}) or {}).get("stdout", "").strip()
        prompt = (
            "Here are three outputs from math processors. "
            "Do they agree, why or why not?\n\n"
            f"Maxima: {max_out}\n"
            f"Python: {py_out}\n"
            f"R: {r_out}\n"
        )
        yield {"messages": [{"role": "user", "content": prompt}]}

    builder.add_node("gather", gather)
    builder.add_edge("maxima", "gather")
    builder.add_edge("python", "gather")
    builder.add_edge("r", "gather")

    # 5) reasoning agent (streams if state["stream"] is True)
    builder.add_node(
        "reason",
        reasoning_completion_node(
            input_key_map={"messages": "messages", "stream": "stream"},
            output_key="reasoning_result",
        ),
    )
    builder.add_edge("gather", "reason")
    builder.add_edge("reason", END)

    app = builder.compile()
    yield from run_flow(app, state, stream)
