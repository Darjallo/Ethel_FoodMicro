from __future__ import annotations

import logging
import os

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from ethelflow.agents.store_vectors.models import StoreVectorsRequest, StoreVectorsResponse
from ethelflow.data.db_utils import get_session
from ethelflow.data.models import TextEmbedding3LargeEmbedding  # keep your existing ORM table
from ethelflow.model_catalog import ModelCatalog

logger = logging.getLogger("uvicorn.error")

app = FastAPI()

# Minimal registry: catalog store_table -> ORM model
STORE_TABLE_REGISTRY = {
    "ada3_large": TextEmbedding3LargeEmbedding,
    # add more as you create tables/models
}


@app.post("/store_vectors", response_model=StoreVectorsResponse)
async def store_vectors(req: StoreVectorsRequest, session: AsyncSession = Depends(get_session)):
    """
    Store vectors for a tenant's embedding space.

    IMPORTANT: We do NOT look up "EmbeddingModel" in the DB anymore.
    The catalog is the source of truth for:
      tenant -> default_space
      space -> dimension + store.table
    """
    try:
        catalog = ModelCatalog.load()

        # Back-compat mapping if someone still sends model_name
        # (optional; remove later)
        if req.space is None and req.model_name:
            if req.model_name == "text-embedding-3-large":
                req.space = "ada3_large"

        route = catalog.tenant_embedding_route(tenant=req.tenant, space=req.space)

        model_cls = STORE_TABLE_REGISTRY.get(route.store_table)
        if not model_cls:
            return StoreVectorsResponse(
                success=False,
                message=f"Store table {route.store_table!r} not supported by store-vectors service.",
                num_vectors_stored=0,
                tenant=req.tenant,
                space=route.space,
                store_table=route.store_table,
            )

        # Dimension sanity check (helps catch tenant/space mistakes immediately)
        for v in req.embeddings:
            if len(v) != route.dimension:
                return StoreVectorsResponse(
                    success=False,
                    message=f"Vector dimension mismatch: got {len(v)} expected {route.dimension} for space={route.space}",
                    num_vectors_stored=0,
                    tenant=req.tenant,
                    space=route.space,
                    store_table=route.store_table,
                )

        new_rows = [model_cls(chunk_id=cid, vector=vec) for cid, vec in zip(req.chunk_ids, req.embeddings)]
        session.add_all(new_rows)
        await session.commit()

        return StoreVectorsResponse(
            success=True,
            num_vectors_stored=len(new_rows),
            tenant=req.tenant,
            space=route.space,
            store_table=route.store_table,
        )

    except Exception as e:
        await session.rollback()
        logger.exception("store_vectors failed")
        return StoreVectorsResponse(success=False, message=str(e), num_vectors_stored=0, tenant=req.tenant, space=req.space)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

