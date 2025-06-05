# Project Ethel
# Node adapter for semantically chunking text
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


def chunk_text_node(
    *,
    input_text_key: str = "text",     # read state["text"]
    output_key: str = "texts",       # write state["texts"]
    url: str = "http://chunk_text:8000/"
) -> Callable[[Dict[str, Any]], Iterator[Dict[str, Any]]]:
    """
    Builds a node which:
      1) Reads the string in state[input_text_key].
      2) POSTS { "text": <that_string> } to http://chunk_text:8000/.
      3) Yields { output_key: <list of chunk‐strings> }.
    """

    def node(state: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        # 1) Fetch raw text from state
        raw = state.get(input_text_key, "")
        if not isinstance(raw, str):
            text_to_chunk = ""
        else:
            text_to_chunk = raw

        # 2) Build payload and POST to the running chunk_text agent
        payload = {"text": text_to_chunk}
        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()

        data = resp.json()
        # 3) Extract the “chunks” list (or empty list if missing)
        chunks_list = data.get("chunks", [])
        if not isinstance(chunks_list, list):
            chunks_list = []

        yield {output_key: chunks_list}

    return node

