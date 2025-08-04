from fastapi import FastAPI, Depends, Request
from ethelflow.agents.embedding.models import EmbeddingRequest, EmbeddingResponse
from ethelflow.settings.embedding_settings import settings as embedding_settings
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
async def embed(
    req: EmbeddingRequest, client: AsyncAzureOpenAI = Depends(get_client)
) -> EmbeddingResponse:
    response = await client.embeddings.create(input=req.texts, model=req.deployment)
    return EmbeddingResponse(
        embeddings=[item.embedding for item in response.data],
        model=response.model,
        usage=response.usage,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
