# Project Ethel
# Node adapter for R processor
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
# agent_pool/agents/r_processor/node_adapter.py

import requests
from typing import Callable, Iterator

def r_processor_node(
    *,
    input_key: str = "script",
    output_key: str = "r_results",
    url: str = "http://r_agent:8000/"
) -> Callable[[dict], Iterator[dict]]:
    """
    Sends `state[input_key]` (an R script) to the R agent
    and writes the JSON response under `state[output_key]`.
    """
    def node(state: dict) -> Iterator[dict]:
        script = state.get(input_key, "")
        if not isinstance(script, str):
            script = ""
        resp = requests.post(url, json={"script": script}, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        yield {output_key: data}
    return node

