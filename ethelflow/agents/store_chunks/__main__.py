from fastapi import FastAPI, Depends
from sqlmodel import create_engine, Session
from ethelflow.agents.store_chunks.models import (
    StoreChunksRequest,
    StoreChunksResponse,
)
from ethelflow.data.models import ChunkSet, Chunk
from ethelflow.settings.postgres_settings import postgres_settings

engine = create_engine(postgres_settings.url)


def get_session():
    with Session(engine) as session:
        yield session


app = FastAPI()


@app.post("/store_chunks", response_model=StoreChunksResponse)
async def store_chunks(
    req: StoreChunksRequest, session: Session = Depends(get_session)
):
    try:
        chunk_set = ChunkSet(document_id=req.document_id, method=req.method)
        session.add(chunk_set)
        session.commit()
        session.refresh(chunk_set)

        new_chunks = []
        for i, chunk_text in enumerate(req.chunks):
            chunk = Chunk(chunk_set_id=chunk_set.id, text=chunk_text, position=i)
            new_chunks.append(chunk)

        session.add_all(new_chunks)
        session.commit()

        chunk_ids = [chunk.id for chunk in new_chunks]

        return StoreChunksResponse(
            success=True, chunk_set_id=chunk_set.id, chunk_ids=chunk_ids
        )

    except Exception as e:
        session.rollback()
        return StoreChunksResponse(success=False, message=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
