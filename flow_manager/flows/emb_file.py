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
# flow_manager/flows/emb_flow.py

from typing import TypedDict, Any, Dict
from langgraph.graph import StateGraph, START, END

from .nodes import (
    file_to_text_node,
    chunk_text_node,
    emb_ada3large_node,
    store_vectors_node,
)


class EmbFileState(TypedDict, total=False):
    # Inputs
    file_id: str
    stream: bool

    # Intermediate values
    text: str               # plain string after extracting from the ft‐agent response
    texts: list[str]        # list of chunk‐strings
    embeddings: list[list[float]]

    # Final output
    store_vectors_result: Dict[str, Any]


def run(context=None, query=None, file_id=None, stream=False):
    """
    1) file_to_text_node: file_id → full response under state["text"]
    2) extract_text_node: pull out state["text"]["text"] → rewrite under state["text"] as a str
    3) chunk_text_node: splits that string into state["texts"]
    4) emb_ada3large_node: batch‐embed state["texts"] → state["embeddings"]
    5) store_vectors_node: write {file_id, texts, embeddings} → state["store_vectors_result"]
    """

    state: EmbFileState = {
        "file_id": file_id,
        "stream":  stream,
    }

    builder = StateGraph(EmbFileState)

    # ─── Node #1: file_to_text_node ───
    ft_node = file_to_text_node(
        input_key_map={"file_id": "file_id"},
        output_key="text",   # for now this is a dict: {id, object, status, text: "<big string>"}
    )

    # ─── Node #2: extract_text_node ───
    def extract_text_node(state_dict: dict) -> dict:
        full_resp = state_dict.get("text", {})
        if isinstance(full_resp, dict):
            inner = full_resp.get("text", "")
            if not isinstance(inner, str):
                inner = ""
        else:
            inner = ""
        yield {"text": inner}

    # ─── Node #3: chunk_text_node ───
    ct_node = chunk_text_node(
        input_text_key="text",   # expects a plain string here
        output_key="texts",      # now emits state["texts"] = List[str]
    )

    # ─── Node #4: emb_ada3large_node ───
    emb_node = emb_ada3large_node(
        input_text_key="texts",    # read the list of chunk‐strings
        output_key="embeddings",   # write the list of embedding‐vectors
    )

    # ─── Node #5: store_vectors_node ───
    sv_node = store_vectors_node(
        input_key_map={
            "file_id":    "file_id",
            "texts":      "texts",
            "embeddings": "embeddings",
        },
        output_key="store_vectors_result",
    )

    # ─── Register nodes ───
    builder.add_node("file_to_text",   ft_node)
    builder.add_node("extract_text",   extract_text_node)
    builder.add_node("chunk_text",     ct_node)
    builder.add_node("embed",          emb_node)
    builder.add_node("store",          sv_node)

    # ─── Wire up execution ───
    builder.add_edge(START,           "file_to_text")
    builder.add_edge("file_to_text",  "extract_text")
    builder.add_edge("extract_text",  "chunk_text")
    builder.add_edge("chunk_text",    "embed")
    builder.add_edge("embed",         "store")
    builder.add_edge("store",         END)

    app = builder.compile()

    if state.get("stream"):
        for update in app.stream(state):
            print("=== Update ===")
            print(update)
            print()
            yield update
    else:
        result = app.invoke(state)
        print("=== Final ===")
        print(result)
        yield result

