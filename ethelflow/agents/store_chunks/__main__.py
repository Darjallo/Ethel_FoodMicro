import logging

import sqlalchemy as sa
from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

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
        await session.flush()  # assign chunk_set.id

        new_chunks = [
            Chunk(chunk_set_id=chunk_set.id, text=chunk_text, position=i)
            for i, chunk_text in enumerate(req.chunks)
        ]
        session.add_all(new_chunks)
        await session.flush()  # assign chunk ids

        await session.commit()

        return StoreChunksResponse(
            success=True,
            chunk_set_id=chunk_set.id,
            chunk_ids=[c.id for c in new_chunks],
        )

    except Exception as e:
        await session.rollback()
        logger.exception("store_chunks failed")
        # Make failures visible to callers (and to LangGraph node adapters)
        raise HTTPException(status_code=500, detail=str(e)) from e


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

