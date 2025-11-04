import logging

from pgvector.sqlalchemy import Vector
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import cast, func, select

from ethelflow.data.models import (
    Chunk,
    ChunkSet,
    EthelDocument,
    TextEmbedding3LargeEmbedding,
)

logger = logging.getLogger("uvicorn.error")


# Retrieve the most relevant chunks based on a query vector
async def get_relevant_chunks(
    session: AsyncSession,
    query_vector: list[float],
    top_k: int = 10,
    distance_threshold: float = 0.4,
    method=None,
):
    query_vec_expr = cast(query_vector, Vector(3072))
    distance = func.cosine_distance(
        TextEmbedding3LargeEmbedding.vector, query_vec_expr
    ).label("distance")

    logger.info(
        f"Querying for relevant chunks, top_k={top_k}, distance_threshold={distance_threshold}, method={method}"
    )

    stmt = (
        select(Chunk.text, EthelDocument.title, distance)
        .join(Chunk, Chunk.id == TextEmbedding3LargeEmbedding.chunk_id)
        .join(ChunkSet, ChunkSet.id == Chunk.chunk_set_id)
        .join(EthelDocument, EthelDocument.id == ChunkSet.document_id)
        .where(distance <= distance_threshold)
        .order_by(distance)
        .limit(top_k)
    )

    if method:
        stmt = stmt.where(ChunkSet.method == method)

    rows = (await session.execute(stmt)).all()

    logger.info(
        f"Found {len(rows)} relevant chunks, average distance: {sum(r.distance for r in rows) / len(rows) if rows else 0}"
    )

    results = [{"text": r.text, "title": r.title, "distance": r.distance} for r in rows]

    return results
