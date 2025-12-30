import logging

import sqlalchemy as sa
from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ethelflow.agents.store_chunks.models import StoreChunksRequest, StoreChunksResponse
from ethelflow.data.db_utils import get_session
from ethelflow.data.models import Chunk, ChunkSet

logger = logging.getLogger("uvicorn.error")

app = FastAPI()


@app.post("/store_chunks", response_model=StoreChunksResponse)
async def store_chunks(req: StoreChunksRequest, session: AsyncSession = Depends(get_session)):
    logger.info(
        f"Storing chunks for text_id={req.text_id} method={req.method} n={len(req.chunks)} replace={req.replace}"
    )

    try:
        if req.replace:
            # Delete existing chunksets for same (text_id, method). Chunks cascade via FK ON DELETE CASCADE.
            await session.execute(
                sa.delete(ChunkSet).where(
                    ChunkSet.text_id == req.text_id,
                    ChunkSet.method == req.method,
                )
            )
            await session.flush()

        chunk_set = ChunkSet(text_id=req.text_id, method=req.method)
        session.add(chunk_set)
        await session.flush()  # ensure chunk_set.id is available

        new_chunks = [
            Chunk(chunk_set_id=chunk_set.id, text=chunk_text, position=i)
            for i, chunk_text in enumerate(req.chunks)
        ]
        session.add_all(new_chunks)
        await session.flush()  # ensure chunk ids are assigned

        await session.commit()

        return StoreChunksResponse(
            success=True,
            chunk_set_id=chunk_set.id,
            chunk_ids=[c.id for c in new_chunks],
        )

    except Exception as e:
        await session.rollback()
        logger.exception("store_chunks failed")
        return StoreChunksResponse(success=False, message=str(e))

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

