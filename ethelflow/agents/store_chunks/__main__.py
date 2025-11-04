import logging

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from ethelflow.agents.store_chunks.models import (
    StoreChunksRequest,
    StoreChunksResponse,
)
from ethelflow.data.db_utils import get_session
from ethelflow.data.models import Chunk, ChunkSet

logger = logging.getLogger("uvicorn.error")


app = FastAPI()


@app.post("/store_chunks", response_model=StoreChunksResponse)
async def store_chunks(
    req: StoreChunksRequest, session: AsyncSession = Depends(get_session)
):
    print(
        f"Storing chunks for document {req.document_id} with method {req.method}, number of chunks: {len(req.chunks)}"
    )
    try:
        chunk_set = ChunkSet(document_id=req.document_id, method=req.method)
        session.add(chunk_set)
        await session.flush()  # ensures chunk_set.id is available

        new_chunks = [
            Chunk(chunk_set_id=chunk_set.id, text=chunk_text, position=i)
            for i, chunk_text in enumerate(req.chunks)
        ]
        session.add_all(new_chunks)

        await session.commit()
        await session.refresh(chunk_set)

        return StoreChunksResponse(
            success=True,
            chunk_set_id=chunk_set.id,
            chunk_ids=[chunk.id for chunk in new_chunks],
        )

    except Exception:
        await session.rollback()
        raise

        # return StoreChunksResponse(success=False, message=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
