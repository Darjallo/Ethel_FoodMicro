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
# Make sure to import all new agents:
from agent_pool.agents.test_agent.node_adapter import test_agent_node
from agent_pool.agents.emb_ada3large.node_adapter import emb_ada3large_node
from agent_pool.agents.emb_file_ada3large.node_adapter import emb_file_ada3large_node

# ... and register them
NODES = {
    "test_agent": test_agent_node,
    "emb_ada3large": emb_ada3large_node,
    "emb_file_ada3large" : emb_file_ada3large_node
}

