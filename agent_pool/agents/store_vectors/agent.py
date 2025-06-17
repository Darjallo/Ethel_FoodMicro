# Project Ethel
# Agent storing embeddings in the vector database
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
from typing import Any, Dict, List, Optional, Tuple

from chromadb import PersistentClient
from chromadb.config import Settings

from agent_pool.base_agent_server import run_server
from agent_pool.base_vector_db import open_chroma_for


class StoreVectorsAgent:
    """
    Agent that:
      1. Accepts {"file_id": <str>, "texts": <list[str]>, "embeddings": <list[list[float]>>}.
      2. Splits file_id into collection_name and file_path.
      3. Uses open_chroma_for(...) to open (or create) a Chroma “default” collection
         inside the proper shard folder.
      4. Deletes any existing vectors whose metadata["path"] == file_path.
      5. Inserts new vectors (ids, embeddings, metadatas, documents).
      6. Persists Chroma to disk.
      7. Returns a JSON response with status/message or error.
    """

    def __init__(self):
        # Nothing to configure here beyond CHROMA_BASE_DIR, which open_chroma_for reads.
        pass

    def handle(self, request_json: Dict[str, Any]) -> Dict[str, Any]:
        response: Dict[str, Any] = {
            "id":      "store_vectors_response",
            "object":  "task_result",
            "created": int(datetime.utcnow().timestamp()),
        }

        # 1) Validate inputs
        file_id    = request_json.get("file_id")
        texts      = request_json.get("texts")
        embeddings = request_json.get("embeddings")

        if not (isinstance(file_id, str) and file_id and "/" in file_id):
            response.update({
                "status": 400,
                "error": "Missing or invalid 'file_id' (must be 'collection/path/to/file.ext')."
            })
            return response

        if not (isinstance(texts, list) and all(isinstance(t, str) for t in texts)):
            response.update({
                "status": 400,
                "error": "Missing or invalid 'texts' (must be a list of strings)."
            })
            return response

        if not (isinstance(embeddings, list) and all(isinstance(v, list) for v in embeddings)):
            response.update({
                "status": 400,
                "error": "Missing or invalid 'embeddings' (must be a list of float‐lists)."
            })
            return response

        if len(texts) != len(embeddings):
            response.update({
                "status": 400,
                "error": "Length mismatch: 'texts' and 'embeddings' must have the same length."
            })
            return response

        # 2) Split file_id into tenant, collection_name and file_path
        tenant,collection_name, file_path = file_id.split("/", 2)

        # 3) Open (or create) the Chroma “default” collection via open_chroma_for(...)
        chroma_result: Optional[Tuple[PersistentClient, Any]] = open_chroma_for(
            tenant,collection_name, emb_method="ada3large"
        )
        if chroma_result is None:
            response.update({
                "status": 400,
                "error": (
                    f"Chroma shard for collection '{collection_name}' exists but with a "
                    f"different embedding method, or could not be opened."
                )
            })
            return response

        client, chr_collection = chroma_result

        # 4) Delete any existing vectors for this exact file_path
        try:
            chr_collection.delete(where={"path": file_path})
        except Exception:
            # If nothing was there or delete() fails on a new collection, ignore
            pass

        # 5) Build IDs, metadatas, documents, embeddings lists
        ids: List[str] = []
        metadatas: List[Dict[str, Any]] = []
        # texts is a list[str]; embeddings is a list of lists
        for idx, chunk_text in enumerate(texts):
            chunk_id = f"{collection_name}/{file_path}-{idx}"
            ids.append(chunk_id)
            metadatas.append({
                "path":         file_path,
                "filename":     os.path.basename(file_path),
                "chunk_number": idx,
                "emb_method":   "ada3large"
            })

        # 6) Insert into Chroma
        try:
            chr_collection.add(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=texts
            )
        except Exception as e:
            traceback.print_exc()
            response.update({
                "status": 500,
                "error": f"Error inserting vectors into Chroma: {e}"
            })
            return response

        # 7) Persist to disk
        try:
            client.persist()
        except Exception:
            # Chroma auto‐persists fairly often; we can ignore failures here
            pass

        # 8) Success
        response.update({
            "status": 200,
            "message": (
                f"Successfully stored {len(texts)} chunks into Chroma collection '{collection_name}'."
            )
        })
        return response


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    run_server(port=port, handler_instance=StoreVectorsAgent())

