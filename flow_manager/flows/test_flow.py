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

class TestFlowState(TypedDict, total=False):
    context: dict
    query: dict
    stream: bool
    test_agent_result: dict

def run(context, query=None, stream=False):
    """
    Entry point for test_flow.
    Yields one dict per node when stream=True,
    otherwise yields just the final dict.
    """
    state = {
        "context": context,
        "query": query or {},
        "stream": stream
    }

    builder = StateGraph(TestFlowState)
    builder.add_node("test_agent", test_agent_node)
    builder.add_edge(START, "test_agent")
    builder.add_edge("test_agent", END)

    app = builder.compile()

    if stream:
        iterator = app.stream(state)
    else:
        # wrap the single result
        iterator = iter([app.invoke(state)])

    for update in iterator:
        yield update

