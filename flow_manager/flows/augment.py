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

# import the two node‐adapters we need:
from .nodes import emb_ada3large_node, emb_similarity_ada3large_node


class AugmentState(TypedDict, total=False):
    # Inputs from the Flow Manager:
    context: dict
    query: dict       # expecting {"text": str, "collection": str}
    stream: bool

    # Transient fields we’ll build:
    text: str
    collection: str
    embedding: list[float]

    # Intermediate + final outputs:
    emb_ada3large_result: list[float]
    emb_similarity_ada3large_result: list[dict]

def run(context=None, query=None, file_id=None, stream=False):
    """
    1) Pull “text” and “collection” out of state["query"].
    2) Embed the text via emb_ada3large.
    3) Do similarity lookup in Chroma using emb_similarity_ada3large.
    """
    state: AugmentState = {
        "context": context,
        "query": query or {},
        "stream": stream,
    }

    builder = StateGraph(AugmentState)

    # ─── Node #1 ───
    # Extract “text” and “collection” from state["query"] into top‐level keys.
    def prep_node(state_dict: dict):
        q = state_dict.get("query", {}) or {}
        text = ""
        coll = ""
        if isinstance(q, dict):
            text = q.get("text", "") or ""
            coll = q.get("collection", "") or ""
        yield {"text": text, "collection": coll}

    # ─── Node #2 ───
    # Call Azure Ada3 to embed the “text” string.  Puts its result under “emb_ada3large_result”.
    emb_node = emb_ada3large_node(
        input_text_key="text",                 # read state["text"]
        output_key="emb_ada3large_result"      # write state["emb_ada3large_result"]
    )

    # ─── Node #3 ───
    # Rename “emb_ada3large_result” → “embedding” for the next node.
    def rename_emb(state_dict: dict):
        vec = state_dict.get("emb_ada3large_result", [])
        yield {"embedding": vec}

    # ─── Node #4 ───
    # Call our emb_similarity_ada3large agent, passing “vector” + “collection”
    sim_node = emb_similarity_ada3large_node(
        input_key_map={"embedding": "vector", "collection": "collection"},
        output_key="emb_similarity_ada3large_result"
    )

    # ─── Wire it all up ───
    builder.add_node("prep", prep_node)
    builder.add_node("embed", emb_node)
    builder.add_node("rename", rename_emb)
    builder.add_node("similarity", sim_node)

    builder.add_edge(START, "prep")
    builder.add_edge("prep", "embed")
    builder.add_edge("embed", "rename")
    builder.add_edge("rename", "similarity")
    builder.add_edge("similarity", END)

    app = builder.compile()

    if state.get("stream"):
        iterator = app.stream(state)
    else:
        iterator = iter([app.invoke(state)])

    for update in iterator:
        yield update

