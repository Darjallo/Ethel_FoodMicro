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

import os
import requests
from typing import Callable, Iterator

def emb_ada3large_node(
    *,
    input_text_key: str = "text",              # which state‐field holds the string to embed
    output_key: str = "emb_ada3large_result",  # name to use for the returned embedding vector
    api_version: str = "2023-05-15",
) -> Callable[[dict], Iterator[dict]]:
    """
    Builds a node that:
      1) Reads the string in state[input_text_key]
      2) Calls the Azure OpenAI Ada-3-large embeddings endpoint
      3) Yields { output_key: <embedding_vector> }.

    The state must contain a plain string under input_text_key. If that key is
    missing or not a string, we default to "" (empty).
    """
    endpoint   = os.environ["AZURE_ENDPOINT"]
    api_key    = os.environ["AZURE_KEY"]
    deployment = os.environ["AZURE_ADA3LARGE_DEPLOYMENT"]
    url = f"{endpoint}/openai/deployments/{deployment}/embeddings?api-version={api_version}"

    headers = {
        "Content-Type": "application/json",
        "api-key": api_key,
    }

    def node(state: dict) -> Iterator[dict]:
        # 1) Fetch the raw value from state
        raw = state.get(input_text_key, "")
        if not isinstance(raw, str):
            text_to_embed = ""
        else:
            text_to_embed = raw

        # 2) Build payload (must be a string or list-of-strings)
        payload = {"input": text_to_embed}

        # 3) Call Azure
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()

        data = resp.json()
        # 4) Extract the embedding vector
        embedding_vector = data["data"][0]["embedding"]

        yield {output_key: embedding_vector}

    return node

