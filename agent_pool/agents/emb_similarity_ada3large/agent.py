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
import os
import traceback
from datetime import datetime
from typing import Any, Dict, List

from chromadb import Client
from chromadb.config import Settings

from agent_pool.base_agent_server import run_server
from agent_pool.base_vector_db import sharded_path


class EmbSimilarityAda3LargeAgent:
    """
    Agent that:
      1. Accepts {"collection": <str>, "vector": <list[float]>, "k": <int, optional>}.
      2. Opens the corresponding Chroma folder for that collection (sharded).
      3. Queries “chunks” by cosine similarity against the provided embedding (Ada-3-large).
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
                "error": "Missing or invalid 'collection' (must be nonempty string)."
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

        # 2) Compute sharded directory path
        base_dir = os.getenv("CHROMA_BASE_DIR", "/chroma_db")
        folder   = os.path.join(base_dir, sharded_path(collection_name))

        # 2a) If the folder itself does not exist on disk, return a 404 variant
        if not os.path.isdir(folder):
            response.update({
                "status": 404,
                "error": (
                    f"Collection folder not found on disk: '{collection_name}'.\n"
                    f"Expected directory at: {folder}"
                ),
                "results": []
            })
            return response

        # 3) Instantiate Chroma client
        try:
            client = Client(
                settings=Settings(
                    persist_directory=folder,
                    anonymized_telemetry=False
                )
            )
        except Exception as e:
            # If Chroma can’t open the folder (e.g. missing DB file inside, permissions, etc.)
            traceback.print_exc()
            response.update({
                "status": 404,
                "error": (
                    f"Could not open Chroma database at '{folder}'.\n"
                    f"Reason: {e}"
                ),
                "results": []
            })
            return response

        # 4) Verify “chunks” collection exists
        try:
            resp = client.list_collections()
            if isinstance(resp, dict) and "collections" in resp:
                existing_names = [c["name"] for c in resp["collections"]]
            else:
                # Older versions returned a simple list of dicts
                existing_names = [c["name"] for c in resp]  # type: ignore
        except Exception as e:
            traceback.print_exc()
            response.update({
                "status": 500,
                "error": f"Error listing Chroma collections in '{folder}': {e}"
            })
            return response

        if "chunks" not in existing_names:
            # Chroma client opened, but no “chunks” inside
            response.update({
                "status": 404,
                "error": (
                    f"No ‘chunks’ collection found for '{collection_name}'.\n"
                    f"Chroma directory: {folder}"
                ),
                "results": []
            })
            return response

        # 5) Open the “chunks” collection
        try:
            chr_collection = client.get_collection("chunks")
        except Exception as e:
            traceback.print_exc()
            response.update({
                "status": 500,
                "error": f"Error opening Chroma collection 'chunks' in '{folder}': {e}"
            })
            return response

        # 6) Perform nearest‐neighbor query (cosine) on the single embedding
        try:
            query_result = chr_collection.query(
                query_embeddings=[embedding],
                n_results=k,
                include=["ids", "documents", "metadatas", "distances"]
            )
            # Each field is a list‐of‐lists. We only passed one query embedding, so index 0:
            ids_list        = query_result["ids"][0]
            docs_list       = query_result["documents"][0]
            metas_list      = query_result["metadatas"][0]
            distances_list  = query_result["distances"][0]
        except Exception as e:
            traceback.print_exc()
            response.update({
                "status": 500,
                "error": f"Error during similarity query on '{collection_name}': {e}"
            })
            return response

        # 7) Build result array
        hits: List[Dict[str, Any]] = []
        for i in range(len(ids_list)):
            hits.append({
                "id":       ids_list[i],
                "text":     docs_list[i],
                "metadata": metas_list[i],
                "distance": distances_list[i]
            })

        # 8) Success
        response.update({
            "status": 200,
            "results": hits
        })
        return response


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    run_server(port=port, handler_instance=EmbSimilarityAda3LargeAgent())

