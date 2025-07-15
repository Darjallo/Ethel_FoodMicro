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
#
#!/usr/bin/env python3
import os
import traceback
from datetime import datetime
from typing import Any, Dict, List
from ethelflow.agents.base_agent_server import run_server
from ethelflow.agents.base_vector_db import open_chroma_for


class EmbSimilarityAda3LargeAgent:
    """
    JSON in ::
       { "tenant": "ethz",
         "collection": "test_collection",
         "vector": [...],
         "k": 10 }
    Returns the k nearest chunks (cosine) from the tenant-scoped Chroma
    collection.
    """

    def handle(self, req: Dict[str, Any]) -> Dict[str, Any]:
        rsp: Dict[str, Any] = {
            "id": "emb_similarity_ada3large_response",
            "object": "task_result",
            "created": int(datetime.utcnow().timestamp()),
        }

        tenant = req.get("tenant")
        collection = req.get("collection")
        embedding = req.get("vector")
        k = req.get("k", 10)

        # ---- validate -------------------------------------------------------
        if not (isinstance(tenant, str) and tenant):
            rsp.update({"status": 400, "error": "Missing 'tenant'"})
            return rsp
        if not (isinstance(collection, str) and collection):
            rsp.update({"status": 400, "error": "Missing 'collection'"})
            return rsp
        if not (
            isinstance(embedding, list)
            and all(isinstance(x, (int, float)) for x in embedding)
        ):
            rsp.update({"status": 400, "error": "Invalid 'vector'"})
            return rsp
        try:
            k = int(k)
            assert k > 0
        except Exception:
            rsp.update({"status": 400, "error": "'k' must be positive int"})
            return rsp

        # ---- open Chroma collection ----------------------------------------
        chroma = open_chroma_for(
            tenant=tenant, collection_name=collection, emb_method="ada3large"
        )
        if chroma is None:
            rsp.update(
                {"status": 404, "error": f"No Chroma shard for {tenant}/{collection}"}
            )
            return rsp
        client, coll = chroma

        # ---- query ----------------------------------------------------------
        try:
            res = coll.query(
                query_embeddings=[embedding],
                n_results=k,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            traceback.print_exc()
            rsp.update({"status": 500, "error": f"Query failed: {e}"})
            return rsp

        hits: List[Dict[str, Any]] = []
        for idx in range(len(res["ids"][0])):
            hits.append(
                {
                    "id": res["ids"][0][idx],
                    "text": res["documents"][0][idx],
                    "metadata": res["metadatas"][0][idx],
                    "distance": res["distances"][0][idx],
                }
            )

        rsp.update({"status": 200, "results": hits})
        return rsp


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    run_server(port=port, handler_instance=EmbSimilarityAda3LargeAgent())
