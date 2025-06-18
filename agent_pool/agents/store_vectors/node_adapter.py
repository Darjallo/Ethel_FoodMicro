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
import requests
from typing import Callable, Iterator, Dict, Any

def store_vectors_node(
    *,
    input_key_map: Dict[str, str] = {
        "tenant":     "tenant",      # NEW
        "file_id":    "file_id",
        "texts":      "texts",
        "embeddings": "embeddings"
    },
    output_key: str = "store_vectors_result",
    url: str = "http://store_vectors:8000/",
) -> Callable[[dict], Iterator[dict]]:
    """
    Sends tenant, file_id, texts, embeddings to the store_vectors agent.
    """
    def node(state: dict) -> Iterator[dict]:
        payload: Dict[str, Any] = {}
        for state_key, payload_field in input_key_map.items():
            if state_key not in state:
                raise KeyError(f"state['{state_key}'] missing for store_vectors_node")
            payload[payload_field] = state[state_key]

        payload["stream"] = False
        resp = requests.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        yield {output_key: resp.json()}

    return node

