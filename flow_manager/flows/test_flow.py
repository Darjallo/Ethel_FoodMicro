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
from .nodes import test_agent_node, livestream_control_node

class TestFlowState(TypedDict, total=False):
    context: dict
    session: str
    query: dict
    stream: bool
    livestream: str
    test_agent_result: dict

def run(context, session=None, query=None, stream=False):
    state = {
        "context": context,
        "session": session,
        "query": query,
        "stream": stream,
        "next_livestream_node": "test_agent"  # explicitly indicate streaming node
    }

    graph_builder = StateGraph(TestFlowState)
    graph_builder.add_node("livestream_control", livestream_control_node)
    graph_builder.add_node("test_agent", test_agent_node)
    graph_builder.add_edge(START, "livestream_control")
    graph_builder.add_edge("livestream_control", "test_agent")
    graph_builder.add_edge("test_agent", END)
    app = graph_builder.compile()

    if stream:
        for update in app.stream(state):
            yield update
    else:
        result_state = app.invoke(state)
        yield result_state

