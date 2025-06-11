# Project Ethel
# A flow that embeds a file from Mongo
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
#
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph
from .nodes import (
    file_to_text_node,
    chunk_text_node,
    emb_ada3large_node,
    store_vectors_node,
)
from .flow_helper import linear, run_flow


class EmbFileState(TypedDict, total=False):
    file_id: str
    stream: bool
    text: str
    texts: List[str]
    embeddings: List[List[float]]
    store_vectors_result: Dict[str, Any]


def run(context=None, query=None, file_id=None, stream=False):
    state: EmbFileState = {"file_id": file_id, "stream": stream}
    builder = StateGraph(EmbFileState)

    # helper to peel plain text out of full ft-agent response
    def extract_text(st):
        full = st.get("text", {})
        plain = full.get("text", "") if isinstance(full, dict) else ""
        yield {"text": plain}

    nodes = [
        ("file_to_text",
         file_to_text_node(
             input_key_map={"file_id": "file_id"},
             output_key="text")),
        ("extract_text", extract_text),
        ("chunk",
         chunk_text_node(input_text_key="text", output_key="texts")),
        ("embed",
         emb_ada3large_node(input_text_key="texts", output_key="embeddings")),
        ("store",
         store_vectors_node(
             input_key_map={"file_id":"file_id","texts":"texts","embeddings":"embeddings"},
             output_key="store_vectors_result")),
    ]

    linear(builder, nodes)        # wires START→…→END
    app = builder.compile()
    yield from run_flow(app, state, stream)

