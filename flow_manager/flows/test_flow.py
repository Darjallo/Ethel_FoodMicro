# Project Ethel
# A test flow, can serve as template
#
# Copyright (C) 2025  Gerd Kortemeyer, ETH Zurich
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from .nodes import test_agent_node

# Define the state schema using TypedDict
class TestFlowState(TypedDict):
    context: dict
    session: str
    query: dict
    stream: bool
    test_agent_result: dict

def run(context, session=None, query=None, stream=False):
    """
    Entry point for the test_flow.
    context, session, query: user data
    stream: if True, yields updates as they are produced by the agent node.
    """
    print("run called with stream =", stream, flush=True)

    state = {
        "context": context,
        "session": session,
        "query": query,
        "stream": stream
    }
    print("Initial state:", state, flush=True)
    graph_builder = StateGraph(TestFlowState)
    graph_builder.add_node("test_agent", test_agent_node)
    graph_builder.add_edge(START, "test_agent")
    graph_builder.add_edge("test_agent", END)
    app = graph_builder.compile()

    if stream:
        # Yield each partial update (as dicts) from the LangGraph app's stream method
        print("We are streaming", flush=True)
        for update in app.stream(state):
            yield update  # this will be a dict with "test_agent_result": ...
    else:
        # Even in non-streaming mode, always yield (never return)
        result_state = app.invoke(state)
        print("Result state:", result_state, flush=True)
        yield result_state.get("test_agent_result")

