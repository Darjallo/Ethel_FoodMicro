# Project Ethel
# Node adapter for storing the embeddings
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
import os
import requests
from typing import Callable, Iterator, Dict, Any

def store_vectors_node(
    *,
    input_key_map: Dict[str, str] = {
        "file_id":   "file_id",
        "texts":     "texts",
        "embeddings": "embeddings"
    },
    output_key: str = "store_vectors_result",
    url: str = "http://store_vectors:8000/",
) -> Callable[[dict], Iterator[dict]]:
    """
    Builds a node which:
      1) Reads `state["file_id"]`, `state["texts"]`, and `state["embeddings"]`.
      2) Posts them (JSON) to the store_vectors agent at `url`.
      3) Yields { output_key: <resp.json()> }.

    By default:
      - It reads `state["file_id"]` → payload["file_id"],
                 `state["texts"]`   → payload["texts"],
                 `state["embeddings"]` → payload["embeddings"].
      - It posts to http://store_vectors:8000/ with that JSON.
      - It returns the full JSON under state[output_key].
    """
    def node(state: dict) -> Iterator[dict]:
        payload: Dict[str, Any] = {}
        # Copy each mapped key from state into payload
        for state_key, payload_field in input_key_map.items():
            payload[payload_field] = state.get(state_key, None)

        # We do not allow streaming in this node
        payload["stream"] = False

        resp = requests.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        yield {output_key: data}

    return node

