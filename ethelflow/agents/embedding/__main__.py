from fastapi import FastAPI, Depends, Request
from ethelflow.agents.embedding.models import EmbeddingRequest
from ethelflow.agents.embedding.settings import settings as embedding_settings
from openai import AsyncAzureOpenAI
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = AsyncAzureOpenAI(
        azure_endpoint=embedding_settings.azure_endpoint,
        api_version=embedding_settings.api_version,
        api_key=embedding_settings.api_key,
    )
    app.state.client = client
    yield
    await client.close()


app = FastAPI(lifespan=lifespan)


async def get_client(request: Request) -> AsyncAzureOpenAI:
    client: AsyncAzureOpenAI = request.app.state.client
    if not client:
        raise ValueError("Azure OpenAI client is not initialized.")
    return client


@app.post("/embedding")
async def embed(req: EmbeddingRequest, client: AsyncAzureOpenAI = Depends(get_client)):
    embeddings = await client.embeddings.create(input=req.texts, model=req.deployment)
    return embeddings


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
