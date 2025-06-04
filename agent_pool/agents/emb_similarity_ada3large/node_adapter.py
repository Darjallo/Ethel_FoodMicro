# Project Ethel
# Node adapter for similarity search
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
#
import requests
from typing import Callable, Iterator, Dict, Any

def emb_similarity_ada3large_node(
    *,
    input_key_map: Dict[str, str] = {
        "collection": "collection",
        "embedding":  "embedding",
        # If you want to expose “k” in state, you can add: "k": "k"
    },
    output_key: str = "emb_similarity_ada3large_result",
    url: str = "http://emb_similarity_ada3large:8000/",
) -> Callable[[Dict[str, Any]], Iterator[Dict[str, Any]]]:
    """
    A node that:
      1) Reads state["collection"] → payload["collection"],
                 state["embedding"]  → payload["embedding"],
         optionally state["k"] → payload["k"].
      2) Posts to the similarity agent at `url` with JSON payload.
      3) Yields { output_key: <agent_response_json> }.
    """
    def node(state: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        payload: Dict[str, Any] = {}
        for state_key, payload_field in input_key_map.items():
            if state_key in state:
                payload[payload_field] = state[state_key]

        # If “k” is present in state, forward it
        if "k" in state:
            payload["k"] = state["k"]

        # Must set stream=False (this agent isn’t streaming)
        payload["stream"] = False

        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        yield {output_key: data}

    return node

