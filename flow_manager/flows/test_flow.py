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
from langgraph.graph import StateGraph
from .nodes import test_agent_node

def run(context, session=None, query=None, stream=False):
    """
    Entry point for the test_flow.
    context, session, query: user data
    stream: if True, expects agent to stream (but here just calls node)
    """
    # Prepare the initial state for the flow
    state = {
        "context": context,
        "session": session,
        "query": query,
        "stream": stream
    }

    # Build the graph
    graph = StateGraph()
    # Register the node
    graph.add_node("test_agent", test_agent_node)
    # Add edges (here, only one node, so just entry)
    graph.set_entry_point("test_agent")
    # Run the flow
    result_state = graph.run(state)
    # Return the result produced by the node (what agent returned)
    return result_state.get("test_agent_result")

