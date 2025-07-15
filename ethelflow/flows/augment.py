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
# flow_manager/flows/augment.py
"""
augment
=======
• Takes {"text": "...", "tenant": "...", "collection": "..."} in state["query"].
• Embeds the single text with Ada-3.
• Extracts the first embedding vector.
• Queries similarity search in the chosen collection.
"""

from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph
from .flow_helper import extract_query, linear, run_flow
from ethelflow.agents.emb_ada3large.node_adapter import emb_ada3large_node
from ethelflow.agents.emb_similarity_ada3large.node_adapter import (
    emb_similarity_ada3large_node,
)


class AugmentState(TypedDict, total=False):
    context: dict
    query: Dict[str, Any]
    stream: bool
    tenant: str  # NEW

    text: str
    collection: str

    texts: List[str]
    emb_ada3large_result: List[List[float]]
    embedding: List[float]
    emb_similarity_ada3large_result: List[Dict[str, Any]]


def run(context=None, query=None, file_id=None, stream=False):
    tenant = (context or {}).get("tenant")
    if not tenant:
        raise ValueError("Missing tenant in context")

    state: AugmentState = {
        "context": context,
        "query": query or {},
        "tenant": tenant,
        "stream": stream,
    }
    builder = StateGraph(AugmentState)

    pull_node = extract_query({"text": "text", "collection": "collection"})
    wrap = lambda st: (yield {"texts": [st.get("text", "")]})

    embed_node = emb_ada3large_node(
        input_text_key="texts", output_key="emb_ada3large_result"
    )

    def first_vec(st):
        vecs = st.get("emb_ada3large_result", [])
        yield {"embedding": vecs[0] if vecs else []}

    sim_node = emb_similarity_ada3large_node(
        input_key_map={
            "tenant": "tenant",
            "collection": "collection",
            "embedding": "vector",
        },
        output_key="emb_similarity_ada3large_result",
    )

    linear(
        builder,
        [
            ("pull", pull_node),
            ("wrap", wrap),
            ("embed", embed_node),
            ("first", first_vec),
            ("sim", sim_node),
        ],
    )
    app = builder.compile()
    yield from run_flow(app, state, stream)
