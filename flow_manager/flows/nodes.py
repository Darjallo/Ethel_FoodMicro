# Project Ethel
# List of nodes
# Needs to be extended for each new agent
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
#
# flow_manager/flows/nodes.py

from agent_pool.agents.test_agent.node_adapter import test_agent_node

def livestream_control_node(state):
    # Tell the flow‐manager: open side‐channel for the next node
    next_node = state.get("next_livestream_node")
    return {"livestream": next_node}

NODES = {
    "livestream_control": livestream_control_node,
    "test_agent": test_agent_node,
}

