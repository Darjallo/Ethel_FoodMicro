import logging

import sqlalchemy as sa
from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from ethelflow.agents.store_chunks.models import StoreChunksRequest, StoreChunksResponse
from ethelflow.data.db_utils import get_session
from ethelflow.data.models import Chunk, ChunkSet

logger = logging.getLogger("uvicorn.error")
app = FastAPI()


@app.post("/store_chunks", response_model=StoreChunksResponse)
async def store_chunks(req: StoreChunksRequest, session: AsyncSession = Depends(get_session)):
    logger.info(
        "store_chunks: text_id=%s method=%s n=%d replace=%s",
        req.text_id,
        req.method,
        len(req.chunks),
        req.replace,
    )

    try:
        async with session.begin():
            # Lock existing row if present (serializes concurrent replace operations)
            lock_stmt = (
                sa.select(ChunkSet)
                .where(ChunkSet.text_id == req.text_id, ChunkSet.method == req.method)
                .with_for_update()
            )
            res = await session.execute(lock_stmt)
            chunk_set = res.scalar_one_or_none()

            if chunk_set is None:
                chunk_set = ChunkSet(text_id=req.text_id, method=req.method)
                session.add(chunk_set)
                try:
                    await session.flush()  # assigns chunk_set.id
                except IntegrityError:
                    # Another transaction created it due to unique constraint; re-fetch + lock
                    await session.rollback()
                    async with session.begin():
                        res = await session.execute(lock_stmt)
                        chunk_set = res.scalar_one()

            # If not replacing, just return existing chunk ids ordered by position
            if not req.replace:
                ids_res = await session.execute(
                    sa.select(Chunk.id)
                    .where(Chunk.chunk_set_id == chunk_set.id)
                    .order_by(Chunk.position)
                )
                return StoreChunksResponse(
                    success=True,
                    chunk_set_id=chunk_set.id,
                    chunk_ids=list(ids_res.scalars().all()),
                )

            # Replace: delete chunks for this chunkset (embeddings cascade via chunk FK)
            await session.execute(sa.delete(Chunk).where(Chunk.chunk_set_id == chunk_set.id))
            await session.flush()

            new_chunks = [
                Chunk(chunk_set_id=chunk_set.id, text=chunk_text, position=i)
                for i, chunk_text in enumerate(req.chunks)
            ]
            session.add_all(new_chunks)
            await session.flush()  # assigns chunk ids

            return StoreChunksResponse(
                success=True,
                chunk_set_id=chunk_set.id,
                chunk_ids=[c.id for c in new_chunks],
            )

    except Exception as e:
        await session.rollback()
        logger.exception("store_chunks failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

