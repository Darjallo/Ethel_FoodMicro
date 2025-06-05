# Project Ethel
# Does ADA3large similarity checking
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
# agent_pool/agents/emb_similarity_ada3large/agent.py

import os
import traceback
from datetime import datetime
from typing import Any, Dict, List

from chromadb import Client
from chromadb.config import Settings

from agent_pool.base_agent_server import run_server
from agent_pool.base_vector_db import open_chroma_for, sharded_path


class EmbSimilarityAda3LargeAgent:
    """
    Agent that:
      1. Accepts {"collection": <str>, "vector": <list[float]>, "k": <int, optional>}.
      2. Opens the corresponding Chroma folder for that collection (sharded) via open_chroma_for().
      3. Queries “chunks” by cosine similarity against the provided embedding.
      4. Returns JSON {status, results:[{id, text, metadata, distance}, …]}.
    """

    def __init__(self):
        # Nothing to configure here beyond CHROMA_BASE_DIR if desired.
        pass

    def handle(self, request_json: Dict[str, Any]) -> Dict[str, Any]:
        response: Dict[str, Any] = {
            "id":      "emb_similarity_ada3large_response",
            "object":  "task_result",
            "created": int(datetime.utcnow().timestamp()),
        }

        # 1) Validate inputs
        collection_name = request_json.get("collection")
        embedding       = request_json.get("vector")
        k               = request_json.get("k", 10)

        if not isinstance(collection_name, str) or not collection_name:
            response.update({
                "status": 400,
                "error": "Missing or invalid 'collection' (must be a nonempty string)."
            })
            return response

        if (not isinstance(embedding, list)
            or not all(isinstance(x, (int, float)) for x in embedding)):
            response.update({
                "status": 400,
                "error": "Missing or invalid 'vector' (must be a list of floats)."
            })
            return response

        try:
            k = int(k)
            if k <= 0:
                raise ValueError()
        except Exception:
            response.update({
                "status": 400,
                "error": "Invalid 'k' (must be a positive integer)."
            })
            return response

        # 2) Open (but do NOT create) the Chroma “chunks” for this collection_name
        #    open_chroma_for will return None if the collection already exists with
        #    metadata mismatch, or if it cannot instantiate a PersistentClient.
        chroma_result = open_chroma_for(collection_name, emb_method="ada3large")
        if chroma_result is None:
            # Could not open or metadata disagreed. Determine the expected shard path:
            shard_dir = os.path.join(
                os.getenv("CHROMA_BASE_DIR", "/chroma_db"),
                sharded_path(collection_name)
            )
            response.update({
                "status": 404,
                "error": (
                    f"No valid Chroma “chunks” collection found for '{collection_name}'.\n"
                    f"Expected Chroma directory: {shard_dir}"
                ),
                "results": []
            })
            return response

        client, chr_collection = chroma_result

        # 3) Perform nearest‐neighbor cosine query
        try:
            query_result = chr_collection.query(
                query_embeddings=[embedding],
                n_results=k,
                include=["documents", "metadatas", "distances"]
            )
            ids_list       = query_result["ids"][0]
            docs_list      = query_result["documents"][0]
            metas_list     = query_result["metadatas"][0]
            distances_list = query_result["distances"][0]
        except Exception as e:
            traceback.print_exc()
            response.update({
                "status": 500,
                "error": f"Error during similarity query: {e}"
            })
            return response

        # 4) Build result array
        hits: List[Dict[str, Any]] = []
        for i in range(len(ids_list)):
            hits.append({
                "id":       ids_list[i],
                "text":     docs_list[i],
                "metadata": metas_list[i],
                "distance": distances_list[i]
            })

        # 5) Success
        response.update({
            "status": 200,
            "results": hits
        })
        return response


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    run_server(port=port, handler_instance=EmbSimilarityAda3LargeAgent())

