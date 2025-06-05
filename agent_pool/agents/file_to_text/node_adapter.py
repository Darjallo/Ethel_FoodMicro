# Project Ethel
# Node adapter to convert files to text
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

def file_to_text_node(
    *,
    input_key_map: Dict[str, str] = {"file_id": "file_id"},
    output_key: str = "file_to_text_result",
    url: str = None,
) -> Callable[[Dict[str, Any]], Iterator[Dict[str, Any]]]:
    """
    Builds a node which:
      1) Reads a key in state (default state["file_id"]) → payload["file_id"]
      2) POSTs to the file_to_text agent at `url`
      3) Yields { output_key: <response JSON> }

    By default:
      - input_key_map={"file_id":"file_id"}  (so it reads state["file_id"])
      - output_key="file_to_text_result"
      - url defaults to "http://file_to_text:8000/" (inside Docker-compose, adjust if needed)
    """
    if url is None:
        # assume a docker‐service name “file_to_text” on port 8000
        url = os.getenv("FILE_TO_TEXT_URL", "http://file_to_text:8000/")

    def node(state: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        payload: Dict[str, Any] = {}
        for state_key, payload_field in input_key_map.items():
            payload[payload_field] = state.get(state_key, "")

        # ensure no streaming parameter is sent
        payload["stream"] = False

        resp = requests.post(url, json=payload, timeout=300)
        resp.raise_for_status()
        data = resp.json()
        yield {output_key: data}

    return node

