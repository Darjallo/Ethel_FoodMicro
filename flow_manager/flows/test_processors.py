# flow_manager/flows/calc_three_languages.py

from typing import TypedDict, Any, Dict, Iterator
from langgraph.graph import StateGraph, START, END

from .nodes import (
    maxima_processor_node,
    python_processor_node,
    r_processor_node,
)

class CalcThreeState(TypedDict, total=False):
    script: str
    maxima_results: Dict[str, Any]
    python_results: Dict[str, Any]
    r_results:      Dict[str, Any]

def run(context=None, query=None, stream=False) -> Iterator[Dict[str, Any]]:
    state: CalcThreeState = {"stream": stream}
    builder = StateGraph(CalcThreeState)

    # 1) Maxima
    builder.add_node("set_maxima", lambda s: ({"script": "6*7;"},))
    builder.add_node(
        "process_maxima",
        maxima_processor_node(
            input_key="script",
            output_key="maxima_results"
        )
    )

    # 2) Python
    builder.add_node("set_python", lambda s: ({"script": "print(6*7)"},))
    builder.add_node(
        "process_python",
        python_processor_node(
            input_key="script",
            output_key="python_results"
        )
    )

    # 3) R
    builder.add_node("set_r", lambda s: ({"script": "print(6*7)"},))
    builder.add_node(
        "process_r",
        r_processor_node(
            input_key="script",
            output_key="r_results"
        )
    )

    # wire it up
    builder.add_edge(START,            "set_maxima")
    builder.add_edge("set_maxima",     "process_maxima")
    builder.add_edge("process_maxima", "set_python")
    builder.add_edge("set_python",     "process_python")
    builder.add_edge("process_python", "set_r")
    builder.add_edge("set_r",          "process_r")
    builder.add_edge("process_r",      END)

    app = builder.compile()
    if stream:
        yield from app.stream(state)
    else:
        yield app.invoke(state)

