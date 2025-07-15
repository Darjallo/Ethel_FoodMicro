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
# flow_manager/flows/emb_file.py
#
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph
from ethelflow.agents.emb_ada3large.node_adapter import emb_ada3large_node
from ethelflow.agents.store_vectors.node_adapter import store_vectors_node
from ethelflow.agents.chunk_text.node_adapter import chunk_text_node
from ethelflow.agents.file_to_text.node_adapter import file_to_text_node
from ethelflow.flows.flow_helper import linear, run_flow


class EmbFileState(TypedDict, total=False):
    tenant: str
    file_id: str
    stream: bool
    text: str
    texts: List[str]
    embeddings: List[List[float]]
    store_vectors_result: Dict[str, Any]


def run(context=None, query=None, file_id=None, stream=False):
    # 1) extract tenant from the incoming context
    tenant = context.get("tenant")
    if not tenant:
        raise ValueError("Missing tenant in context")

    # 2) initialize state with tenant + file_id + stream flag
    state: EmbFileState = {"tenant": tenant, "file_id": file_id, "stream": stream}
    builder = StateGraph(EmbFileState)

    # helper to peel plain text out of full file_to_text response
    def extract_text(st):
        full = st.get("text", {})
        plain = full.get("text", "") if isinstance(full, dict) else ""
        yield {"text": plain}

    nodes = [
        # file_to_text now knows both tenant and file_id
        (
            "file_to_text",
            file_to_text_node(
                input_key_map={"tenant": "tenant", "file_id": "file_id"},
                output_key="text",
            ),
        ),
        ("extract_text", extract_text),
        ("chunk", chunk_text_node(input_text_key="text", output_key="texts")),
        ("embed", emb_ada3large_node(input_text_key="texts", output_key="embeddings")),
        # store_vectors also needs tenant so it writes under the right namespace
        (
            "store",
            store_vectors_node(
                input_key_map={
                    "tenant": "tenant",
                    "file_id": "file_id",
                    "texts": "texts",
                    "embeddings": "embeddings",
                },
                output_key="store_vectors_result",
            ),
        ),
    ]

    # wire them up and run
    linear(builder, nodes)
    app = builder.compile()
    yield from run_flow(app, state, stream)
