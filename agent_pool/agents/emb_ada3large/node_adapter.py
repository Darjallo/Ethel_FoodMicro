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
import time
import requests
from typing import Callable, Iterator, Any

def emb_ada3large_node(
    *,
    input_text_key: str = "texts",               # which state‐field holds the list of strings to embed
    output_key: str = "emb_ada3large_results",   # key for the returned list of embedding vectors
    api_version: str = "2023-05-15",
) -> Callable[[dict], Iterator[dict]]:
    """
    Builds a node that:
      1) Reads the list of strings in state[input_text_key].
      2) Splits that list into batches (default batch size 10, configurable via BATCH_SIZE env var).
      3) For each batch:
           • Calls the Azure OpenAI Ada-3-large embeddings endpoint (with retries on 429).
           • Sleeps a short interval (default 2 s, configurable via BATCH_DELAY) between batches.
      4) Collects all the returned vectors into one flat list, preserving order.
      5) Yields { output_key: <list of embedding vectors> } once at the end.

    Environment variables:
      - AZURE_ENDPOINT
      - AZURE_KEY
      - AZURE_ADA3LARGE_DEPLOYMENT
      - BATCH_SIZE (optional, defaults to 10)
      - BATCH_DELAY (optional, seconds between batches, defaults to 2)
    """
    endpoint   = os.environ["AZURE_ENDPOINT"]
    api_key    = os.environ["AZURE_KEY"]
    deployment = os.environ["AZURE_ADA3LARGE_DEPLOYMENT"]
    url = f"{endpoint}/openai/deployments/{deployment}/embeddings?api-version={api_version}"

    headers = {
        "Content-Type": "application/json",
        "api-key": api_key,
    }

    # Batch tuning via env, with sensible defaults
    try:
        BATCH_SIZE = int(os.getenv("BATCH_SIZE", "10"))
    except ValueError:
        BATCH_SIZE = 10

    try:
        BATCH_DELAY = float(os.getenv("BATCH_DELAY", "2"))
    except ValueError:
        BATCH_DELAY = 2.0

    def embed_batch(texts: list[str]) -> list[list[float]]:
        """
        Send a single batch of texts to Azure embeddings with retry-on-429.
        Returns a list of embedding vectors in the same order as `texts`.
        """
        max_retries = 5
        backoff = 1
        for attempt in range(max_retries):
            try:
                payload = {"input": texts}
                resp = requests.post(url, json=payload, headers=headers, timeout=60)
                if resp.status_code == 429:
                    # Rate‐limited: wait & retry
                    time.sleep(backoff)
                    backoff *= 2
                    continue

                resp.raise_for_status()
                data = resp.json()
                # Azure returns data["data"] = [ { "embedding": [...], ... }, ... ]
                embeddings = [item["embedding"] for item in data["data"]]
                return embeddings

            except requests.exceptions.HTTPError as http_err:
                if resp.status_code == 429:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                else:
                    raise RuntimeError(f"HTTP error during embedding batch: {http_err} (status {resp.status_code})")
            except Exception as exc:
                raise RuntimeError(f"Error calling embedding endpoint: {exc}")

        raise RuntimeError("Exceeded max retries for embedding batch (rate‐limited)")

    def node(state: dict) -> Iterator[dict]:
        # 1) Fetch the raw list of texts from state
        raw = state.get(input_text_key, [])
        if not isinstance(raw, list):
            # If user passed something else, coerce to empty‐list
            texts_to_embed: list[str] = []
        else:
            # Ensure each element is a string; non‐strings become ""
            texts_to_embed = [t if isinstance(t, str) else "" for t in raw]

        all_embeddings: list[list[float]] = []
        n_texts = len(texts_to_embed)

        # 2) Process in sub‐batches of size BATCH_SIZE
        for i in range(0, n_texts, BATCH_SIZE):
            batch = texts_to_embed[i : i + BATCH_SIZE]
            # 2a) Embed the current batch (with retry‐logic)
            try:
                batch_embeds = embed_batch(batch)
            except Exception as exc:
                # If a batch fails completely, raise, since partial results are not helpful.
                raise

            all_embeddings.extend(batch_embeds)

            # 2b) If there are more batches to go, sleep a bit
            if i + BATCH_SIZE < n_texts:
                time.sleep(BATCH_DELAY)

        # 3) Yield once with the complete list of embedding vectors
        yield {output_key: all_embeddings}

    return node

