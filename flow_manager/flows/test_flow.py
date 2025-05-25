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

# flow_manager/flows/test_flow.py

from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from .nodes import livestream_control_node, test_agent_node

class TestFlowState(TypedDict, total=False):
    context: dict
    session: str
    query: dict
    stream: bool
    next_livestream_node: str

    # only this key now—no more livestream_control!
    livestream: str

    test_agent_result: dict

def run(context, session=None, query=None, stream=False):
    state = {
        "context": context,
        "session": session,
        "query": query,
        "stream": stream,
        "next_livestream_node": "test_agent",
    }

    graph = StateGraph(TestFlowState)
    graph.add_node("livestream_control", livestream_control_node)
    graph.add_node("test_agent",         test_agent_node)
    graph.add_edge(START,                "livestream_control")
    graph.add_edge("livestream_control", "test_agent")
    graph.add_edge("test_agent",         END)
    app = graph.compile()

    if stream:
        for update in app.stream(state):
            yield update
    else:
        # always yield, never return
        result = app.invoke(state)
        yield result

