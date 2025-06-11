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
• Takes {"text": "...", "collection": "..."} in state["query"].
• Embeds the single text with Ada-3.
• Extracts the first embedding vector.
• Queries similarity search in the chosen collection.
"""

from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph
from .nodes import emb_ada3large_node, emb_similarity_ada3large_node
from .flow_helper import extract_query, linear, run_flow


# ──────────── State schema ──────────────────────────────────
class AugmentState(TypedDict, total=False):
    context: dict
    query: Dict[str, Any]
    stream: bool

    # pulled from query
    text: str
    collection: str

    # intermediate
    texts: List[str]
    emb_ada3large_result: List[List[float]]
    embedding: List[float]

    # final
    emb_similarity_ada3large_result: List[Dict[str, Any]]


# ──────────── Flow entrypoint ───────────────────────────────
def run(context=None, query=None, file_id=None, stream=False):
    state: AugmentState = {"context": context, "query": query or {}, "stream": stream}
    builder = StateGraph(AugmentState)

    # 1) pull "text" and "collection" out of query
    pull_node = extract_query({"text": "text", "collection": "collection"})

    # 2) wrap text into single-element list → state["texts"]
    def wrap(st): yield {"texts": [st.get("text", "")]}

    # 3) Ada-3 embedding → emb_ada3large_result
    embed_node = emb_ada3large_node(
        input_text_key="texts",
        output_key="emb_ada3large_result")

    # 4) take the first embedding vector
    def first_vec(st):
        batch = st.get("emb_ada3large_result", [])
        vec   = batch[0] if batch and isinstance(batch[0], list) else []
        yield {"embedding": vec}

    # 5) similarity search
    sim_node = emb_similarity_ada3large_node(
        input_key_map={"embedding": "vector", "collection": "collection"},
        output_key="emb_similarity_ada3large_result")

    # linear chain
    linear(builder, [
        ("pull", pull_node),
        ("wrap", wrap),
        ("embed", embed_node),
        ("first", first_vec),
        ("similarity", sim_node),
    ])

    app = builder.compile()
    yield from run_flow(app, state, stream)

