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

from typing import TypedDict
from langgraph.graph import StateGraph, START, END

# import the (updated) two node‐adapters we need:
from .nodes import emb_ada3large_node, emb_similarity_ada3large_node


class AugmentState(TypedDict, total=False):
    # Inputs from the Flow Manager
    context: dict
    query: dict       # expecting {"text": str, "collection": str}
    stream: bool

    # Transient fields we'll build:
    texts: list[str]       # one‐element list containing the single "text" to embed
    collection: str
    embedding: list[float]

    # Intermediate + final outputs:
    emb_ada3large_result: list[list[float]]         # a list of embedding‐vectors (batch output)
    emb_similarity_ada3large_result: list[dict]     # final list of similarity hits


def run(context=None, query=None, file_id=None, stream=False):
    """
    1) Pull “text” and “collection” out of state["query"].
    2) Wrap “text” into a one‐element list ["text"] and call emb_ada3large_node.
       That node now returns a list of vectors (one per input string).
    3) Extract the single embedding (first element of that list) into state["embedding"].
    4) Call emb_similarity_ada3large_node with {"vector": embedding, "collection": collection}.
    """

    state: AugmentState = {
        "context": context,
        "query": query or {},
        "stream": stream,
    }

    builder = StateGraph(AugmentState)

    # ─── Node #1 ───
    # Extract “text” and “collection” from state["query"], wrap text into a one‐element list.
    def prep_node(state_dict: dict):
        q = state_dict.get("query", {}) or {}
        text = ""
        coll = ""
        if isinstance(q, dict):
            text = q.get("text", "") or ""
            coll = q.get("collection", "") or ""
        # put "texts" as a list (even if empty string) so that emb_ada3large_node sees it as batch
        yield {"texts": [text], "collection": coll}

    # ─── Node #2 ───
    # Call Azure Ada3 to embed the “texts” list.  Puts its result under “emb_ada3large_result”.
    emb_node = emb_ada3large_node(
        input_text_key="texts",                 # read state["texts"] (a list of strings)
        output_key="emb_ada3large_result"       # write state["emb_ada3large_result"] (a list of vectors)
    )

    # ─── Node #3 ───
    # Extract the first (and only) vector from emb_ada3large_result → put into "embedding"
    def unpack_vector(state_dict: dict):
        batch_embeds = state_dict.get("emb_ada3large_result", [])
        single_vec: list[float] = []
        if isinstance(batch_embeds, list) and len(batch_embeds) > 0:
            single_list = batch_embeds[0]
            if isinstance(single_list, list):
                single_vec = single_list
        yield {"embedding": single_vec}

    # ─── Node #4 ───
    # Call our emb_similarity_ada3large agent, passing {"vector": <embedding>, "collection": <collection>}
    sim_node = emb_similarity_ada3large_node(
        input_key_map={"embedding": "vector", "collection": "collection"},
        output_key="emb_similarity_ada3large_result"
    )

    # ─── Wire everything up ───
    builder.add_node("prep", prep_node)
    builder.add_node("embed", emb_node)
    builder.add_node("unpack", unpack_vector)
    builder.add_node("similarity", sim_node)

    builder.add_edge(START, "prep")
    builder.add_edge("prep", "embed")
    builder.add_edge("embed", "unpack")
    builder.add_edge("unpack", "similarity")
    builder.add_edge("similarity", END)

    app = builder.compile()

    if state.get("stream"):
        iterator = app.stream(state)
    else:
        iterator = iter([app.invoke(state)])

    for update in iterator:
        yield update

