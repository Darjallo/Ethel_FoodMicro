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
import requests
from typing import Callable, Iterator, Dict, Any

def emb_similarity_ada3large_node(
    *,
    input_key_map: Dict[str, str] = {
        "tenant":     "tenant",     # NEW
        "collection": "collection",
        "embedding":  "vector",
        # Optionally expose "k": "k"
    },
    output_key: str = "emb_similarity_ada3large_result",
    url: str = "http://emb_similarity_ada3large:8000/",
) -> Callable[[Dict[str, Any]], Iterator[Dict[str, Any]]]:
    """
    Reads tenant / collection / embedding (and optional k) from state,
    POSTs to the similarity agent, and yields the agent's JSON.
    """
    def node(state: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        payload: Dict[str, Any] = {}

        for state_key, payload_field in input_key_map.items():
            if state_key not in state:
                raise KeyError(f"state['{state_key}'] missing for similarity node")
            payload[payload_field] = state[state_key]

        if "k" in state:
            payload["k"] = state["k"]

        payload["stream"] = False
        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        yield {output_key: resp.json()}

    return node

