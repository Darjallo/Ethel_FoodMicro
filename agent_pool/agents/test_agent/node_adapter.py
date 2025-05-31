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

def test_agent_node(
    *,
    input_key_map: dict[str, str] = {"context": "context", "query": "query",},
    output_key: str = "test_agent_result",
    url: str = "http://test_agent:8000/",
) -> Callable[[dict], Iterator[dict]]:
    """
    Builds a node which takes `state["context"]` and `state["query"]`, 
    sends them to http://test_agent:8000/, and yields { output_key: <resp.json()> }.
    """
    def node(state: dict) -> Iterator[dict]:
        payload = {}
        print("In test agent",flush=True)
        # copy `context` and `query` into payload
        for state_key, payload_field in input_key_map.items():
            # if missing, get default {} (or you could raise)
            payload[payload_field] = state.get(state_key, {})

        # force stream=False always
        payload["stream"] = False

        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        yield {output_key: data}

    return node

