# Project Ethel
# A (currently) one-node flow that embeds a file from Mongo
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
# flow_manager/flows/emb_file.py

from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from .nodes import emb_file_ada3large_node
import os

class EmbFileState(TypedDict, total=False):
    # Input from the caller
    file_id: str
    stream: bool

    # Output of the emb_file_ada3large node (the JSON response from that agent)
    emb_file_ada3large_result: dict

def run(context=None, query=None, file_id=None, stream=False):
    """
    One-node flow that takes a single `file_id` (e.g. "collection/path/to/file.ext")
    and calls the emb_file_ada3large agent. Yields the final state with
    `emb_file_ada3large_result` containing the agent's JSON response.
    """
    # 1) Initialize shared state
    state: EmbFileState = {
        "file_id": file_id,
        "stream": stream
    }

    # 2) Build the graph
    builder = StateGraph(EmbFileState)

    # 3) Create the node that wraps emb_file_ada3large_agent
    emb_fn = emb_file_ada3large_node(
        input_key_map={"file_id": "file_id"},
        output_key="emb_file_ada3large_result",
        url=os.getenv("EMB_FILE_ADA3LARGE_URL", "http://emb_file_ada3large:8000/")
    )

    # 4) Register the single node and wire START → call_emb_file → END
    builder.add_node("call_emb_file", emb_fn)
    builder.add_edge(START, "call_emb_file")
    builder.add_edge("call_emb_file", END)

    # 5) Compile the graph
    app = builder.compile()

    # 6) Execute (streaming if requested, otherwise return a single dict)
    if stream:
        iterator = app.stream(state)
    else:
        iterator = iter([app.invoke(state)])

    # 7) Yield each update
    for update in iterator:
        yield update

