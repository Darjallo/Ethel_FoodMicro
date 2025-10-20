from typing import AsyncGenerator

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from ethelflow.agents.store_vectors.models import (
    StoreVectorsRequest,
    StoreVectorsResponse,
)
from ethelflow.data.models import EmbeddingModel, TextEmbedding3LargeEmbedding
from ethelflow.settings.postgres_settings import postgres_settings

AsyncSessionLocal: sessionmaker[AsyncSession] = sessionmaker(
    create_async_engine(
        postgres_settings.async_url,
        pool_size=20,
        max_overflow=20,
    ),
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


app = FastAPI()


@app.post("/store_vectors", response_model=StoreVectorsResponse)
async def store_vectors(
    req: StoreVectorsRequest, session: AsyncSession = Depends(get_session)
):
    try:
        statement = select(EmbeddingModel).where(EmbeddingModel.name == req.model_name)
        embedding_model = (await session.execute(statement)).scalars().one_or_none()

        if not embedding_model:
            return StoreVectorsResponse(
                success=False,
                message=f"Model {req.model_name} not found.",
                num_vectors_stored=0,
            )

        if embedding_model.table_name != "embeddings_text_embedding_3_large":
            return StoreVectorsResponse(
                success=False,
                message=f"Table for model {req.model_name} not supported yet.",
                num_vectors_stored=0,
            )

        new_embeddings = []
        for chunk_id, vector in zip(req.chunk_ids, req.embeddings):
            new_embeddings.append(
                TextEmbedding3LargeEmbedding(chunk_id=chunk_id, vector=vector)
            )

        session.add_all(new_embeddings)
        await session.commit()

        return StoreVectorsResponse(
            success=True, num_vectors_stored=len(new_embeddings)
        )

    except Exception as e:
        await session.rollback()
        raise e

        # return StoreVectorsResponse(success=False, message=str(e), num_vectors_stored=0)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
