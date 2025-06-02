# Project Ethel
# Node adapter for test echo agent, needs to be included in nodes.py
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
# node_adapter.py

import os
import requests
from typing import Callable, Iterator

def emb_file_ada3large_node(
    *,
    input_key_map: dict[str, str] = {"file_id": "file_id"},
    output_key: str = "emb_file_ada3large_result",
    url: str = "http://emb_file_ada3large:8000/",
) -> Callable[[dict], Iterator[dict]]:
    """
    Builds a node which takes `state["file_id"]`, sends it to the
    emb_file_ada3large agent at `url`, and yields { output_key: <resp.json()> }.

    By default:
      - It reads `state["file_id"]` and maps it to payload["file_id"].
      - It posts to http://emb_file_ada3large:8000/ with {"file_id": ...}.
      - It returns the full JSON response under state[output_key].
    """
    def node(state: dict) -> Iterator[dict]:
        payload: dict = {}
        # Copy each mapped key from state into payload
        for state_key, payload_field in input_key_map.items():
            payload[payload_field] = state.get(state_key, "")

        # Ensure no streaming parameter is sent
        payload["stream"] = False

        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        yield {output_key: data}

    return node

