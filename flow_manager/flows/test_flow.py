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
from .nodes import test_agent_node

class TestFlowState(TypedDict, total=False):
    context: dict
    session: str
    query: dict
    stream: bool
    # the node’s final JSON result goes here
    test_agent_result: dict

def run(context, session=None, query=None, stream=False):
    """
    Entry point for the test_flow.
    Always yields dicts, streaming if requested.
    """
    state = {
        "context": context,
        "session": session,
        "query": query,
        "stream": stream
    }

    builder = StateGraph(TestFlowState)
    builder.add_node("test_agent", test_agent_node)
    builder.add_edge(START, "test_agent")
    builder.add_edge("test_agent", END)

    app = builder.compile()

    # choose streaming vs. non-streaming
    if stream:
        iterator = app.stream(state)
    else:
        # wrap the single final result in a list so we can for-loop uniformly
        iterator = iter([app.invoke(state)])

    for update in iterator:
        yield update

