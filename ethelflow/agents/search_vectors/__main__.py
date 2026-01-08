from __future__ import annotations

import logging
import re
from typing import List

import sqlalchemy as sa
from fastapi import Depends, FastAPI
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from pgvector.sqlalchemy import Vector

from ethelflow.agents.search_vectors.models import SearchHit, SearchVectorsRequest, SearchVectorsResponse
from ethelflow.data.db_utils import get_session
from ethelflow.model_catalog import ModelCatalog

logger = logging.getLogger("uvicorn.error")
app = FastAPI()

_TABLE_IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _build_query_sql(table_name: str, dim: int) -> sa.sql.elements.TextClause:
    """
    Build SQL that:
      - restricts to doc_ids + extractor + chunk method
      - joins chunks to the embedding table
      - orders by cosine distance
      - uses halfvec cast automatically for dim > 2000 (matches your indexing strategy)
    """
    if dim > 2000:
        # Must match the halfvec expression index used for high-dimensional HNSW.
        order_expr = f"(e.vector::halfvec({dim}) <=> ((:qvec::vector({dim}))::halfvec({dim})))"
    else:
        # For <=2000 dims, we assume HNSW on vector (vector_cosine_ops) is fine.
        order_expr = "(e.vector <=> :qvec)"

    sql = f"""
    SELECT
      e.chunk_id AS chunk_id,
      {order_expr} AS distance
    FROM document_texts dt
    JOIN chunksets cs ON cs.text_id = dt.id
    JOIN chunks c ON c.chunk_set_id = cs.id
    JOIN public.{table_name} e ON e.chunk_id = c.id
    WHERE dt.document_id = ANY(:document_ids)
      AND dt.extractor = :extractor
      AND cs.method = :method
    ORDER BY distance
    LIMIT :top_k
    """
    return sa.text(sql)


@app.post("/search_vectors", response_model=SearchVectorsResponse)
async def search_vectors(req: SearchVectorsRequest, session: AsyncSession = Depends(get_session)):
    try:
        catalog = ModelCatalog.load()
        route = catalog.tenant_embedding_route(tenant=req.tenant, space=req.space)

        table_name = route.store_table
        dim = route.dimension

        if not isinstance(table_name, str) or not _TABLE_IDENT_RE.match(table_name):
            return SearchVectorsResponse(
                success=False,
                message=f"Unsafe/invalid store table name: {table_name!r}",
                tenant=req.tenant,
                space=route.space,
                store_table=table_name,
            )

        if len(req.query_embedding) != dim:
            return SearchVectorsResponse(
                success=False,
                message=f"Query embedding dimension mismatch: got {len(req.query_embedding)} expected {dim} for space={route.space}",
                tenant=req.tenant,
                space=route.space,
                store_table=table_name,
            )

        stmt = _build_query_sql(table_name=table_name, dim=dim)

        # Strong typing for array-of-uuid + vector binding
        stmt = stmt.bindparams(
            sa.bindparam(
                "document_ids",
                value=req.document_ids,
                type_=postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            ),
            sa.bindparam("extractor", value=req.extractor),
            sa.bindparam("method", value=req.method),
            sa.bindparam("top_k", value=req.top_k, type_=sa.Integer()),
            sa.bindparam("qvec", value=req.query_embedding, type_=Vector(dim)),
        )

        res = await session.execute(stmt)
        rows = res.fetchall()

        hits: List[SearchHit] = [SearchHit(chunk_id=r.chunk_id, distance=float(r.distance)) for r in rows]
        chunk_ids = [h.chunk_id for h in hits]

        return SearchVectorsResponse(
            success=True,
            tenant=req.tenant,
            space=route.space,
            store_table=table_name,
            hits=hits,
            chunk_ids=chunk_ids,
        )

    except Exception as e:
        logger.exception("search_vectors failed")
        return SearchVectorsResponse(
            success=False,
            message=str(e),
            tenant=req.tenant,
            space=req.space,
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

