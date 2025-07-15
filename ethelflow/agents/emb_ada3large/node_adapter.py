# Project Ethel
# Node adapter for ADA3large embedding, needs to be included in nodes.py
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
# agent_pool/agents/emb_ada3large/node_adapter.py
#
import requests
from typing import Callable, Iterator


def emb_ada3large_node(
    *,
    input_text_key: str = "texts",
    output_key: str = "emb_ada3large_results",
    url: str = "http://emb_ada3large:8000/",
) -> Callable[[dict], Iterator[dict]]:
    def node(state: dict) -> Iterator[dict]:
        raw = state.get(input_text_key, [])
        if not isinstance(raw, list):
            texts = []
        else:
            texts = [t if isinstance(t, str) else "" for t in raw]

        resp = requests.post(url, json={"texts": texts}, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        yield {output_key: data.get("embeddings", [])}

    return node
