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
from ethelflow.agents.emb_ada3large.node_adapter import emb_ada3large_node
from ethelflow.agents.emb_similarity_ada3large.node_adapter import (
    emb_similarity_ada3large_node,
)
from ethelflow.agents.file_to_text.node_adapter import file_to_text_node
from ethelflow.agents.chunk_text.node_adapter import chunk_text_node
from ethelflow.agents.store_vectors.node_adapter import store_vectors_node
from ethelflow.agents.reasoning_completion.node_adapter import reasoning_completion_node
from ethelflow.agents.maxima_processor.node_adapter import maxima_processor_node
from ethelflow.agents.python_processor.node_adapter import python_processor_node
from ethelflow.agents.r_processor.node_adapter import r_processor_node


# ... and register them
NODES = {
    "emb_ada3large": emb_ada3large_node,
    "emb_similarity_ada3large": emb_similarity_ada3large_node,
    "file_to_text": file_to_text_node,
    "chunk_text": chunk_text_node,
    "store_vectors": store_vectors_node,
    "reasoning_completion": reasoning_completion_node,
    "process_maxima": maxima_processor_node,
    "process_python": python_processor_node,
    "process_r": r_processor_node,
}
