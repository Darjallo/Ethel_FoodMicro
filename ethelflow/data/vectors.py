import logging

from pgvector.sqlalchemy import HALFVEC
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, cast, text, select, Float

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
    embedding_model: SQLModel = TextEmbedding3LargeEmbedding,
    ef_search: int = 100,
    method=None,
):
    # FIXME: vector length is hardcoded here, should be derived from the model
    # we use the literal op "<=>" for cosine distance, otherwise Postgres doeesn't know that the index can be used
    distance = (
        cast(embedding_model.vector, HALFVEC(3072))
        .op("<=>")(cast(query_vector, HALFVEC(3072)))
        .cast(Float)
        .label("distance")
    )

    logger.info(
        f"Querying for relevant chunks, top_k={top_k}, distance_threshold={distance_threshold}, method={method}"
    )

    stmt = (
        select(Chunk.text, EthelDocument.title, distance)
        .select_from(embedding_model)
        .join(Chunk, Chunk.id == embedding_model.chunk_id)
        .join(ChunkSet, ChunkSet.id == Chunk.chunk_set_id)
        .join(EthelDocument, EthelDocument.id == ChunkSet.document_id)
        .where(distance <= distance_threshold)
        .order_by(distance)
        .limit(top_k)
    )

    if method:
        stmt = stmt.where(ChunkSet.method == method)

    async with session.begin():
        await session.execute(text(f"SET LOCAL hnsw.ef_search = {ef_search}"))
        rows = (await session.execute(stmt)).all()

    logger.info(
        f"Found {len(rows)} relevant chunks, average distance: {sum(r.distance for r in rows) / len(rows) if rows else 0}"
    )

    results = [{"text": r.text, "title": r.title, "distance": r.distance} for r in rows]

    return results
