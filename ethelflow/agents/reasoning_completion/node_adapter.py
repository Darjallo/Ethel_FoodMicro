# Project Ethel
# Node adapter for reasoning chat completion
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


def reasoning_completion_node(
    *,
    input_key_map: Dict[str, str] = {
        "messages": "messages",  # maps state["messages"] → payload["messages"]
        "schema": "schema",  # optional
        "reasoning_effort": "reasoning_effort",  # optional
        "file_ids": "file_ids",  # optional list[str]
        "tenant": "tenant",
        "stream": "stream",  # optional boolean
    },
    output_key: str = "reasoning_completion_result",
    url: str = "http://reasoning_completion:8000/",
) -> Callable[[Dict[str, Any]], Iterator[Dict[str, Any]]]:
    """
    Builds a node that:
      1) Reads state[*] according to input_key_map, composing payload.
      2) POSTs to http://reasoning_completion:8000/ with that payload.
      3) If state.get("stream") is True, it streams back each JSON chunk and yields
         { output_key: <that_chunk> } per line. Otherwise it does one POST and yields
         { output_key: <full_response> }.
    """

    def node(state: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        # 1) Build payload by copying each mapped key from state
        payload: Dict[str, Any] = {}
        for state_key, payload_field in input_key_map.items():
            if state_key in state:
                payload[payload_field] = state.get(state_key)

        # Ensure "stream" is explicitly a boolean
        payload["stream"] = bool(state.get("stream", False))

        # 2) Fire the request
        if payload["stream"]:
            # streaming mode
            resp = requests.post(url, json=payload, timeout=600, stream=True)
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                text = line.decode() if isinstance(line, bytes) else line
                try:
                    obj = requests.utils.json.loads(text)
                except Exception:
                    continue
                yield {output_key: obj}
        else:
            # non-streaming: do one POST → full JSON
            resp = requests.post(url, json=payload, timeout=600)
            resp.raise_for_status()
            data = resp.json()
            yield {output_key: data}

    return node
