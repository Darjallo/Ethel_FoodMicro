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
#!/usr/bin/env python3
"""
StoreVectorsAgent
-----------------
Receives JSON::

    {
      "tenant":     "ethz",
      "file_id":    "ethz/test_collection/path/to/file.ext",
      "texts":      [...],
      "embeddings": [...]
    }

Splits tenant / collection / path and stores vectors in a tenant-scoped
Chroma collection whose on-disk location is::

    CHROMA_BASE_DIR/<tenant>/<sharded collection>/
"""

import os
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from chromadb import PersistentClient
from agent_pool.base_agent_server import run_server
from agent_pool.base_vector_db import open_chroma_for


class StoreVectorsAgent:
    """Vector-storage agent for multi-tenant Ethel."""

    # ------------------------------------------------------------------ handle
    def handle(self, request_json: Dict[str, Any]) -> Dict[str, Any]:
        rsp: Dict[str, Any] = {
            "id":      "store_vectors_response",
            "object":  "task_result",
            "created": int(datetime.utcnow().timestamp()),
        }

        # ---------- 1) Extract tenant / collection / path ----------
        tenant   = request_json.get("tenant")
        file_id  = request_json.get("file_id")

        if tenant and file_id and file_id.startswith(tenant + "/"):
            _, collection_name, file_path = file_id.split("/", 2)
        elif file_id:
            try:
                tenant, collection_name, file_path = file_id.split("/", 2)
            except ValueError:
                rsp.update({"status": 400,
                            "error": "file_id must be 'tenant/collection/path'"})
                return rsp
        else:
            rsp.update({"status": 400,
                        "error": "Missing 'file_id' (and/or 'tenant')."})
            return rsp

        # ---------- 2) Validate texts / embeddings ----------
        texts      = request_json.get("texts")
        embeds     = request_json.get("embeddings")

        if not (isinstance(texts, list) and all(isinstance(t, str) for t in texts)):
            rsp.update({"status": 400, "error": "'texts' must be list[str]."}); return rsp
        if not (isinstance(embeds, list) and all(isinstance(v, list) for v in embeds)):
            rsp.update({"status": 400, "error": "'embeddings' must be list[list[float]]."}); return rsp
        if len(texts) != len(embeds):
            rsp.update({"status": 400, "error": "texts/embeddings length mismatch"}); return rsp

        # ---------- 3) Open / create Chroma collection ----------
        chroma = open_chroma_for(
            tenant=tenant,
            collection_name=collection_name,
            emb_method="ada3large"
        )
        if chroma is None:
            rsp.update({"status": 400,
                        "error": "Chroma shard unavailable or emb_method mismatch."})
            return rsp
        client, coll = chroma

        # ---------- 4) Remove previous vectors for this file ----------
        try:
            coll.delete(where={"path": file_path})
        except Exception:
            pass

        # ---------- 5) Build ids & metadata ----------
        ids, metadatas = [], []
        for idx in range(len(texts)):
            ids.append(f"{tenant}/{collection_name}/{file_path}-{idx}")
            metadatas.append({
                "tenant":       tenant,
                "collection":   collection_name,
                "path":         file_path,
                "chunk_number": idx,
                "emb_method":   "ada3large"
            })

        # ---------- 6) Insert ----------
        try:
            coll.add(ids=ids, embeddings=embeds,
                     metadatas=metadatas, documents=texts)
        except Exception as e:
            traceback.print_exc()
            rsp.update({"status": 500, "error": f"Insertion failed: {e}"}); return rsp

        try:
            client.persist()
        except Exception:
            pass  # non-fatal

        rsp.update({"status": 200,
                    "message": f"Stored {len(texts)} chunks into {tenant}/{collection_name}."})
        return rsp


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    # PORT env allows overriding the default 8000
    port = int(os.getenv("PORT", "8000"))
    run_server(port=port, handler_instance=StoreVectorsAgent())

