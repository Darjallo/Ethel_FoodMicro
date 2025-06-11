# flow_manager/flows/test_processors.py
from typing import TypedDict, Dict, Any
from langgraph.graph import StateGraph
from .nodes import maxima_processor_node, python_processor_node, r_processor_node
from .flow_helper import linear, run_flow


class CalcThreeState(TypedDict, total=False):
    stream: bool
    script: str
    maxima_results: Dict[str, Any]
    python_results: Dict[str, Any]
    r_results: Dict[str, Any]


def run(context=None, query=None, file_id=None, stream=False):
    state: CalcThreeState = {"stream": stream}
    builder = StateGraph(CalcThreeState)

    # helpers that YIELD a dict (must be generator)
    def set_maxima(_):  yield {"script": "6*7;"}
    def set_python(_):  yield {"script": "print(6*7)"}
    def set_r(_):       yield {"script": "print(6*7)"}

    nodes = [
        ("set_maxima",  set_maxima),
        ("maxima",
         maxima_processor_node(input_key="script", output_key="maxima_results")),
        ("set_python",  set_python),
        ("python",
         python_processor_node(input_key="script", output_key="python_results")),
        ("set_r",       set_r),
        ("r",
         r_processor_node(input_key="script", output_key="r_results")),
    ]

    linear(builder, nodes)
    app = builder.compile()
    yield from run_flow(app, state, stream)

